import logging
import re
from typing import Dict, List, Optional, Tuple
from django.core.cache import cache

from .tmdb_service import TMDBService
from .omdb_service import OMDbService
from .kinopoisk_service import KinopoiskService

logger = logging.getLogger(__name__)


class MovieService:
    """
    Основной сервис для работы с фильмами.
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
            logger.error(f"Error searching movies via Kinopoisk: {str(e)}")
            return []
    
    def get_movie_data(self, kinopoisk_id: int) -> Optional[Dict]:
        """
        Получение полных данных о фильме по Kinopoisk ID.
        """

        logger.info(f"=== START get_movie_data for ID: {kinopoisk_id} ===")

        try:
            # cache_key = f'film_data_{kinopoisk_id}'
            # cached_data = cache.get(cache_key)
            # if cached_data:
            #     return cached_data
            
            kp_details = self.kinopoisk_service.get_movie_details(kinopoisk_id)
            
            if not kp_details:
                logger.error(f"No data from Kinopoisk for ID {kinopoisk_id}")
                return None
            
            result_id = kp_details.get('kinopoiskId') or kp_details.get('kinopoisk_id') or kp_details.get('id')
            if result_id != kinopoisk_id:
                logger.error(f"Kinopoisk returned wrong movie! Expected: {kinopoisk_id}, Got: {result_id}")
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
            
            if film_data['imdb_id']:
                try:
                    omdb_ratings = self.omdb_service.get_movie_ratings(film_data['imdb_id'])
                    
                    for source, rating in omdb_ratings.items():
                        if source not in ratings:
                            ratings[source] = rating
                            
                except Exception as e:
                    logger.error(f"Error getting OMDb ratings: {str(e)}")
            
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
            
            # cache.set(cache_key, film_data, 3600)
            
            return film_data
            
        except Exception as e:
            logger.error(f"=== ERROR get_movie_data for ID {kinopoisk_id}: {str(e)} ===")
            import traceback
            logger.error(traceback.format_exc())
            return None