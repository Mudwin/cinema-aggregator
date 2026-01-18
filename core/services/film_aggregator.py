import logging
import re
from typing import Dict, List, Optional
from django.core.cache import cache

from .tmdb_service import TMDBService
from .omdb_service import OMDbService
from .kinopoisk_service import KinopoiskService

logger = logging.getLogger(__name__)


class FilmAggregator:
    """
    Сервис для агрегации всех данных о фильме из разных источников в реальном времени.
    """
    
    def __init__(self):
        self.tmdb_service = TMDBService()
        self.omdb_service = OMDbService()
        self.kinopoisk_service = KinopoiskService()
    
    def _clean_cache_key(self, key: str) -> str:
        """Очистка ключа кэша от недопустимых символов."""
        return key
    
    def get_film_data(self, tmdb_id: int) -> Optional[Dict]:
        """
        Получение всех данных о фильме в реальном времени.
        """
        try:
            cache_key = f'film_full_data_{tmdb_id}'
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
            
            tmdb_data = self._get_tmdb_movie_data(tmdb_id)
            
            if not tmdb_data:
                logger.error(f"No valid data from TMDB for ID {tmdb_id}")
                return None
            
            if not tmdb_data.get('title'):
                logger.error(f"Empty title in TMDB data for ID {tmdb_id}")
                return None
            
            title = tmdb_data.get('title', '')
            original_title = tmdb_data.get('original_title', '')

            if title == original_title and original_title:
                search_title = original_title
            else:
                search_title = title if title else original_title

            kinopoisk_search_title = search_title

            release_date = tmdb_data.get('release_date', '')
            year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
            
            poster_path = tmdb_data.get('poster_path', '')
            poster_url = f"https://image.tmdb.org/t/p/original{poster_path}" if poster_path else None
            
            film_data = {
                'tmdb_id': tmdb_data.get('id'),
                'title': tmdb_data.get('title', ''),
                'original_title': tmdb_data.get('original_title', ''),
                'year': year,
                'description': tmdb_data.get('overview', ''),
                'poster_url': poster_url,
                'imdb_id': tmdb_data.get('imdb_id', ''),
                'runtime': tmdb_data.get('runtime'),
                'genres': [genre['name'] for genre in tmdb_data.get('genres', [])],
                'countries': [country['name'] for country in tmdb_data.get('production_countries', [])],
                'tmdb_rating': tmdb_data.get('vote_average'),
                'tmdb_votes': tmdb_data.get('vote_count'),
            }
            
            ratings = self._get_all_ratings(film_data['imdb_id'], film_data['title'], film_data['year'])
            film_data['ratings'] = ratings
            
            normalized_ratings = []
            for source, rating in ratings.items():
                if 'value' in rating and 'max_value' in rating and rating['max_value'] > 0:
                    normalized_value = (rating['value'] / rating['max_value']) * 10
                    ratings[source]['normalized_value'] = normalized_value
                    normalized_ratings.append(normalized_value)
            
            if normalized_ratings:
                avg_rating = sum(normalized_ratings) / len(normalized_ratings)
                film_data['average_rating'] = round(avg_rating, 2)
                film_data['ratings_count'] = len(ratings)
            else:
                film_data['average_rating'] = None
                film_data['ratings_count'] = 0
            
            credits = tmdb_data.get('credits', {})
            
            directors = []
            for person in credits.get('crew', []):
                if person.get('job') == 'Director':
                    profile_path = person.get('profile_path', '')
                    directors.append({
                        'name': person.get('name', ''),
                        'photo_url': f"https://image.tmdb.org/t/p/w185{profile_path}" if profile_path else None,
                    })
            film_data['directors'] = directors[:3]
            
            actors = []
            for person in credits.get('cast', [])[:10]:
                profile_path = person.get('profile_path', '')
                actors.append({
                    'name': person.get('name', ''),
                    'character': person.get('character', ''),
                    'photo_url': f"https://image.tmdb.org/t/p/w185{profile_path}" if profile_path else None,
                })
            film_data['actors'] = actors
            
            cache.set(cache_key, film_data, 3600)
            
            return film_data
            
        except Exception as e:
            logger.error(f"Error aggregating film data for TMDB ID {tmdb_id}: {str(e)}")
            return None
    
    def _get_tmdb_movie_data(self, tmdb_id: int) -> Optional[Dict]:
        """
        Получение данных о фильме из TMDB с несколькими попытками и fallback.
        """
        languages = ['ru-RU', 'en-US']
        
        for language in languages:
            tmdb_data = self.tmdb_service.get_movie_details(
                tmdb_id,
                append_to_response='credits',
                language=language
            )
            
            if tmdb_data and tmdb_data.get('id') == tmdb_id:
                return tmdb_data
        
        logger.warning(f"Could not get movie {tmdb_id} directly, trying search...")
        
        search_cache_key = f'tmdb_movie_title_{tmdb_id}'
        movie_title = cache.get(search_cache_key)
        
        if not movie_title:
            for language in languages:
                temp_data = self.tmdb_service.get_movie_details(
                    tmdb_id,
                    language=language
                )
                if temp_data and temp_data.get('title'):
                    movie_title = temp_data.get('title')
                    cache.set(search_cache_key, movie_title, 3600)
                    break
        
        if movie_title:
            search_results = self.tmdb_service.search_movies(
                query=movie_title,
                year=None,
                page=1,
                language='en-US'
            )
            
            if search_results.get('results'):
                first_result = search_results['results'][0]
                correct_tmdb_id = first_result.get('id')
                
                if correct_tmdb_id and correct_tmdb_id != tmdb_id:
                    logger.info(f"Found correct ID for {movie_title}: {correct_tmdb_id} (was {tmdb_id})")
                    
                    for language in languages:
                        tmdb_data = self.tmdb_service.get_movie_details(
                            correct_tmdb_id,
                            append_to_response='credits',
                            language=language
                        )
                        
                        if tmdb_data and tmdb_data.get('id') == correct_tmdb_id:
                            return tmdb_data
        
        return None
    
    def _get_all_ratings(self, imdb_id: str, title: str, year: int) -> Dict:
        """
        Получение рейтингов из всех источников.
        """
        ratings = {}
        
        if imdb_id:
            try:
                omdb_ratings = self.omdb_service.get_movie_ratings(imdb_id)
                ratings.update(omdb_ratings)
            except Exception as e:
                logger.error(f"Error getting OMDb ratings for {imdb_id}: {str(e)}")
        
        if imdb_id:
            try:
                kinopoisk_movie = self.kinopoisk_service.get_movie_by_imdb_id(imdb_id)
                if kinopoisk_movie:
                    kp_ratings = self.kinopoisk_service.get_movie_rating(kinopoisk_movie)
                    ratings.update(kp_ratings)
            except Exception as e:
                logger.error(f"Error getting Kinopoisk ratings by IMDb ID {imdb_id}: {str(e)}")
        
        if 'kinopoisk' not in ratings and title:
            try:
                search_results = self.kinopoisk_service.search_movies(title, year=year, page=1)
                if search_results.get('items'):
                    kinopoisk_movie = search_results['items'][0]
                    kp_ratings = self.kinopoisk_service.get_movie_rating(kinopoisk_movie)
                    if 'kinopoisk' in kp_ratings:
                        ratings['kinopoisk'] = kp_ratings['kinopoisk']
            except Exception as e:
                logger.error(f"Error searching Kinopoisk by title {title}: {str(e)}")
        
        return ratings
    
    def search_films(self, query: str, year: Optional[int] = None) -> List[Dict]:
        """
        Поиск фильмов в TMDB.
        """
        try:
            cache_key = f'film_search_{query}_{year}'
            cached_results = cache.get(cache_key)
            if cached_results:
                return cached_results
            
            search_results = self.tmdb_service.search_movies(
                query=query,
                year=year,
                page=1
            )
            
            films = []
            for result in search_results.get('results', [])[:20]:
                if not result.get('id'):
                    continue
                    
                release_date = result.get('release_date', '')
                film_year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
                
                poster_path = result.get('poster_path', '')
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                
                film_data = {
                    'tmdb_id': result.get('id'),
                    'title': result.get('title', ''),
                    'original_title': result.get('original_title', ''),
                    'year': film_year,
                    'description': result.get('overview', ''),
                    'poster_url': poster_url,
                    'tmdb_rating': result.get('vote_average'),
                    'tmdb_votes': result.get('vote_count'),
                }
                films.append(film_data)
            
            cache.set(cache_key, films, 300)
            return films
            
        except Exception as e:
            logger.error(f"Error searching films: {str(e)}")
            return []