from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.cache import cache
from django.views.decorators.http import require_http_methods

import hashlib
import logging
from .models import Film, Person, Rating
from .services import TMDBService
from .tasks import fetch_film_data, update_film_ratings

logger = logging.getLogger(__name__)

def home(request):
    """Главная страница с кнопками поиска."""
    return render(request, 'core/home.html')


def film_search(request):
    """Страница поиска фильмов."""
    query = request.GET.get('q', '').strip()
    year = request.GET.get('year', '').strip()
    
    films = []
    external_films = []
    
    if query:
        cache_key = f'search_{query}_{year}'
        
        search_films = Film.objects.all()
        
        if query:
            search_films = search_films.filter(
                Q(title__icontains=query) | 
                Q(original_title__icontains=query)
            )
        
        if year and year.isdigit():
            search_films = search_films.filter(year=int(year))
        
        search_films = search_films.order_by('-composite_rating')
        
        if search_films.exists():
            films = search_films[:20]
        else:
            cached_external = cache.get(cache_key)
            
            if cached_external:
                external_films = cached_external
            else:
                try:
                    tmdb_service = TMDBService()
                    search_results = tmdb_service.search_movies(
                        query=query,
                        year=int(year) if year and year.isdigit() else None,
                        page=1
                    )
                    
                    for result in search_results.get('results', [])[:20]:
                        film_data = {
                            'tmdb_id': result.get('id'),
                            'title': result.get('title', ''),
                            'original_title': result.get('original_title', ''),
                            'year': result.get('release_date', '')[:4] if result.get('release_date') else None,
                            'description': result.get('overview', ''),
                            'poster_url': f"https://image.tmdb.org/t/p/w500{result.get('poster_path')}" if result.get('poster_path') else None,
                            'tmdb_rating': result.get('vote_average'),
                            'can_import': True
                        }
                        
                        external_films.append(film_data)
                    
                    cache.set(cache_key, external_films, 300)
                        
                except Exception as e:
                    messages.error(request, f'Ошибка при поиске во внешних источниках: {str(e)}')
    
    context = {
        'query': query,
        'year': year,
        'films': films,
        'external_films': external_films,
    }
    
    return render(request, 'core/film_search.html', context)


def film_search_external(request):
    """Поиск фильмов во внешних источниках (TMDB)."""
    query = request.GET.get('q', '').strip()
    year = request.GET.get('year', '').strip()
    
    external_films = []
    
    if query:
        try:
            tmdb_service = TMDBService()
            search_results = tmdb_service.search_movies(
                query=query,
                year=int(year) if year and year.isdigit() else None,
                page=1
            )
            
            for result in search_results.get('results', [])[:20]:
                film_data = {
                    'tmdb_id': result.get('id'),
                    'title': result.get('title', ''),
                    'original_title': result.get('original_title', ''),
                    'year': result.get('release_date', '')[:4] if result.get('release_date') else None,
                    'description': result.get('overview', ''),
                    'poster_url': f"https://image.tmdb.org/t/p/w500{result.get('poster_path')}" if result.get('poster_path') else None,
                    'tmdb_rating': result.get('vote_average'),
                    'can_import': True
                }
                
                existing = Film.objects.filter(tmdb_id=result.get('id')).first()
                if existing:
                    film_data['can_import'] = False
                    film_data['id'] = existing.id
                
                external_films.append(film_data)
                
        except Exception as e:
            messages.error(request, f'Ошибка при поиске во внешних источниках: {str(e)}')
    
    context = {
        'query': query,
        'year': year,
        'external_films': external_films,
        'search_performed': True,
    }
    
    return render(request, 'core/film_search.html', context)


@require_http_methods(["POST"])
def film_import(request):
    """Импорт фильма из TMDB (синхронная версия)."""
    tmdb_id = request.POST.get('tmdb_id')
    query = request.POST.get('query', '')
    year = request.POST.get('year', '')
    
    if not tmdb_id:
        messages.error(request, 'Не указан TMDB ID фильма')
        return redirect('film_search')
    
    try:
        existing_film = Film.objects.filter(tmdb_id=tmdb_id).first()
        if existing_film:
            messages.info(request, f'Фильм "{existing_film.title}" уже был импортирован ранее')
            return redirect('film_detail', film_id=existing_film.id)
        
        from django.core.cache import cache
        cache_keys_to_delete = [
            f'api_cache:{hashlib.md5(f"GET:https://api.themoviedb.org/3/movie/{tmdb_id}:{{\"language\":\"ru-RU\"}}".encode()).hexdigest()}',
            f'api_cache:{hashlib.md5(f"GET:https://api.themoviedb.org/3/movie/{tmdb_id}:{{\"language\":\"ru-RU\",\"append_to_response\":\"credits\"}}".encode()).hexdigest()}',
        ]
        for key in cache_keys_to_delete:
            cache.delete(key)
        
        tmdb_service = TMDBService()
        
        if hasattr(tmdb_service.session, 'cache'):
            tmdb_service.session.cache.clear()
        
        movie_data = tmdb_service.get_movie_details(
            int(tmdb_id),
            append_to_response='credits',
            language='ru-RU'
        )
        
        if not movie_data or 'id' not in movie_data:
            messages.error(request, 'Не удалось получить данные фильма из TMDB')
            return redirect('film_search')
        
        search_title = query.lower() if query else ''
        tmdb_title = movie_data.get('title', '').lower()
        tmdb_original_title = movie_data.get('original_title', '').lower()
        
        if search_title and (search_title not in tmdb_title and search_title not in tmdb_original_title):
            messages.warning(request, f'Внимание: получен фильм "{movie_data.get("title")}", а не "{query}"')
        
        release_date = movie_data.get('release_date', '')
        year_from_release = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
        
        film, created = Film.objects.update_or_create(
            tmdb_id=tmdb_id,
            defaults={
                'title': movie_data.get('title', ''),
                'original_title': movie_data.get('original_title', ''),
                'year': year_from_release,
                'description': movie_data.get('overview', ''),
                'poster_url': f"https://image.tmdb.org/t/p/original{movie_data.get('poster_path', '')}" if movie_data.get('poster_path') else None,
                'imdb_id': movie_data.get('imdb_id', '')
            }
        )
        
        if created:
            messages.success(request, f'Фильм "{film.title}" успешно импортирован!')
        else:
            messages.info(request, f'Фильм "{film.title}" обновлен')
        
        from ..tasks import update_film_ratings
        task = update_film_ratings.delay(film.id)
        messages.info(request, f'Рейтинги загружаются (задача #{task.id})...')
        
        return redirect('film_detail', film_id=film.id)
        
    except Exception as e:
        messages.error(request, f'Ошибка при импорте фильма: {str(e)}')
        logger.error(f"Error importing film {tmdb_id}: {str(e)}")
        
        redirect_url = f'/films/search/?q={query}'
        if year:
            redirect_url += f'&year={year}'
        return redirect(redirect_url)


def film_detail(request, film_id):
    """Детальная страница фильма."""
    film = get_object_or_404(Film, id=film_id)
    
    ratings = film.ratings.all()
    
    film_roles = film.film_roles.select_related('person')
    
    actors = []
    directors = []
    
    for role in film_roles:
        person_info = {
            'id': role.person.id,
            'name': role.person.name,
            'photo_url': role.person.photo_url,
            'role': role.get_role_display(),
            'character_name': role.character_name
        }
        
        if role.role == 'actor':
            actors.append(person_info)
        elif role.role == 'director':
            directors.append(person_info)
    
    similar_films = Film.objects.filter(
        year=film.year
    ).exclude(
        id=film.id
    ).filter(
        composite_rating__isnull=False
    ).order_by('-composite_rating')[:6]
    
    context = {
        'film': film,
        'ratings': ratings,
        'actors': actors,
        'directors': directors,
        'similar_films': similar_films,
    }
    
    return render(request, 'core/film_detail.html', context)


@require_http_methods(["POST"])
def update_film_ratings_view(request, film_id):
    """Обновление рейтингов фильма."""
    film = get_object_or_404(Film, id=film_id)
    
    try:
        task = update_film_ratings.delay(film.id)
        messages.success(request, f'Обновление рейтингов начато. Задача #{task.id}')
    except Exception as e:
        messages.error(request, f'Ошибка: {str(e)}')
    
    return redirect('film_detail', film_id=film_id)