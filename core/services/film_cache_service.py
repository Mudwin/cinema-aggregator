import logging
from typing import Dict, Optional
from django.core.cache import cache

logger = logging.getLogger(__name__)


class FilmCacheService:
    """
    Сервис для управления кэшированием данных о фильмах.
    Предотвращает проблемы с некорректным кэшированием.
    """
    
    @staticmethod
    def get_film_data(kinopoisk_id: int) -> Optional[Dict]:
        """
        Получение данных фильма из кэша с проверкой корректности.
        """
        cache_key = f'film_data_{kinopoisk_id}'
        data = cache.get(cache_key)
        
        if data:
            if data.get('kinopoisk_id') == kinopoisk_id:
                return data
            else:
                cache.delete(cache_key)
        
        return None
    
    @staticmethod
    def set_film_data(kinopoisk_id: int, data: Dict, timeout: int = 3600) -> None:
        """
        Сохранение данных фильма в кэш с проверкой.
        """
        if data.get('kinopoisk_id') != kinopoisk_id:
            return
        
        cache_key = f'film_data_{kinopoisk_id}'
        cache.set(cache_key, data, timeout)
    
    @staticmethod
    def clear_film_cache(kinopoisk_id: int) -> None:
        """
        Очистка кэша для конкретного фильма.
        """
        cache_key = f'film_data_{kinopoisk_id}'
        cache.delete(cache_key)
    
    @staticmethod
    def clear_all_film_cache() -> None:
        """
        Очистка всего кэша фильмов.
        """
        from django.core.cache import cache
        keys_to_delete = []
        
        for key in cache._cache.keys():
            if isinstance(key, str) and (key.startswith('film_data_') or 
                                         key.startswith('tmdb:') or 
                                         key.startswith('api_cache:')):
                keys_to_delete.append(key)
        
        cache.delete_many(keys_to_delete)