import logging
from django.shortcuts import render, redirect
from django.contrib import messages

from .services.movie_service import MovieService
from .services.person_service import PersonService

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
            logger.error(f"Ошибка при поиске: {str(e)}")
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
        logger.error(f"Ошибка при загрузке данных для Kinopoisk ID {kinopoisk_id}: {str(e)}")
        messages.error(request, 'Ошибка при загрузке данных фильма')
        return redirect('film_search')


def force_refresh(request, kinopoisk_id):
    """Принудительное обновление данных фильма."""
    from django.core.cache import cache
    cache.delete(f'movie_full_data_{kinopoisk_id}')
    cache.delete(f'kp_search_*')  
    
    messages.success(request, 'Данные фильма будут обновлены при следующем просмотре')
    return redirect('film_detail', kinopoisk_id=kinopoisk_id)

def person_detail(request, tmdb_id):
    """Страница персоны с фильмографией."""
    try:
        service = PersonService()
        person_data = service.get_person_data(int(tmdb_id))
        
        if not person_data:
            messages.error(request, 'Персона не найдена')
            return redirect('home')
        
        filmography = service.get_person_filmography_with_ratings(int(tmdb_id))
        
        actor_films = [f for f in filmography if f.get('role_type') == 'actor']
        crew_films = [f for f in filmography if f.get('role_type') != 'actor']
        
        actor_films.sort(key=lambda x: x.get('rating_kinopoisk') or x.get('vote_average') or 0, reverse=True)
        
        crew_by_job = {}
        for film in crew_films:
            job = film.get('role', 'Другое')
            if job not in crew_by_job:
                crew_by_job[job] = []
            crew_by_job[job].append(film)
        
        for job in crew_by_job:
            crew_by_job[job].sort(key=lambda x: x.get('year', 0) or 0, reverse=True)
        
        context = {
            'person': person_data,
            'actor_films': actor_films,
            'crew_by_job': crew_by_job,
            'film_count': person_data.get('film_count', 0),
            'actor_roles': person_data.get('actor_roles', 0),
            'crew_roles': person_data.get('crew_roles', 0),
        }
        
        return render(request, 'core/person_detail.html', context)
        
    except ValueError:
        messages.error(request, 'Неверный ID персоны')
        return redirect('home')
    except Exception as e:
        messages.error(request, 'Ошибка при загрузке данных персоны')
        return redirect('home')


def person_search(request):
    """Поиск персон по имени."""
    query = request.GET.get('q', '').strip()
    
    persons = []
    
    if query:
        try:
            service = PersonService()
            persons = service.search_person_by_name(query)
            
            if not persons:
                messages.info(request, 'Персоны не найдены')
                
        except Exception as e:
            logger.error(f"Ошибка при поиске: {str(e)}")
            messages.error(request, f'Ошибка при поиске: {str(e)}')
    
    context = {
        'query': query,
        'persons': persons,
    }
    
    return render(request, 'core/person_search.html', context)