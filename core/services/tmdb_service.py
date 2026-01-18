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
    
    def get_cache_key(self, method: str, params: Dict) -> str:
        """
        Переопределяем метод генерации ключа кэша с учетом URL.
        """
        import hashlib
        import json
        
        cache_str = f"{method}:{self.BASE_URL}:{json.dumps(params, sort_keys=True)}"
        return f"tmdb_api:{hashlib.md5(cache_str.encode()).hexdigest()}"
    
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
            
        cache_key = f"tmdb_search_{query}_{year}_{page}_{language}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
            
        result = self.get("search/movie", params=params)
        self._set_cached(cache_key, result)
        return result
    
    @api_request_logger
    def get_movie_details(self, tmdb_id, append_to_response=None, language='ru-RU', force_refresh=False):
        """
        Получение детальной информации о фильме.
        """
        params = {"language": language}
        if append_to_response:
            params["append_to_response"] = append_to_response
        
        # Уникальный ключ кэша для каждого фильма
        cache_key = f"tmdb_movie_{tmdb_id}_{language}_{append_to_response}"
        
        if force_refresh:
            self._delete_cached(cache_key)
        
        cached = self._get_cached(cache_key)
        if cached:
            return cached
            
        result = self.get(f"movie/{tmdb_id}", params=params)
        
        # Валидация данных: убедимся, что это правильный фильм
        if result.get('id') != tmdb_id:
            logger.error(f"TMDB returned wrong movie! Requested ID: {tmdb_id}, Got ID: {result.get('id')}")
            self._delete_cached(cache_key)
            return None
            
        self._set_cached(cache_key, result)
        return result
    
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
        
        cache_key = f"tmdb_person_search_{query}_{page}_{language}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
            
        result = self.get("search/person", params=params)
        self._set_cached(cache_key, result)
        return result
    
    @api_request_logger
    def get_person_details(self, tmdb_id: int, language: str = 'ru-RU') -> Dict:
        """
        Получение детальной информации о персоне.
        """
        params = {"language": language}
        
        cache_key = f"tmdb_person_{tmdb_id}_{language}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
            
        result = self.get(f"person/{tmdb_id}", params=params)
        self._set_cached(cache_key, result)
        return result
    
    @api_request_logger
    def get_person_movie_credits(self, tmdb_id: int, language: str = 'ru-RU') -> Dict:
        """
        Получение фильмографии персоны.
        """
        params = {"language": language}
        
        cache_key = f"tmdb_person_credits_{tmdb_id}_{language}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
            
        result = self.get(f"person/{tmdb_id}/movie_credits", params=params)
        self._set_cached(cache_key, result)
        return result
    
    @api_request_logger
    def get_movie_credits(self, tmdb_id: int, language: str = 'ru-RU') -> Dict:
        """
        Получение информации о съемочной группе и актерах.
        """
        params = {"language": language}
        
        cache_key = f"tmdb_movie_credits_{tmdb_id}_{language}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
            
        result = self.get(f"movie/{tmdb_id}/credits", params=params)
        self._set_cached(cache_key, result)
        return result
    
    def _get_cached(self, cache_key: str):
        """Получение данных из кэша."""
        from django.core.cache import cache
        return cache.get(cache_key)
    
    def _set_cached(self, cache_key: str, data, timeout=None):
        """Сохранение данных в кэш."""
        from django.core.cache import cache
        if timeout is None:
            timeout = self.CACHE_TIMEOUT
        cache.set(cache_key, data, timeout)
    
    def _delete_cached(self, cache_key: str):
        """Удаление данных из кэша."""
        from django.core.cache import cache
        cache.delete(cache_key)