import logging
from typing import Dict, List, Optional
from django.core.cache import cache

from .tmdb_service import TMDBService
from .kinopoisk_service import KinopoiskService

logger = logging.getLogger(__name__)


class PersonService:
    """
    Сервис для работы с персонами.
    """
    
    def __init__(self):
        self.tmdb_service = TMDBService()
        self.kinopoisk_service = KinopoiskService()
    
    def get_person_data(self, tmdb_id: int) -> Optional[Dict]:
        """
        Получение всех данных о персоне по TMDB ID.
        """
        try:
            cache_key = f'person_data_{tmdb_id}'
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
            
            person_details = self.tmdb_service.get_person_details(tmdb_id)
            
            if not person_details:
                return None
            
            combined_credits = self.tmdb_service.get_person_combined_credits(tmdb_id)
            
            external_ids = self.tmdb_service.get_person_external_ids(tmdb_id)
            
            person_data = {
                'tmdb_id': person_details.get('id'),
                'name': person_details.get('name', ''),
                'original_name': person_details.get('original_name', ''),
                'biography': person_details.get('biography', ''),
                'photo_url': f"https://image.tmdb.org/t/p/h632{person_details.get('profile_path')}" if person_details.get('profile_path') else None,
                'birth_date': person_details.get('birthday', ''),
                'death_date': person_details.get('deathday', ''),
                'place_of_birth': person_details.get('place_of_birth', ''),
                'imdb_id': external_ids.get('imdb_id', ''),
                'known_for_department': person_details.get('known_for_department', ''),
                'popularity': person_details.get('popularity'),
            }
            
            filmography = []
            
            for credit in combined_credits.get('cast', []):
                if credit.get('media_type') == 'movie': 
                    film_data = self._format_credit_data(credit, 'actor')
                    filmography.append(film_data)
            
            for credit in combined_credits.get('crew', []):
                if credit.get('media_type') == 'movie':  
                    film_data = self._format_credit_data(credit, credit.get('job', 'crew'))
                    filmography.append(film_data)
            
            filmography.sort(key=lambda x: x.get('year', 0) or 0, reverse=True)
            
            person_data['filmography'] = filmography[:50]
            
            person_data['film_count'] = len(filmography)
            person_data['actor_roles'] = len([f for f in filmography if f.get('role_type') == 'actor'])
            person_data['crew_roles'] = len([f for f in filmography if f.get('role_type') != 'actor'])
            
            cache.set(cache_key, person_data, 3600 * 24) 
            
            return person_data
            
        except Exception as e:
            logger.error(f"Ошибка получения данных от TMDB ID {tmdb_id}: {str(e)}")
            return None
    
    def _format_credit_data(self, credit: Dict, role_type: str) -> Dict:
        """
        Форматирование данных о работе в фильме.
        """
        release_date = credit.get('release_date', '')
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
        
        poster_path = credit.get('poster_path', '')
        poster_url = f"https://image.tmdb.org/t/p/w200{poster_path}" if poster_path else None
        
        role = credit.get('character', '') if role_type == 'actor' else credit.get('job', '')
        
        return {
            'tmdb_id': credit.get('id'),
            'title': credit.get('title', ''),
            'original_title': credit.get('original_title', ''),
            'year': year,
            'poster_url': poster_url,
            'role': role,
            'role_type': role_type,
            'vote_average': credit.get('vote_average'),
            'vote_count': credit.get('vote_count'),
            'release_date': release_date,
        }
    
    def search_person_by_name(self, name: str) -> List[Dict]:
        """
        Поиск персоны по имени.
        """
        try:
            cache_key = f'person_search_{name}'
            cached_results = cache.get(cache_key)
            if cached_results:
                return cached_results
            
            search_results = self.tmdb_service.search_person(name)
            
            persons = []
            for result in search_results.get('results', [])[:10]:
                if not result.get('id'):
                    continue
                
                person = {
                    'tmdb_id': result.get('id'),
                    'name': result.get('name', ''),
                    'original_name': result.get('original_name', ''),
                    'photo_url': f"https://image.tmdb.org/t/p/w185{result.get('profile_path')}" if result.get('profile_path') else None,
                    'known_for_department': result.get('known_for_department', ''),
                    'popularity': result.get('popularity'),
                    'known_for': result.get('known_for', []),
                }
                persons.append(person)
            
            cache.set(cache_key, persons, 300)  
            return persons
            
        except Exception as e:
            logger.error(f"Ошибка поиска персоны по имени {name}: {str(e)}")
            return []
    
    def get_person_filmography_with_ratings(self, tmdb_id: int) -> List[Dict]:
        """
        Получение фильмографии с рейтингами (использует MovieService для получения рейтингов).
        """
        from .movie_service import MovieService
        
        try:
            person_data = self.get_person_data(tmdb_id)
            if not person_data or 'filmography' not in person_data:
                return []
            
            filmography = person_data['filmography']
            movie_service = MovieService()
            
            for film in filmography[:20]: 
                if film.get('tmdb_id'):
                    try:
                        search_results = self.kinopoisk_service.search_movies(
                            film['title'], 
                            year=film.get('year'),
                            page=1
                        )
                        
                        if search_results.get('items'):
                            kp_film = search_results['items'][0]
                            film['kinopoisk_id'] = kp_film.get('kinopoiskId')
                            film['rating_kinopoisk'] = kp_film.get('ratingKinopoisk')
                            film['rating_imdb'] = kp_film.get('ratingImdb')
                    except Exception as e:
                        continue
            
            return filmography
            
        except Exception as e:
            logger.error(f"Ошибка получения фильмографии для персоны с ID {tmdb_id}: {str(e)}")
            return []