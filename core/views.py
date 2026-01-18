import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.cache import cache
from django.views.decorators.http import require_http_methods

from .services.film_aggregator import FilmAggregator

logger = logging.getLogger(__name__)


def home(request):
    """Главная страница с кнопками поиска."""
    return render(request, 'core/home.html')


def film_search(request):
    """Поиск фильмов - показывает результаты из TMDB."""
    query = request.GET.get('q', '').strip()
    year = request.GET.get('year', '').strip()
    
    films = []
    
    if query:
        try:
            aggregator = FilmAggregator()
            search_year = int(year) if year and year.isdigit() else None
            films = aggregator.search_films(query, search_year)
            
            if not films:
                messages.info(request, 'Фильмы не найдены')
                
        except Exception as e:
            logger.error(f"Error in film search: {str(e)}")
            messages.error(request, f'Ошибка при поиске: {str(e)}')
    
    context = {
        'query': query,
        'year': year,
        'films': films,
    }
    
    return render(request, 'core/film_search.html', context)


def film_detail(request, tmdb_id):
    """Страница фильма со всеми рейтингами в реальном времени."""
    try:
        cache_key = f'film_full_data_{tmdb_id}'
        cache.delete(cache_key)
        
        aggregator = FilmAggregator()
        film_data = aggregator.get_film_data(tmdb_id)
        
        if not film_data:
            messages.error(request, 'Фильм не найден')
            return redirect('film_search')
        
        ratings_list = []
        for source, rating in film_data.get('ratings', {}).items():
            ratings_list.append({
                'source': rating['source'],
                'value': rating['value'],
                'max_value': rating['max_value'],
                'normalized_value': rating.get('normalized_value'),
                'votes_count': rating.get('votes')
            })
        
        source_order = ['tmdb', 'imdb', 'kinopoisk', 'rotten_tomatoes', 'metacritic']
        ratings_list.sort(key=lambda x: source_order.index(x['source'].lower()) 
                         if x['source'].lower() in source_order else 999)
        
        context = {
            'film': {
                'tmdb_id': film_data['tmdb_id'],
                'title': film_data['title'],
                'original_title': film_data['original_title'],
                'year': film_data['year'],
                'description': film_data['description'],
                'poster_url': film_data['poster_url'],
                'runtime': film_data.get('runtime'),
                'genres': film_data.get('genres', []),
                'countries': film_data.get('countries', []),
                'average_rating': film_data.get('average_rating'),
                'ratings_count': film_data.get('ratings_count', 0),
            },
            'ratings': ratings_list,
            'directors': film_data.get('directors', []),
            'actors': film_data.get('actors', []),
        }
        
        return render(request, 'core/film_detail.html', context)
        
    except Exception as e:
        logger.error(f"Error in film detail for TMDB ID {tmdb_id}: {str(e)}")
        messages.error(request, f'Ошибка при загрузке данных фильма: {str(e)}')
        return redirect('film_search')


def force_refresh(request, tmdb_id):
    """Принудительное обновление данных фильма."""
    cache_key = f'film_full_data_{tmdb_id}'
    cache.delete(cache_key)
    
    messages.success(request, 'Данные фильма обновлены')
    return redirect('film_detail', tmdb_id=tmdb_id)