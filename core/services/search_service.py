import logging
from typing import Dict, List, Optional, Tuple
from django.db import transaction
from django.utils import timezone

from ..models import Film, Person, FilmPersonRole, Rating
from .tmdb_service import TMDBService
from .omdb_service import OMDbService
from .kinopoisk_service import KinopoiskService
from ..tasks import update_film_ratings, update_person_data

logger = logging.getLogger(__name__)


class SearchService:
    """
    Сервис для управления логикой поиска фильмов.
    """
    
    def __init__(self):
        self.tmdb_service = TMDBService()
        self.omdb_service = OMDbService()
        self.kinopoisk_service = KinopoiskService()
    
    def search_and_import_film(self, tmdb_id: int) -> Tuple[Film, bool]:
        """
        Поиск и импорт фильма по TMDB ID.
        
        Args:
            tmdb_id (int): ID фильма в TMDB
        
        Returns:
            Tuple[Film, bool]: (объект фильма, создан ли новый)
        """
        film = Film.objects.filter(tmdb_id=tmdb_id).first()
        
        if film:
            logger.info(f"Film already exists: {film.title} (ID: {film.id})")
            return film, False
        
        logger.info(f"Fetching film data from TMDB for ID: {tmdb_id}")
        movie_data = self.tmdb_service.get_movie_details(
            tmdb_id,
            append_to_response='credits',
            language='ru-RU'
        )
        
        if not movie_data:
            raise ValueError(f"No data found for TMDB ID: {tmdb_id}")
        
        film = self._create_film_from_tmdb(movie_data)
        
        self._fetch_and_save_ratings(film)
        
        self._update_persons_data(film, movie_data.get('credits', {}))
        
        logger.info(f"Film imported successfully: {film.title} (ID: {film.id})")
        
        return film, True
    
    def _create_film_from_tmdb(self, movie_data: Dict) -> Film:
        """
        Создание объекта Film из данных TMDB.
        """
        release_date = movie_data.get('release_date', '')
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
        
        poster_path = movie_data.get('poster_path')
        poster_url = f"https://image.tmdb.org/t/p/original{poster_path}" if poster_path else None
        
        film, created = Film.objects.get_or_create(
            tmdb_id=movie_data.get('id'),
            defaults={
                'title': movie_data.get('title', ''),
                'original_title': movie_data.get('original_title', ''),
                'year': year,
                'description': movie_data.get('overview', ''),
                'poster_url': poster_url,
                'imdb_id': movie_data.get('imdb_id', '')
            }
        )
        
        if not created:
            film.title = movie_data.get('title', '')
            film.original_title = movie_data.get('original_title', '')
            film.year = year
            film.description = movie_data.get('overview', '')
            film.poster_url = poster_url
            film.imdb_id = movie_data.get('imdb_id', '')
            film.save()
        
        return film
    
    def _fetch_and_save_ratings(self, film: Film) -> None:
        """
        Получение и сохранение рейтингов для фильма.
        """
        ratings_data = {}
        
        if film.imdb_id:
            try:
                omdb_ratings = self.omdb_service.get_movie_ratings(film.imdb_id)
                ratings_data.update(omdb_ratings)
            except Exception as e:
                logger.error(f"Error fetching OMDb ratings for {film.title}: {str(e)}")
        
        try:
            kinopoisk_movie = self.kinopoisk_service.get_movie_by_imdb_id(
                film.imdb_id, 
                film_title=film.title,
                year=film.year
            )
            
            if kinopoisk_movie:
                kp_ratings = self.kinopoisk_service.get_movie_rating(kinopoisk_movie)
                
                if 'kinopoisk' in kp_ratings:
                    ratings_data['kinopoisk'] = kp_ratings['kinopoisk']
                
                if 'imdb' in kp_ratings and 'imdb' not in ratings_data:
                    ratings_data['imdb'] = kp_ratings['imdb']
            else:
                logger.warning(f"Film not found in Kinopoisk: {film.title} (IMDb: {film.imdb_id})")
                
        except Exception as e:
            logger.error(f"Error fetching Kinopoisk ratings for {film.title}: {str(e)}")
        
        if 'kinopoisk' not in ratings_data and film.title:
            try:
                search_results = self.kinopoisk_service.search_movies(
                    film.title, 
                    year=film.year,
                    page=1
                )
                
                if "items" in search_results and search_results["items"]:
                    kinopoisk_movie = search_results["items"][0]
                    kp_ratings = self.kinopoisk_service.get_movie_rating(kinopoisk_movie)
                    
                    if 'kinopoisk' in kp_ratings:
                        ratings_data['kinopoisk'] = kp_ratings['kinopoisk']
                        
            except Exception as e:
                logger.error(f"Error searching Kinopoisk by title for {film.title}: {str(e)}")
        
        self._save_ratings_to_db(film, ratings_data)
        
        from .rating_calculator import RatingCalculator
        composite_rating = RatingCalculator.calculate_composite_rating(film)
        if composite_rating:
            film.composite_rating = composite_rating
            film.save(update_fields=['composite_rating'])
    
    def _save_ratings_to_db(self, film: Film, ratings_data: Dict) -> None:
        """
        Сохранение рейтингов в базу данных.
        """
        source_mapping = {
            'imdb': Rating.SourceChoices.IMDB,
            'rotten_tomatoes': Rating.SourceChoices.ROTTEN_TOMATOES,
            'metacritic': Rating.SourceChoices.METACRITIC,
            'kinopoisk': Rating.SourceChoices.KINOPOISK
        }
        
        for source_key, rating_data in ratings_data.items():
            if source_key in source_mapping:
                Rating.objects.update_or_create(
                    film=film,
                    source=source_mapping[source_key],
                    defaults={
                        'value': rating_data['value'],
                        'max_value': rating_data['max_value'],
                        'votes_count': rating_data.get('votes', None),
                        'last_updated': timezone.now()
                    }
                )
    
    def _update_persons_data(self, film: Film, credits_data: Dict) -> None:
        """
        Обновление данных о персонах фильма.
        """
        crew = credits_data.get('crew', [])
        directors = [person for person in crew if person.get('job') == 'Director']
        
        for director_data in directors[:3]:  
            self._add_person_to_film(film, director_data, 'director')
        
        cast = credits_data.get('cast', [])[:15]
        
        for i, actor_data in enumerate(cast):
            self._add_person_to_film(film, actor_data, 'actor', character_name=actor_data.get('character'), order=i)
    
    def _add_person_to_film(self, film: Film, person_data: Dict, role: str, 
                           character_name: Optional[str] = None, order: int = 0) -> None:
        """
        Добавление персоны к фильму.
        """
        person_id = person_data.get('id')
        if not person_id:
            return
        
        person, created = Person.objects.get_or_create(
            tmdb_id=person_id,
            defaults={
                'name': person_data.get('name', ''),
                'original_name': person_data.get('original_name', ''),
                'profession': Person.ProfessionChoices.DIRECTOR if role == 'director' else Person.ProfessionChoices.ACTOR
            }
        )
        
        role_mapping = {
            'actor': FilmPersonRole.RoleChoices.ACTOR,
            'director': FilmPersonRole.RoleChoices.DIRECTOR
        }
        
        if role in role_mapping:
            FilmPersonRole.objects.get_or_create(
                film=film,
                person=person,
                role=role_mapping[role],
                defaults={
                    'character_name': character_name,
                    'order': order
                }
            )
        
        if created:
            update_person_data.delay(person.id)
    
    def batch_import_films(self, tmdb_ids: List[int]) -> Dict:
        """
        Пакетный импорт фильмов.
        
        Args:
            tmdb_ids (List[int]): Список TMDB ID
        
        Returns:
            Dict: Статистика импорта
        """
        stats = {
            'total': len(tmdb_ids),
            'imported': 0,
            'already_exist': 0,
            'failed': 0,
            'details': []
        }
        
        for tmdb_id in tmdb_ids:
            try:
                film, created = self.search_and_import_film(tmdb_id)
                
                if created:
                    stats['imported'] += 1
                    stats['details'].append({
                        'tmdb_id': tmdb_id,
                        'status': 'imported',
                        'film_id': film.id,
                        'film_title': film.title
                    })
                else:
                    stats['already_exist'] += 1
                    stats['details'].append({
                        'tmdb_id': tmdb_id,
                        'status': 'already_exists',
                        'film_id': film.id,
                        'film_title': film.title
                    })
                    
            except Exception as e:
                stats['failed'] += 1
                stats['details'].append({
                    'tmdb_id': tmdb_id,
                    'status': 'failed',
                    'error': str(e)
                })
                logger.error(f"Failed to import film with TMDB ID {tmdb_id}: {str(e)}")
        
        return stats