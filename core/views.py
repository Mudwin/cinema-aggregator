from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.contrib import messages
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page
from django.core.cache import cache

from .models import Film, Person, Rating
from .services import TMDBService, OMDbService, KinopoiskService, RatingCalculator
from .tasks import update_film_ratings


def home(request):
    """Главная страница с кнопками поиска."""
    return render(request, 'core/home.html')


def film_search(request):
    """Страница поиска фильмов - показывает результаты из TMDB без сохранения в БД."""
    query = request.GET.get('q', '').strip()
    year = request.GET.get('year', '').strip()
    
    films = []
    search_performed = False
    
    if query:
        search_performed = True
        
        cache_key = f'search_{query}_{year}'
        cached_results = cache.get(cache_key)
        
        if cached_results:
            films = cached_results
        else:
            try:
                tmdb_service = TMDBService()
                search_results = tmdb_service.search_movies(
                    query=query,
                    year=int(year) if year and year.isdigit() else None,
                    page=int(request.GET.get('page', 1))
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
                        'can_view': True  
                    }
                    
                    existing = Film.objects.filter(tmdb_id=result.get('id')).first()
                    if existing:
                        film_data['in_database'] = True
                        film_data['db_film_id'] = existing.id
                        film_data['db_rating'] = existing.composite_rating
                    else:
                        film_data['in_database'] = False
                    
                    films.append(film_data)
                
                cache.set(cache_key, films, 600)
                    
            except Exception as e:
                messages.error(request, f'Ошибка при поиске: {str(e)}')
    
    context = {
        'query': query,
        'year': year,
        'films': films,
        'search_performed': search_performed,
    }
    
    return render(request, 'core/film_search.html', context)


def film_search_external(request):
    """Альтернативный поиск - всегда показывает внешние результаты."""
    return film_search(request)


def film_preview(request, tmdb_id):
    """Просмотр информации о фильме без сохранения в базу данных."""
    try:
        tmdb_service = TMDBService()
        
        movie_data = tmdb_service.get_movie_details(
            tmdb_id,
            append_to_response='credits',
            language='ru-RU'
        )
        
        if not movie_data:
            messages.error(request, 'Не удалось получить данные фильма')
            return redirect('film_search')
        
        existing_film = Film.objects.filter(tmdb_id=tmdb_id).first()
        if existing_film:
            return redirect('film_detail', film_id=existing_film.id)
        
        release_date = movie_data.get('release_date', '')
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
        
        film_info = {
            'tmdb_id': tmdb_id,
            'title': movie_data.get('title', ''),
            'original_title': movie_data.get('original_title', ''),
            'year': year,
            'description': movie_data.get('overview', ''),
            'poster_url': f"https://image.tmdb.org/t/p/original{movie_data.get('poster_path', '')}" if movie_data.get('poster_path') else None,
            'imdb_id': movie_data.get('imdb_id', ''),
            'runtime': movie_data.get('runtime'),
            'genres': [genre['name'] for genre in movie_data.get('genres', [])],
            'countries': [country['name'] for country in movie_data.get('production_countries', [])],
            'tmdb_rating': movie_data.get('vote_average'),
            'tmdb_votes': movie_data.get('vote_count'),
        }
        
        ratings = {}
        if film_info['imdb_id']:
            try:
                omdb_service = OMDbService()
                omdb_ratings = omdb_service.get_movie_ratings(film_info['imdb_id'])
                ratings.update(omdb_ratings)
            except Exception as e:
                print(f"Error getting OMDb ratings: {e}")
        
        credits = movie_data.get('credits', {})
        
        directors = []
        for person in credits.get('crew', []):
            if person.get('job') == 'Director':
                directors.append({
                    'name': person.get('name', ''),
                    'photo_url': f"https://image.tmdb.org/t/p/w185{person.get('profile_path')}" if person.get('profile_path') else None,
                })
        
        actors = []
        for person in credits.get('cast', [])[:10]:
            actors.append({
                'name': person.get('name', ''),
                'character': person.get('character', ''),
                'photo_url': f"https://image.tmdb.org/t/p/w185{person.get('profile_path')}" if person.get('profile_path') else None,
            })
        
        context = {
            'film': film_info,
            'ratings': ratings,
            'directors': directors[:3],  
            'actors': actors,  
            'is_preview': True,  
        }
        
        return render(request, 'core/film_preview.html', context)
        
    except Exception as e:
        messages.error(request, f'Ошибка при получении данных фильма: {str(e)}')
        return redirect('film_search')


def film_detail(request, film_id):
    """Детальная страница фильма из базы данных."""
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
    
    context = {
        'film': film,
        'ratings': ratings,
        'actors': actors,
        'directors': directors,
        'is_preview': False,
    }
    
    return render(request, 'core/film_detail.html', context)


@require_http_methods(["POST"])
def film_import(request):
    """Импорт фильма из TMDB в нашу базу."""
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
        
        tmdb_service = TMDBService()
        movie_data = tmdb_service.get_movie_details(
            int(tmdb_id),
            append_to_response='credits',
            language='ru-RU'
        )
        
        if not movie_data or 'id' not in movie_data:
            messages.error(request, 'Не удалось получить данные фильма из TMDB')
            return redirect('film_search')
        
        release_date = movie_data.get('release_date', '')
        year_from_release = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
        
        imdb_id = movie_data.get('imdb_id')
        
        if imdb_id and Film.objects.filter(imdb_id=imdb_id).exists():
            film = Film.objects.create(
                tmdb_id=tmdb_id,
                title=movie_data.get('title', ''),
                original_title=movie_data.get('original_title', ''),
                year=year_from_release,
                description=movie_data.get('overview', ''),
                poster_url=f"https://image.tmdb.org/t/p/original{movie_data.get('poster_path', '')}" if movie_data.get('poster_path') else None,
            )
            messages.warning(request, f'Фильм "{film.title}" импортирован без IMDb ID (уже используется другим фильмом)')
        else:
            film = Film.objects.create(
                tmdb_id=tmdb_id,
                title=movie_data.get('title', ''),
                original_title=movie_data.get('original_title', ''),
                year=year_from_release,
                description=movie_data.get('overview', ''),
                poster_url=f"https://image.tmdb.org/t/p/original{movie_data.get('poster_path', '')}" if movie_data.get('poster_path') else None,
                imdb_id=imdb_id
            )
            messages.success(request, f'Фильм "{film.title}" успешно импортирован!')
        
        credits = movie_data.get('credits', {})
        
        for person in credits.get('crew', []):
            if person.get('job') == 'Director':
                person_id = person.get('id')
                if person_id:
                    person_obj, _ = Person.objects.get_or_create(
                        tmdb_id=person_id,
                        defaults={
                            'name': person.get('name', ''),
                            'original_name': person.get('original_name', person.get('name', '')),
                            'profession': Person.ProfessionChoices.DIRECTOR
                        }
                    )
                    
                    from .models import FilmPersonRole
                    FilmPersonRole.objects.get_or_create(
                        film=film,
                        person=person_obj,
                        role=FilmPersonRole.RoleChoices.DIRECTOR
                    )
        
        for i, actor in enumerate(credits.get('cast', [])[:10]):
            person_id = actor.get('id')
            if person_id:
                person_obj, _ = Person.objects.get_or_create(
                    tmdb_id=person_id,
                    defaults={
                        'name': actor.get('name', ''),
                        'original_name': actor.get('original_name', actor.get('name', '')),
                        'profession': Person.ProfessionChoices.ACTOR
                    }
                )
                
                from .models import FilmPersonRole
                FilmPersonRole.objects.get_or_create(
                    film=film,
                    person=person_obj,
                    role=FilmPersonRole.RoleChoices.ACTOR,
                    defaults={
                        'character_name': actor.get('character', ''),
                        'order': i
                    }
                )
        
        update_film_ratings.delay(film.id)
        messages.info(request, 'Рейтинги загружаются...')
        
        return redirect('film_detail', film_id=film.id)
        
    except Exception as e:
        messages.error(request, f'Ошибка при импорте фильма: {str(e)}')
        
        redirect_url = f'/films/search/?q={query}'
        if year:
            redirect_url += f'&year={year}'
        return redirect(redirect_url)


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