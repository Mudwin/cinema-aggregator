import logging
from typing import Optional, Dict

from django.conf import settings
from django.core.cache import cache  # ДОБАВЬТЕ ЭТУ СТРОКУ!
from .base_api import BaseAPIClient, api_request_logger

logger = logging.getLogger(__name__)


class KinopoiskService(BaseAPIClient):
    """
    Сервис для работы с неофициальным Kinopoisk API.
    """
    
    BASE_URL = "https://kinopoiskapiunofficial.tech/api/v2.2"
    CACHE_TIMEOUT = 3600 * 6  # 6 часов для Kinopoisk
    
    def setup_session(self):
        """Настройка сессии для Kinopoisk API"""
        super().setup_session()
        self.session.headers.update({
            "X-API-KEY": settings.KINOPOISK_API_KEY,
            "Content-Type": "application/json"
        })
    
    def get_cache_key(self, method: str, params: Dict) -> str:
        """
        Переопределяем метод генерации ключа кэша для Kinopoisk.
        Убираем пробелы и специальные символы.
        """
        import hashlib
        import json
        
        cache_str = f"kinopoisk:{method}:{json.dumps(params, sort_keys=True)}"
        return f"kp:{hashlib.md5(cache_str.encode()).hexdigest()}"
    
    @api_request_logger
    def get_movie_details(self, kinopoisk_id: int) -> Dict:
        """
        Получение детальной информации о фильме по Kinopoisk ID.
        """
        try:
            result = self._make_request(
                'GET',
                f"films/{kinopoisk_id}",
                use_cache=False  
            )
            
            if not result:
                logger.error(f"Empty response from Kinopoisk for ID {kinopoisk_id}")
                return {}
            
            result_id = result.get('kinopoiskId') or result.get('kinopoisk_id') or result.get('id')
            if result_id != kinopoisk_id:
                logger.error(f"Kinopoisk returned wrong movie! Requested: {kinopoisk_id}, Got: {result_id}")
                return {}
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting movie details from Kinopoisk for ID {kinopoisk_id}: {str(e)}")
            return {}
    
    @api_request_logger
    def search_movies(self, query: str, year: Optional[int] = None, page: int = 1) -> Dict:
        """
        Поиск фильмов по названию.
        """
        params = {
            "keyword": query,
            "page": page
        }
        
        if year:
            params["yearFrom"] = year
            params["yearTo"] = year
            
        return self.get("films", params=params)
    
    @api_request_logger
    def get_movie_rating(self, film_data: Dict) -> Dict:
        """
        Получение рейтинга фильма с Кинопоиска.
        """
        try:
            kinopoisk_id = None
            
            if isinstance(film_data, dict):
                if 'kinopoiskId' in film_data:
                    kinopoisk_id = film_data['kinopoiskId']
                elif 'kinopoisk_id' in film_data:
                    kinopoisk_id = film_data['kinopoisk_id']
                elif 'id' in film_data and isinstance(film_data['id'], int):
                    kinopoisk_id = film_data['id']
            elif isinstance(film_data, int):
                kinopoisk_id = film_data
            
            if not kinopoisk_id:
                logger.warning(f"No kinopoisk_id found in film_data: {film_data}")
                return {}
            
            data = self.get_movie_details(kinopoisk_id)
            
            if not data:
                return {}
            
            ratings = {}
            
            if "ratingKinopoisk" in data and data["ratingKinopoisk"]:
                ratings["kinopoisk"] = {
                    "value": float(data["ratingKinopoisk"]),
                    "max_value": 10,
                    "votes": data.get("ratingKinopoiskVoteCount", 0)
                }
            
            if "ratingImdb" in data and data["ratingImdb"]:
                ratings["imdb"] = {
                    "value": float(data["ratingImdb"]),
                    "max_value": 10,
                    "votes": data.get("ratingImdbVoteCount", 0)
                }
            
            return ratings
            
        except Exception as e:
            logger.error(f"Error getting movie rating from Kinopoisk: {str(e)}")
            return {}
    
    @api_request_logger
    def get_movie_by_imdb_id(self, imdb_id: str, film_title: Optional[str] = None, year: Optional[int] = None) -> Optional[Dict]:
        """
        Поиск фильма по IMDb ID через Kinopoisk API.
        """
        try:
            search_results = self.search_movies(imdb_id, year=year, page=1)
            
            if "items" in search_results:
                for film in search_results["items"]:
                    if film.get("imdbId") == imdb_id:
                        return film
            
            if film_title:
                clean_title = self._clean_title_for_search(film_title)
                search_results = self.search_movies(clean_title, year=year, page=1)
                
                if "items" in search_results and search_results["items"]:
                    return search_results["items"][0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error searching movie by IMDb ID {imdb_id}: {str(e)}")
            return None

    def _clean_title_for_search(self, title: str) -> str:
        """
        Очистка названия фильма для поиска.
        """
        import re
        title = re.sub(r'\s*\(\d{4}\)', '', title)
        title = re.sub(r'\s*\([^)]*\)', '', title)
        title = re.sub(r'[^\w\s]', ' ', title, flags=re.UNICODE)
        title = ' '.join(title.split())
        
        return title