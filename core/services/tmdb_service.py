import requests
from django.conf import settings


class TMDBService:
    """
    Сервис для работы с The Movie Database (TMDB) API.
    """
    
    BASE_URL = "https://api.themoviedb.org/3"
    
    def __init__(self):
        self.api_key = settings.TMDB_API_KEY
        self.headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def search_movies(self, query, year=None, page=1, language='ru-RU'):
        """
        Поиск фильмов по названию.
        
        Args:
            query (str): Поисковый запрос
            year (int, optional): Год выпуска
            page (int): Номер страницы
            language (str): Язык ответа
        
        Returns:
            dict: Результаты поиска
        """
        params = {
            "query": query,
            "page": page,
            "language": language,
            "include_adult": "false"
        }
        if year:
            params["year"] = year
            
        response = requests.get(
            f"{self.BASE_URL}/search/movie",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_movie_details(self, tmdb_id, append_to_response=None, language='ru-RU'):
        """
        Получение детальной информации о фильме.
        
        Args:
            tmdb_id (int): ID фильма в TMDB
            append_to_response (str, optional): Дополнительные данные (videos,credits и т.д.)
            language (str): Язык ответа
        
        Returns:
            dict: Информация о фильме
        """
        params = {"language": language}
        if append_to_response:
            params["append_to_response"] = append_to_response
            
        response = requests.get(
            f"{self.BASE_URL}/movie/{tmdb_id}",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def search_person(self, query, page=1, language='ru-RU'):
        """
        Поиск персоны по имени.
        
        Args:
            query (str): Поисковый запрос
            page (int): Номер страницы
            language (str): Язык ответа
        
        Returns:
            dict: Результаты поиска
        """
        params = {
            "query": query,
            "page": page,
            "language": language,
            "include_adult": "false"
        }
            
        response = requests.get(
            f"{self.BASE_URL}/search/person",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_person_details(self, tmdb_id, language='ru-RU'):
        """
        Получение детальной информации о персоне.
        
        Args:
            tmdb_id (int): ID персоны в TMDB
            language (str): Язык ответа
        
        Returns:
            dict: Информация о персоне
        """
        params = {"language": language}
        
        response = requests.get(
            f"{self.BASE_URL}/person/{tmdb_id}",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_person_movie_credits(self, tmdb_id, language='ru-RU'):
        """
        Получение фильмографии персоны.
        
        Args:
            tmdb_id (int): ID персоны в TMDB
            language (str): Язык ответа
        
        Returns:
            dict: Фильмография персоны
        """
        params = {"language": language}
        
        response = requests.get(
            f"{self.BASE_URL}/person/{tmdb_id}/movie_credits",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_movie_credits(self, tmdb_id, language='ru-RU'):
        """
        Получение информации о съемочной группе и актерах.
        
        Args:
            tmdb_id (int): ID фильма в TMDB
            language (str): Язык ответа
        
        Returns:
            dict: Информация о съемочной группе
        """
        params = {"language": language}
        
        response = requests.get(
            f"{self.BASE_URL}/movie/{tmdb_id}/credits",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()