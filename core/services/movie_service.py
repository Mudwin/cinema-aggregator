import logging
import re
from typing import Dict, List, Optional
from django.core.cache import cache

from .tmdb_service import TMDBService
from .omdb_service import OMDbService
from .kinopoisk_service import KinopoiskService

logger = logging.getLogger(__name__)


class MovieService:
    """
    Основной сервис для работы с фильмами.
    Использует Kinopoisk для основной информации и рейтингов,
    TMDB для информации об актерах и режиссерах.
    """
    
    def __init__(self):
        self.tmdb_service = TMDBService()
        self.omdb_service = OMDbService()
        self.kinopoisk_service = KinopoiskService()
    
    def _clean_cache_key(self, key: str) -> str:
        """
        Очистка ключа кэша от недопустимых символов.
        """
        return re.sub(r'[^a-zA-Z0-9]', '_', key)
    
    def search_movies(self, query: str, year: Optional[int] = None) -> List[Dict]:
        """
        Поиск фильмов через Kinopoisk API.
        """
        try:
            safe_query = self._clean_cache_key(query)
            cache_key = f'movie_search_{safe_query}_{year}'
            cached_results = cache.get(cache_key)
            if cached_results:
                return cached_results
            
            search_results = self.kinopoisk_service.search_movies(
                query=query,
                year=year,
                page=1
            )
            
            films = []
            for item in search_results.get('items', [])[:20]:
                if not item.get('kinopoiskId'):
                    continue
                
                film = {
                    'kinopoisk_id': item['kinopoiskId'],
                    'title': item.get('nameRu') or item.get('nameOriginal') or item.get('nameEn', ''),
                    'original_title': item.get('nameOriginal') or item.get('nameEn') or item.get('nameRu', ''),
                    'year': item.get('year'),
                    'poster_url': item.get('posterUrl'),
                    'imdb_id': item.get('imdbId', ''),
                    'genres': [genre['genre'] for genre in item.get('genres', [])],
                    'countries': [country['country'] for country in item.get('countries', [])],
                    'rating_kinopoisk': item.get('ratingKinopoisk'),
                    'rating_imdb': item.get('ratingImdb'),
                    'type': item.get('type', 'FILM'),
                }
                films.append(film)
            
            cache.set(cache_key, films, 300)
            return films
            
        except Exception as e:
            logger.error(f"Ошибка поиска фильмов через Кинопоиск: {str(e)}")
            return []
    
    def _find_tmdb_id_for_film(self, title: str, original_title: str, year: int, imdb_id: str = None) -> Optional[int]:
        """
        Поиск TMDB ID для фильма по разным критериям.
        """
        if imdb_id:
            try:
                tmdb_data = self.tmdb_service.find_by_imdb_id(imdb_id, language='ru-RU')
                
                if tmdb_data and tmdb_data.get('movie_results'):
                    movie_result = tmdb_data['movie_results'][0]
                    if movie_result.get('id'):
                        logger.info(f"Найден TMDB ID {movie_result['id']} для IMDb {imdb_id}")
                        return movie_result['id']
            except Exception as e:
                logger.debug(f"Поиск в TMDB по IMDb ID вернулся с ошибкой: {str(e)}")
        
        search_attempts = []
        
        if title:
            search_attempts.append((title, 'ru-RU'))
        
        if original_title and original_title != title:
            search_attempts.append((original_title, 'en-US'))
        
        for search_title, language in search_attempts:
            try:
                search_results = self.tmdb_service.search_movies(
                    query=search_title,
                    year=year,
                    page=1,
                    language=language
                )
                
                if search_results.get('results'):
                    first_result = search_results['results'][0]
                    
                    if first_result.get('release_date'):
                        result_year = int(first_result['release_date'][:4]) if first_result['release_date'] else None
                        if not year or not result_year or abs(result_year - year) <= 2:
                            logger.info(f"Найдено TMDB ID {first_result['id']} для '{search_title}'")
                            return first_result['id']
            except Exception as e:
                logger.debug(f"Поиск в TMDB по названию вернулся с ошибкой для '{search_title}': {str(e)}")
                continue
        
        return None
    
    def get_movie_data(self, kinopoisk_id: int) -> Optional[Dict]:
        """
        Получение полных данных о фильме по Kinopoisk ID.
        """
        try:
            kp_details = self.kinopoisk_service.get_movie_details(kinopoisk_id)
            
            if not kp_details:
                logger.error(f"Нет данных на Кинопоиске для ID {kinopoisk_id}")
                return None
            
            result_id = kp_details.get('kinopoiskId') or kp_details.get('kinopoisk_id') or kp_details.get('id')
            if result_id != kinopoisk_id:
                logger.error(f"Кинопоиск вернул не тот фильм. Ожидалось: {kinopoisk_id}, получено: {result_id}")
                return None
            
            film_data = {
                'kinopoisk_id': kinopoisk_id,
                'title': kp_details.get('nameRu') or kp_details.get('nameOriginal') or kp_details.get('nameEn', ''),
                'original_title': kp_details.get('nameOriginal') or kp_details.get('nameEn') or kp_details.get('nameRu', ''),
                'year': kp_details.get('year'),
                'description': kp_details.get('description', ''),
                'poster_url': kp_details.get('posterUrl'),
                'imdb_id': kp_details.get('imdbId', ''),
                'runtime': kp_details.get('filmLength'),
                'genres': [genre['genre'] for genre in kp_details.get('genres', [])],
                'countries': [country['country'] for country in kp_details.get('countries', [])],
            }
            
            ratings = {}
            
            kp_rating = kp_details.get('ratingKinopoisk')
            if kp_rating:
                ratings['kinopoisk'] = {
                    'value': float(kp_rating),
                    'max_value': 10,
                    'votes': kp_details.get('ratingKinopoiskVoteCount', 0)
                }
            
            imdb_rating = kp_details.get('ratingImdb')
            if imdb_rating:
                ratings['imdb'] = {
                    'value': float(imdb_rating),
                    'max_value': 10,
                    'votes': kp_details.get('ratingImdbVoteCount', 0)
                }
            
            try:
                tmdb_id = self._find_tmdb_id_for_film(
                    title=film_data['title'],
                    original_title=film_data['original_title'],
                    year=film_data['year'],
                    imdb_id=film_data.get('imdb_id')
                )
                
                if tmdb_id:
                    tmdb_data = self.tmdb_service.get_movie_details(
                        tmdb_id,
                        append_to_response='credits',
                        language='ru-RU'
                    )
                    
                    if tmdb_data and tmdb_data.get('credits'):
                        credits = tmdb_data['credits']
                        film_data['tmdb_id'] = tmdb_id
                        
                        directors = []
                        for person in credits.get('crew', []):
                            if person.get('job') == 'Director':
                                profile_path = person.get('profile_path', '')
                                directors.append({
                                    'name': person.get('name', ''),
                                    'photo_url': f"https://image.tmdb.org/t/p/w185{profile_path}" if profile_path else None,
                                    'tmdb_id': person.get('id'), 
                                })
                        film_data['directors'] = directors[:3]
                        
                        actors = []
                        for person in credits.get('cast', [])[:10]:
                            profile_path = person.get('profile_path', '')
                            actors.append({
                                'name': person.get('name', ''),
                                'character': person.get('character', ''),
                                'photo_url': f"https://image.tmdb.org/t/p/w185{profile_path}" if profile_path else None,
                                'tmdb_id': person.get('id'),
                            })
                        film_data['actors'] = actors
                    else:
                        film_data['directors'] = []
                        film_data['actors'] = []
                else:
                    film_data['directors'] = []
                    film_data['actors'] = []
                    
            except Exception as e:
                logger.error(f"Ошибка получения данных из TMDB для актеров/режиссеров: {str(e)}")
                film_data['directors'] = []
                film_data['actors'] = []
            
            if film_data['imdb_id']:
                try:
                    omdb_ratings = self.omdb_service.get_movie_ratings(film_data['imdb_id'])
                    
                    for source, rating in omdb_ratings.items():
                        if source not in ratings:
                            ratings[source] = rating
                            
                except Exception as e:
                    logger.error(f"Ошибка получения рейтингов OMDb: {str(e)}")
            
            normalized_ratings = []
            for source, rating in ratings.items():
                if 'value' in rating and 'max_value' in rating and rating['max_value'] > 0:
                    normalized_value = (rating['value'] / rating['max_value']) * 10
                    ratings[source]['normalized_value'] = normalized_value
                    normalized_ratings.append(normalized_value)
            
            if normalized_ratings:
                avg_rating = sum(normalized_ratings) / len(normalized_ratings)
                film_data['average_rating'] = round(avg_rating, 2)
                film_data['ratings_count'] = len(ratings)
            else:
                film_data['average_rating'] = None
                film_data['ratings_count'] = 0
            
            film_data['ratings'] = ratings
            
            return film_data
            
        except Exception as e:
            logger.error(f"Ошибка получения данных для Kinopoisk ID {kinopoisk_id}: {str(e)}")
            return None