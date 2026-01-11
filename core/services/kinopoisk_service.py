import logging
from typing import Optional, Dict

from django.conf import settings
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
    
    @api_request_logger
    def get_movie_details(self, kinopoisk_id: int) -> Dict:
        """
        Получение детальной информации о фильме по Kinopoisk ID.
        """
        return self.get(f"films/{kinopoisk_id}")
    
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
    def get_movie_rating(self, kinopoisk_id: int) -> Dict:
        """
        Получение рейтинга фильма с Кинопоиска.
        """
        data = self.get_movie_details(kinopoisk_id)
        
        ratings = {}
        
        # Рейтинг Кинопоиска
        if "ratingKinopoisk" in data and data["ratingKinopoisk"]:
            ratings["kinopoisk"] = {
                "value": float(data["ratingKinopoisk"]),
                "max_value": 10,
                "votes": data.get("ratingKinopoiskVoteCount", 0)
            }
        
        # IMDb рейтинг (из Kinopoisk API)
        if "ratingImdb" in data and data["ratingImdb"]:
            ratings["imdb"] = {
                "value": float(data["ratingImdb"]),
                "max_value": 10,
                "votes": data.get("ratingImdbVoteCount", 0)
            }
        
        # Рейтинг кинокритиков
        if "ratingFilmCritics" in data and data["ratingFilmCritics"]:
            ratings["film_critics"] = {
                "value": float(data["ratingFilmCritics"]),
                "max_value": 10,
                "votes": data.get("ratingFilmCriticsVoteCount", 0)
            }
        
        # Рейтинг ожидания
        if "ratingAwait" in data and data["ratingAwait"]:
            ratings["await"] = {
                "value": float(data["ratingAwait"]),
                "max_value": 10,
                "votes": data.get("ratingAwaitCount", 0)
            }
        
        # Рейтинг российских кинокритиков
        if "ratingRfCritics" in data and data["ratingRfCritics"]:
            ratings["rf_critics"] = {
                "value": float(data["ratingRfCritics"]),
                "max_value": 10,
                "votes": data.get("ratingRfCriticsVoteCount", 0)
            }
        
        return ratings
    
    @api_request_logger
    def get_movie_by_imdb_id(self, imdb_id: str) -> Optional[Dict]:
        """
        Поиск фильма по IMDb ID через Kinopoisk API.
        """
        search_results = self.search_movies(imdb_id)
        
        if "items" in search_results:
            for film in search_results["items"]:
                if film.get("imdbId") == imdb_id:
                    return film
        
        return None