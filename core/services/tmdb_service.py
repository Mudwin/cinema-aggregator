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
                         language: str = 'ru-RU') -> Optional[Dict]:
        """
        Получение детальной информации о фильме.
        """
        params = {"language": language}
        if append_to_response:
            params["append_to_response"] = append_to_response
            
        try:
            result = self.get(f"movie/{tmdb_id}", params=params)
            
            if not result or result.get('id') != tmdb_id:
                logger.warning(f"TMDB returned wrong data for ID {tmdb_id}. Expected: {tmdb_id}, Got: {result.get('id') if result else 'None'}")
                return None
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting movie details for {tmdb_id}: {str(e)}")
            return None
    
    @api_request_logger
    def find_by_imdb_id(self, imdb_id: str, language: str = 'ru-RU') -> Dict:
        """
        Поиск фильма по IMDb ID.
        """
        params = {
            "external_source": "imdb_id",
            "language": language
        }
        
        return self.get(f"find/{imdb_id}", params=params)