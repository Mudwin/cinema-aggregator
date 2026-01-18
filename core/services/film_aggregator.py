import logging
from typing import Dict, List, Optional
from django.core.cache import cache

from .tmdb_service import TMDBService
from .omdb_service import OMDbService
from .kinopoisk_service import KinopoiskService

logger = logging.getLogger(__name__)


class FilmAggregator:
    """
    Сервис для агрегации всех данных о фильме из разных источников в реальном времени.
    Работает без сохранения в базу данных.
    """
    
    def __init__(self):
        self.tmdb_service = TMDBService()
        self.omdb_service = OMDbService()
        self.kinopoisk_service = KinopoiskService()
    
    def get_film_data(self, tmdb_id: int) -> Optional[Dict]:
        """
        Получение всех данных о фильме в реальном времени.
        
        Args:
            tmdb_id (int): ID фильма в TMDB
            
        Returns:
            Dict: Все данные о фильме или None если ошибка
        """
        try:
            cache_key = f'film_full_data_{tmdb_id}'
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
            
            tmdb_data = self.tmdb_service.get_movie_details(
                tmdb_id,
                append_to_response='credits',
                language='ru-RU',
                force_refresh=True  
            )
            
            if not tmdb_data:
                logger.error(f"No data from TMDB for ID {tmdb_id}")
                return None
            
            release_date = tmdb_data.get('release_date', '')
            year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
            
            film_data = {
                'tmdb_id': tmdb_id,
                'title': tmdb_data.get('title', ''),
                'original_title': tmdb_data.get('original_title', ''),
                'year': year,
                'description': tmdb_data.get('overview', ''),
                'poster_url': f"https://image.tmdb.org/t/p/original{tmdb_data.get('poster_path', '')}" if tmdb_data.get('poster_path') else None,
                'imdb_id': tmdb_data.get('imdb_id', ''),
                'runtime': tmdb_data.get('runtime'),
                'genres': [genre['name'] for genre in tmdb_data.get('genres', [])],
                'countries': [country['name'] for country in tmdb_data.get('production_countries', [])],
                'tmdb_rating': tmdb_data.get('vote_average'),
                'tmdb_votes': tmdb_data.get('vote_count'),
            }
            
            ratings = self._get_all_ratings(tmdb_data)
            film_data['ratings'] = ratings
            
            if ratings:
                normalized_ratings = []
                for rating in ratings.values():
                    if 'normalized_value' in rating:
                        normalized_ratings.append(rating['normalized_value'])
                
                if normalized_ratings:
                    avg_rating = sum(normalized_ratings) / len(normalized_ratings)
                    film_data['average_rating'] = round(avg_rating, 2)
                    film_data['ratings_count'] = len(ratings)
            
            credits = tmdb_data.get('credits', {})
            
            directors = []
            for person in credits.get('crew', []):
                if person.get('job') == 'Director':
                    directors.append({
                        'name': person.get('name', ''),
                        'photo_url': f"https://image.tmdb.org/t/p/w185{person.get('profile_path')}" if person.get('profile_path') else None,
                    })
            film_data['directors'] = directors[:3]  
            
            actors = []
            for person in credits.get('cast', [])[:10]:
                actors.append({
                    'name': person.get('name', ''),
                    'character': person.get('character', ''),
                    'photo_url': f"https://image.tmdb.org/t/p/w185{person.get('profile_path')}" if person.get('profile_path') else None,
                })
            film_data['actors'] = actors
            
            cache.set(cache_key, film_data, 3600)
            
            return film_data
            
        except Exception as e:
            logger.error(f"Error aggregating film data for TMDB ID {tmdb_id}: {str(e)}")
            return None
    
    def _get_all_ratings(self, tmdb_data: Dict) -> Dict:
        """
        Получение рейтингов из всех источников.
        
        Returns:
            Dict: Словарь со всеми рейтингами
        """
        ratings = {}
        
        if tmdb_data.get('vote_average'):
            ratings['tmdb'] = {
                'source': 'TMDB',
                'value': tmdb_data.get('vote_average'),
                'max_value': 10,
                'normalized_value': tmdb_data.get('vote_average'),
                'votes': tmdb_data.get('vote_count', 0)
            }
        
        imdb_id = tmdb_data.get('imdb_id')
        if not imdb_id:
            return ratings
        
        try:
            omdb_ratings = self.omdb_service.get_movie_ratings(imdb_id)
            
            if 'imdb' in omdb_ratings:
                ratings['imdb'] = {
                    'source': 'IMDb',
                    'value': omdb_ratings['imdb']['value'],
                    'max_value': omdb_ratings['imdb']['max_value'],
                    'normalized_value': omdb_ratings['imdb']['value'],
                    'votes': omdb_ratings['imdb'].get('votes', 0)
                }
            
            if 'rotten_tomatoes' in omdb_ratings:
                ratings['rotten_tomatoes'] = {
                    'source': 'Rotten Tomatoes',
                    'value': omdb_ratings['rotten_tomatoes']['value'],
                    'max_value': omdb_ratings['rotten_tomatoes']['max_value'],
                    'normalized_value': omdb_ratings['rotten_tomatoes']['value'] / 10,  # Из 100% в 10
                    'votes': None
                }
            
            if 'metacritic' in omdb_ratings:
                ratings['metacritic'] = {
                    'source': 'Metacritic',
                    'value': omdb_ratings['metacritic']['value'],
                    'max_value': omdb_ratings['metacritic']['max_value'],
                    'normalized_value': omdb_ratings['metacritic']['value'] / 10,  # Из 100 в 10
                    'votes': None
                }
                
        except Exception as e:
            logger.error(f"Error getting OMDb ratings: {str(e)}")
        
        try:
            title = tmdb_data.get('title', '')
            year = tmdb_data.get('release_date', '')[:4] if tmdb_data.get('release_date') else None
            
            search_results = self.kinopoisk_service.search_movies(title, year=year, page=1)
            
            if search_results.get('items'):
                kinopoisk_movie = search_results['items'][0]
                
                if kinopoisk_movie.get('ratingKinopoisk'):
                    ratings['kinopoisk'] = {
                        'source': 'Кинопоиск',
                        'value': kinopoisk_movie['ratingKinopoisk'],
                        'max_value': 10,
                        'normalized_value': kinopoisk_movie['ratingKinopoisk'],
                        'votes': kinopoisk_movie.get('ratingKinopoiskVoteCount', 0)
                    }
                
                if kinopoisk_movie.get('ratingImdb') and 'imdb' not in ratings:
                    ratings['imdb'] = {
                        'source': 'IMDb',
                        'value': kinopoisk_movie['ratingImdb'],
                        'max_value': 10,
                        'normalized_value': kinopoisk_movie['ratingImdb'],
                        'votes': kinopoisk_movie.get('ratingImdbVoteCount', 0)
                    }
                    
        except Exception as e:
            logger.error(f"Error getting Kinopoisk ratings: {str(e)}")
        
        return ratings
    
    def search_films(self, query: str, year: Optional[int] = None) -> List[Dict]:
        """
        Поиск фильмов в TMDB.
        
        Returns:
            List[Dict]: Список найденных фильмов
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
                film_data = {
                    'tmdb_id': result.get('id'),
                    'title': result.get('title', ''),
                    'original_title': result.get('original_title', ''),
                    'year': result.get('release_date', '')[:4] if result.get('release_date') else None,
                    'description': result.get('overview', ''),
                    'poster_url': f"https://image.tmdb.org/t/p/w500{result.get('poster_path')}" if result.get('poster_path') else None,
                    'tmdb_rating': result.get('vote_average'),
                    'tmdb_votes': result.get('vote_count'),
                }
                films.append(film_data)
            
            cache.set(cache_key, films, 300)
            return films
            
        except Exception as e:
            logger.error(f"Error searching films: {str(e)}")
            return []