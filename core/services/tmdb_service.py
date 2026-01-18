import logging
from typing import Optional, Dict

from django.conf import settings
from .base_api import BaseAPIClient, api_request_logger

logger = logging.getLogger(__name__)


class TMDBService(BaseAPIClient):
    """
    Сервис для работы с The Movie Database (TMDB) API.
    """
    
    BASE_URL = "https://api.themoviedb.org/3"
    CACHE_TIMEOUT = 3600 * 24  # 24 часа для TMDB 
    
    def setup_session(self):
        """Настройка сессии для TMDB API"""
        super().setup_session()
        self.session.headers.update({
            "accept": "application/json",
            "Authorization": f"Bearer {settings.TMDB_API_KEY}"
        })
    
    @api_request_logger
    def search_movies(self, query: str, year: Optional[int] = None, page: int = 1, language: str = 'ru-RU') -> Dict:
        """
        Поиск фильмов по названию.
        """
        params = {
            "query": query,
            "page": page,
            "language": language,
            "include_adult": "false"
        }
        if year:
            params["year"] = year
            
        return self.get("search/movie", params=params)
    
    @api_request_logger
    def get_movie_details(self, tmdb_id, append_to_response=None, language='ru-RU', force_refresh=False):
        """
        Получение детальной информации о фильме.
        """
        params = {"language": language}
        if append_to_response:
            params["append_to_response"] = append_to_response
            
        if force_refresh:
            cache_key = f"tmdb_movie_{tmdb_id}_{language}_{append_to_response}"
            from django.core.cache import cache
            cache.delete(cache_key)
        
        return self.get(f"movie/{tmdb_id}", params=params)
    
    @api_request_logger
    def search_person(self, query: str, page: int = 1, language: str = 'ru-RU') -> Dict:
        """
        Поиск персоны по имени.
        """
        params = {
            "query": query,
            "page": page,
            "language": language,
            "include_adult": "false"
        }
            
        return self.get("search/person", params=params)
    
    @api_request_logger
    def get_person_details(self, tmdb_id: int, language: str = 'ru-RU') -> Dict:
        """
        Получение детальной информации о персоне.
        """
        params = {"language": language}
        
        return self.get(f"person/{tmdb_id}", params=params)
    
    @api_request_logger
    def get_person_movie_credits(self, tmdb_id: int, language: str = 'ru-RU') -> Dict:
        """
        Получение фильмографии персоны.
        """
        params = {"language": language}
        
        return self.get(f"person/{tmdb_id}/movie_credits", params=params)
    
    @api_request_logger
    def get_movie_credits(self, tmdb_id: int, language: str = 'ru-RU') -> Dict:
        """
        Получение информации о съемочной группе и актерах.
        """
        params = {"language": language}
        
        return self.get(f"movie/{tmdb_id}/credits", params=params)