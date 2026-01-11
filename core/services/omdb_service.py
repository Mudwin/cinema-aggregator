import requests
from django.conf import settings


class OMDbService:
    """
    Сервис для работы с OMDb API (получение рейтингов IMDb, Rotten Tomatoes, Metacritic).
    """
    
    BASE_URL = "http://www.omdbapi.com/"
    
    def __init__(self):
        self.api_key = settings.OMDB_API_KEY
    
    def get_movie_by_id(self, imdb_id):
        """
        Получение информации о фильме по IMDb ID.
        
        Args:
            imdb_id (str): IMDb ID фильма (например: 'tt0111161')
        
        Returns:
            dict: Информация о фильме
        """
        params = {
            "i": imdb_id,
            "apikey": self.api_key
        }
        
        response = requests.get(self.BASE_URL, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_movie_by_title(self, title):
        """
        Получение информации о фильме по названию.
        
        Args:
            title (str): Название фильма
        
        Returns:
            dict: Информация о фильме
        """
        params = {
            "t": title,
            "apikey": self.api_key
        }
        
        response = requests.get(self.BASE_URL, params=params)
        response.raise_for_status()
        return response.json()
    
    def search_movies(self, query, page=1):
        """
        Поиск фильмов по названию.
        
        Args:
            query (str): Поисковый запрос
            page (int): Номер страницы
        
        Returns:
            dict: Результаты поиска
        """
        params = {
            "s": query,
            "page": page,
            "apikey": self.api_key
        }
        
        response = requests.get(self.BASE_URL, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_movie_ratings(self, imdb_id):
        """
        Получение рейтингов фильма по IMDb ID.
        
        Args:
            imdb_id (str): IMDb ID фильма (например: 'tt0111161')
        
        Returns:
            dict: Рейтинги из различных источников
        """
        data = self.get_movie_by_id(imdb_id)
        
        if data.get("Response") == "False":
            return {}
        
        ratings = {}
        
        # IMDb 
        if "imdbRating" in data and data["imdbRating"] != "N/A":
            votes = data.get("imdbVotes", "0").replace(",", "")
            ratings["imdb"] = {
                "value": float(data["imdbRating"]),
                "max_value": 10,
                "votes": int(votes) if votes.isdigit() else 0
            }
        
        # Metacritic
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
                    # Rotten Tomatoes
                    if "%" in value:
                        ratings["rotten_tomatoes"] = {
                            "value": float(value.replace("%", "")),
                            "max_value": 100
                        }
                
                elif "Metacritic" in source:
                    # Metacritic
                    if "/" in value:
                        val, max_val = value.split("/")
                        ratings["metacritic"] = {
                            "value": float(val),
                            "max_value": float(max_val)
                        }
        
        return ratings