import logging
from typing import Optional, Dict

from django.conf import settings
from .base_api import BaseAPIClient, api_request_logger

logger = logging.getLogger(__name__)


class OMDbService(BaseAPIClient):
    """
    Сервис для работы с OMDb API (получение рейтингов IMDb, Rotten Tomatoes, Metacritic).
    """
    
    BASE_URL = "http://www.omdbapi.com"
    CACHE_TIMEOUT = 3600 * 12  # 12 часов для OMDb
    
    def setup_session(self):
        """Настройка сессии для OMDb API"""
        super().setup_session()
    
    @api_request_logger
    def get_movie_by_id(self, imdb_id: str) -> Dict:
        """
        Получение информации о фильме по IMDb ID.
        """
        params = {
            "i": imdb_id,
            "apikey": settings.OMDB_API_KEY
        }
        
        return self.get("/", params=params)
    
    @api_request_logger
    def get_movie_by_title(self, title: str) -> Dict:
        """
        Получение информации о фильме по названию.
        """
        params = {
            "t": title,
            "apikey": settings.OMDB_API_KEY
        }
        
        return self.get("/", params=params)
    
    @api_request_logger
    def search_movies(self, query: str, page: int = 1) -> Dict:
        """
        Поиск фильмов по названию.
        """
        params = {
            "s": query,
            "page": page,
            "apikey": settings.OMDB_API_KEY
        }
        
        return self.get("/", params=params)
    
    @api_request_logger
    def get_movie_ratings(self, imdb_id: str) -> Dict:
        """
        Получение рейтингов фильма по IMDb ID.
        """
        data = self.get_movie_by_id(imdb_id)
        
        if data.get("Response") == "False":
            return {}
        
        ratings = {}
        
        # IMDb рейтинг
        if "imdbRating" in data and data["imdbRating"] != "N/A":
            votes = data.get("imdbVotes", "0").replace(",", "")
            ratings["imdb"] = {
                "value": float(data["imdbRating"]),
                "max_value": 10,
                "votes": int(votes) if votes.isdigit() else 0
            }
        
        # Metacritic рейтинг
        if "Metascore" in data and data["Metascore"] != "N/A":
            ratings["metacritic"] = {
                "value": float(data["Metascore"]),
                "max_value": 100
            }
        
        # Рейтинги из массива Ratings
        if "Ratings" in data:
            for rating in data["Ratings"]:
                source = rating["Source"]
                value = rating["Value"]
                
                if "Rotten Tomatoes" in source:
                    # Rotten Tomatoes: "89%"
                    if "%" in value:
                        ratings["rotten_tomatoes"] = {
                            "value": float(value.replace("%", "")),
                            "max_value": 100
                        }
                
                # Metacritic в массиве Ratings
                elif "Metacritic" in source:
                    # Metacritic: "94/100"
                    if "/" in value:
                        val, max_val = value.split("/")
                        ratings["metacritic"] = {
                            "value": float(val),
                            "max_value": float(max_val)
                        }
        
        return ratings