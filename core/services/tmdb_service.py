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
    CACHE_TIMEOUT = 3600 * 24  
    
    def setup_session(self):
        """Настройка сессии для TMDB API"""
        super().setup_session()
        self.session.headers.update({
            "accept": "application/json",
            "Authorization": f"Bearer {settings.TMDB_API_KEY}"
        })
    
    def get_cache_key(self, method: str, params: Dict) -> str:
        """
        Переопределяем метод генерации ключа кэша для TMDB.
        """
        import hashlib
        import json
        
        cache_parts = [
            "tmdb_api",
            method,
            json.dumps(params, sort_keys=True)
        ]
        cache_str = ":".join(cache_parts)
        return f"tmdb:{hashlib.md5(cache_str.encode()).hexdigest()}"
    
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
    def get_movie_details(self, tmdb_id: int, append_to_response: Optional[str] = None, 
                         language: str = 'ru-RU', force_refresh: bool = False) -> Optional[Dict]:
        """
        Получение детальной информации о фильме.
        Возвращает None если получены некорректные данные.
        """
        params = {"language": language}
        if append_to_response:
            params["append_to_response"] = append_to_response
        
        use_cache = not force_refresh
        
        try:
            result = self.get(f"movie/{tmdb_id}", params=params, use_cache=use_cache)
            
            if not result or result.get('id') != tmdb_id:
                logger.warning(f"TMDB returned wrong data for ID {tmdb_id}. Expected: {tmdb_id}, Got: {result.get('id') if result else 'None'}")
                return None
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting movie details for {tmdb_id}: {str(e)}")
            return None
    
    @api_request_logger
    def search_movie_by_title(self, title: str, year: Optional[int] = None, 
                             language: str = 'ru-RU') -> Optional[Dict]:
        """
        Поиск фильма по названию и возврат первого результата.
        """
        try:
            search_results = self.search_movies(title, year, language=language)
            if search_results.get('results'):
                return search_results['results'][0]
            return None
        except Exception as e:
            logger.error(f"Error searching movie by title {title}: {str(e)}")
            return None
    
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