import logging
from django.shortcuts import render, redirect
from django.contrib import messages

from .services.movie_service import MovieService

logger = logging.getLogger(__name__)


def home(request):
    """Главная страница с кнопками поиска."""
    return render(request, 'core/home.html')


def film_search(request):
    """Поиск фильмов - показывает результаты из Kinopoisk."""
    query = request.GET.get('q', '').strip()
    year = request.GET.get('year', '').strip()
    
    films = []
    
    if query:
        try:
            service = MovieService()
            search_year = int(year) if year and year.isdigit() else None
            films = service.search_movies(query, search_year)
            
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


def film_detail(request, kinopoisk_id):
    """Страница фильма со всеми рейтингами."""
    try:
        service = MovieService()
        film_data = service.get_movie_data(kinopoisk_id)
        
        if not film_data:
            messages.error(request, 'Фильм не найден')
            return redirect('film_search')
        
        ratings_list = []
        for source_key, rating in film_data.get('ratings', {}).items():
            source_names = {
                'imdb': 'IMDb',
                'kinopoisk': 'Кинопоиск',
                'rotten_tomatoes': 'Rotten Tomatoes',
                'metacritic': 'Metacritic',
                'film_critics': 'Кинокритики',
            }
            
            source_name = source_names.get(source_key, source_key)
            
            ratings_list.append({
                'source': source_name,
                'value': rating['value'],
                'max_value': rating['max_value'],
                'normalized_value': rating.get('normalized_value'),
                'votes_count': rating.get('votes')
            })
        
        source_order = ['kinopoisk', 'imdb', 'rotten_tomatoes', 'metacritic', 'film_critics']
        ratings_list.sort(key=lambda x: (
            source_order.index(x['source'].lower()) 
            if x['source'].lower() in source_order 
            else 999
        ))
        
        context = {
            'film': film_data,
            'ratings': ratings_list,
            'directors': film_data.get('directors', []),
            'actors': film_data.get('actors', []),
        }
        
        return render(request, 'core/film_detail.html', context)
        
    except Exception as e:
        logger.error(f"Error in film detail for Kinopoisk ID {kinopoisk_id}: {str(e)}")
        messages.error(request, 'Ошибка при загрузке данных фильма')
        return redirect('film_search')


def force_refresh(request, kinopoisk_id):
    """Принудительное обновление данных фильма."""
    from django.core.cache import cache
    cache.delete(f'movie_full_data_{kinopoisk_id}')
    cache.delete(f'kp_search_*')  
    
    messages.success(request, 'Данные фильма будут обновлены при следующем просмотре')
    return redirect('film_detail', kinopoisk_id=kinopoisk_id)