import requests
from django.conf import settings


class KinopoiskService:
    """
    Сервис для работы с неофициальным Kinopoisk API.
    """
    
    BASE_URL = "https://kinopoiskapiunofficial.tech/api/v2.2"
    
    def __init__(self):
        self.api_key = settings.KINOPOISK_API_KEY
        self.headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
    
    def get_movie_details(self, kinopoisk_id):
        """
        Получение детальной информации о фильме по Kinopoisk ID.
        
        Args:
            kinopoisk_id (int): ID фильма в Kinopoisk
        
        Returns:
            dict: Информация о фильме
        """
        response = requests.get(
            f"{self.BASE_URL}/films/{kinopoisk_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
    
    def search_movies(self, query, year=None, page=1):
        """
        Поиск фильмов по названию.
        
        Args:
            query (str): Поисковый запрос
            year (int, optional): Год выпуска
            page (int): Номер страницы
        
        Returns:
            dict: Результаты поиска
        """
        params = {
            "keyword": query,
            "page": page
        }
        
        if year:
            params["yearFrom"] = year
            params["yearTo"] = year
            
        response = requests.get(
            f"{self.BASE_URL}/films",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_movie_rating(self, kinopoisk_id):
        """
        Получение рейтинга фильма с Кинопоиска.
        
        Args:
            kinopoisk_id (int): ID фильма в Kinopoisk
        
        Returns:
            dict: Рейтинги Кинопоиска
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
    
    def get_movie_by_imdb_id(self, imdb_id):
        """
        Поиск фильма по IMDb ID через Kinopoisk API.
        
        Args:
            imdb_id (str): IMDb ID фильма
        
        Returns:
            dict: Информация о фильме
        """
        search_results = self.search_movies(imdb_id)
        
        if "items" in search_results:
            for film in search_results["items"]:
                if film.get("imdbId") == imdb_id:
                    return film
        
        return None