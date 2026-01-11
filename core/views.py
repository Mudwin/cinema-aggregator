from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.contrib import messages
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods

from .models import Film, Person, Rating
from .services import TMDBService
from .tasks import fetch_film_data, update_film_ratings


def home(request):
    """Главная страница с кнопками поиска."""
    return render(request, 'core/home.html')


def film_search(request):
    """Страница поиска фильмов."""
    query = request.GET.get('q', '').strip()
    year = request.GET.get('year', '').strip()
    
    films = []
    external_search = False
    
    if query:
        search_films = Film.objects.all()
        
        if query:
            search_films = search_films.filter(
                Q(title__icontains=query) | 
                Q(original_title__icontains=query)
            )
        
        if year and year.isdigit():
            search_films = search_films.filter(year=int(year))
        
        search_films = search_films.order_by('-composite_rating')
        
        paginator = Paginator(search_films, 20)
        page_number = request.GET.get('page', 1)
        films = paginator.get_page(page_number)
        
        if search_films.count() < 3:
            external_search = True
    
    context = {
        'query': query,
        'year': year,
        'films': films,
        'external_search': external_search,
    }
    
    return render(request, 'core/film_search.html', context)


def film_search_external(request):
    """Поиск фильмов во внешних источниках (TMDB)."""
    query = request.GET.get('q', '').strip()
    year = request.GET.get('year', '').strip()
    
    films = []
    
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
                
                films.append(film_data)
                
        except Exception as e:
            messages.error(request, f'Ошибка при поиске во внешних источниках: {str(e)}')
    
    context = {
        'query': query,
        'year': year,
        'films': films,
        'external_search': True,
    }
    
    return render(request, 'core/film_search.html', context)


@require_http_methods(["POST"])
def film_import(request):
    """Импорт фильма из TMDB."""
    tmdb_id = request.POST.get('tmdb_id')
    
    if tmdb_id:
        try:
            task = fetch_film_data.delay(int(tmdb_id))
            messages.success(request, f'Импорт фильма начат. Задача #{task.id}')
        except Exception as e:
            messages.error(request, f'Ошибка при импорте: {str(e)}')
    
    return redirect('film_search')


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