import logging
from typing import Dict, List, Optional, Tuple
from django.core.cache import cache

from .tmdb_service import TMDBService
from .omdb_service import OMDbService
from .kinopoisk_service import KinopoiskService

logger = logging.getLogger(__name__)


class MovieService:
    """
    Основной сервис для работы с фильмами, использующий Kinopoisk как основной источник.
    """
    
    def __init__(self):
        self.tmdb_service = TMDBService()
        self.omdb_service = OMDbService()
        self.kinopoisk_service = KinopoiskService()
    
    def search_movies(self, query: str, year: Optional[int] = None) -> List[Dict]:
        """
        Поиск фильмов через Kinopoisk API.
        """
        try:
            cache_key = f'kp_search_{query}_{year}'
            cached_results = cache.get(cache_key)
            if cached_results:
                return cached_results
            
            search_results = self.kinopoisk_service.search_movies(
                query=query,
                year=year,
                page=1
            )
            
            films = []
            for item in search_results.get('items', [])[:20]:
                if not item.get('kinopoiskId'):
                    continue
                
                kp_details = self.kinopoisk_service.get_movie_details(item['kinopoiskId'])
                
                film = {
                    'kinopoisk_id': item['kinopoiskId'],
                    'title': item.get('nameRu') or item.get('nameOriginal') or item.get('nameEn', ''),
                    'original_title': item.get('nameOriginal') or item.get('nameEn') or item.get('nameRu', ''),
                    'year': item.get('year'),
                    'description': kp_details.get('description', ''),
                    'poster_url': item.get('posterUrl'),
                    'poster_url_preview': item.get('posterUrlPreview'),
                    'imdb_id': item.get('imdbId', ''),
                    'genres': [genre['genre'] for genre in item.get('genres', [])],
                    'countries': [country['country'] for country in item.get('countries', [])],
                    'rating_kinopoisk': item.get('ratingKinopoisk'),
                    'rating_imdb': item.get('ratingImdb'),
                    'type': item.get('type', 'FILM'),
                }
                
                tmdb_id = self._find_tmdb_id(film['title'], film['original_title'], film['year'])
                if tmdb_id:
                    film['tmdb_id'] = tmdb_id
                
                films.append(film)
            
            cache.set(cache_key, films, 300)
            return films
            
        except Exception as e:
            logger.error(f"Error searching movies via Kinopoisk: {str(e)}")
            return []
    
    def _find_tmdb_id(self, title: str, original_title: str, year: int) -> Optional[int]:
        """
        Поиск TMDB ID по названию фильма.
        """
        try:
            search_results = self.tmdb_service.search_movies(
                query=title,
                year=year,
                page=1,
                language='ru-RU'
            )
            
            if search_results.get('results'):
                for result in search_results['results']:
                    if result.get('title') == title or result.get('original_title') == original_title:
                        return result.get('id')
            
            if original_title and original_title != title:
                search_results = self.tmdb_service.search_movies(
                    query=original_title,
                    year=year,
                    page=1,
                    language='en-US'
                )
                
                if search_results.get('results'):
                    for result in search_results['results']:
                        if result.get('title') == original_title or result.get('original_title') == original_title:
                            return result.get('id')
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding TMDB ID for {title}: {str(e)}")
            return None
    
    def get_movie_data(self, kinopoisk_id: int) -> Optional[Dict]:
        """
        Получение полных данных о фильме по Kinopoisk ID.
        """
        try:
            cache_key = f'movie_full_data_{kinopoisk_id}'
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
            
            kp_details = self.kinopoisk_service.get_movie_details(kinopoisk_id)
            
            if not kp_details:
                logger.error(f"No data from Kinopoisk for ID {kinopoisk_id}")
                return None
            
            film_data = {
                'kinopoisk_id': kinopoisk_id,
                'title': kp_details.get('nameRu') or kp_details.get('nameOriginal') or kp_details.get('nameEn', ''),
                'original_title': kp_details.get('nameOriginal') or kp_details.get('nameEn') or kp_details.get('nameRu', ''),
                'year': kp_details.get('year'),
                'description': kp_details.get('description', ''),
                'poster_url': kp_details.get('posterUrl'),
                'imdb_id': kp_details.get('imdbId', ''),
                'runtime': kp_details.get('filmLength'),
                'genres': [genre['genre'] for genre in kp_details.get('genres', [])],
                'countries': [country['country'] for country in kp_details.get('countries', [])],
                'rating_kinopoisk': kp_details.get('ratingKinopoisk'),
                'rating_imdb': kp_details.get('ratingImdb'),
                'rating_film_critics': kp_details.get('ratingFilmCritics'),
            }
            
            ratings = {}
            
            kp_rating = kp_details.get('ratingKinopoisk')
            if kp_rating:
                ratings['kinopoisk'] = {
                    'value': kp_rating,
                    'max_value': 10,
                    'votes': kp_details.get('ratingKinopoiskVoteCount', 0)
                }
            
            imdb_rating = kp_details.get('ratingImdb')
            if imdb_rating:
                ratings['imdb'] = {
                    'value': imdb_rating,
                    'max_value': 10,
                    'votes': kp_details.get('ratingImdbVoteCount', 0)
                }
            
            if film_data['imdb_id']:
                try:
                    omdb_ratings = self.omdb_service.get_movie_ratings(film_data['imdb_id'])
                    ratings.update(omdb_ratings)
                except Exception as e:
                    logger.error(f"Error getting OMDb ratings: {str(e)}")
            
            tmdb_id = self._find_tmdb_id(film_data['title'], film_data['original_title'], film_data['year'])
            
            if tmdb_id:
                try:
                    tmdb_data = self.tmdb_service.get_movie_details(
                        tmdb_id,
                        append_to_response='credits',
                        language='ru-RU'
                    )
                    
                    if tmdb_data and tmdb_data.get('id') == tmdb_id:
                        film_data['tmdb_id'] = tmdb_id
                        
                        # Режиссеры
                        directors = []
                        for person in tmdb_data.get('credits', {}).get('crew', []):
                            if person.get('job') == 'Director':
                                profile_path = person.get('profile_path', '')
                                directors.append({
                                    'name': person.get('name', ''),
                                    'photo_url': f"https://image.tmdb.org/t/p/w185{profile_path}" if profile_path else None,
                                })
                        film_data['directors'] = directors[:3]
                        
                        # Актеры
                        actors = []
                        for person in tmdb_data.get('credits', {}).get('cast', [])[:10]:
                            profile_path = person.get('profile_path', '')
                            actors.append({
                                'name': person.get('name', ''),
                                'character': person.get('character', ''),
                                'photo_url': f"https://image.tmdb.org/t/p/w185{profile_path}" if profile_path else None,
                            })
                        film_data['actors'] = actors
                        
                        # Дополнительная информация из TMDB
                        if not film_data.get('poster_url') and tmdb_data.get('poster_path'):
                            film_data['poster_url'] = f"https://image.tmdb.org/t/p/original{tmdb_data['poster_path']}"
                        
                        if not film_data.get('description') and tmdb_data.get('overview'):
                            film_data['description'] = tmdb_data.get('overview')
                        
                        film_data['tmdb_rating'] = tmdb_data.get('vote_average')
                        film_data['tmdb_votes'] = tmdb_data.get('vote_count')
                    
                except Exception as e:
                    logger.error(f"Error getting TMDB data: {str(e)}")
            
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
            
            film_data['ratings'] = ratings
            
            cache.set(cache_key, film_data, 3600)
            return film_data
            
        except Exception as e:
            logger.error(f"Error getting movie data for Kinopoisk ID {kinopoisk_id}: {str(e)}")
            return None