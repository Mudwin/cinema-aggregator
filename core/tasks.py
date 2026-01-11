import logging
from datetime import timedelta
from typing import List, Optional

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import Film, Person, Rating
from .services import TMDBService, OMDbService, KinopoiskService, RatingCalculator
from .services.base_api import APIRateLimitError, APIRequestError

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(APIRateLimitError, APIRequestError),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    default_retry_delay=60
)
def update_film_ratings(self, film_id: int) -> dict:
    """
    Задача для обновления рейтингов фильма из различных источников.
    """
    try:
        film = Film.objects.get(id=film_id)
    except Film.DoesNotExist:
        logger.error(f"Film with id {film_id} not found")
        return {'status': 'error', 'message': f'Film with id {film_id} not found'}
    
    logger.info(f"Starting update ratings for film: {film.title} (ID: {film_id})")
    
    from ..services import TMDBService, OMDbService, KinopoiskService, RatingCalculator
    
    tmdb_service = TMDBService()
    omdb_service = OMDbService()
    kinopoisk_service = KinopoiskService()
    
    stats = {
        'film_id': film_id,
        'film_title': film.title,
        'ratings_updated': 0,
        'ratings_created': 0,
        'sources': []
    }
    
    try:
        if film.imdb_id:
            try:
                omdb_ratings = omdb_service.get_movie_ratings(film.imdb_id)
                
                for source_name, rating_data in omdb_ratings.items():
                    source_mapping = {
                        'imdb': Rating.SourceChoices.IMDB,
                        'rotten_tomatoes': Rating.SourceChoices.ROTTEN_TOMATOES,
                        'metacritic': Rating.SourceChoices.METACRITIC
                    }
                    
                    if source_name in source_mapping:
                        source = source_mapping[source_name]
                        rating, created = Rating.objects.update_or_create(
                            film=film,
                            source=source,
                            defaults={
                                'value': rating_data['value'],
                                'max_value': rating_data['max_value'],
                                'votes_count': rating_data.get('votes', None)
                            }
                        )
                        
                        if created:
                            stats['ratings_created'] += 1
                        else:
                            stats['ratings_updated'] += 1
                        
                        stats['sources'].append(source)
                        logger.debug(f"Updated {source} rating for {film.title}: {rating_data['value']}")
            except Exception as e:
                logger.error(f"Error updating OMDb ratings for {film.title}: {str(e)}")
        
        try:
            kinopoisk_movie = None
            
            if film.imdb_id:
                kinopoisk_movie = kinopoisk_service.get_movie_by_imdb_id(
                    film.imdb_id, 
                    film_title=film.title,
                    year=film.year
                )
            
            if not kinopoisk_movie and film.title:
                search_results = kinopoisk_service.search_movies(
                    film.title, 
                    year=film.year,
                    page=1
                )
                if "items" in search_results and search_results["items"]:
                    kinopoisk_movie = search_results["items"][0]
            
            if kinopoisk_movie:
                kp_ratings = kinopoisk_service.get_movie_rating(kinopoisk_movie)
                
                if 'kinopoisk' in kp_ratings:
                    rating_data = kp_ratings['kinopoisk']
                    rating, created = Rating.objects.update_or_create(
                        film=film,
                        source=Rating.SourceChoices.KINOPOISK,
                        defaults={
                            'value': rating_data['value'],
                            'max_value': rating_data['max_value'],
                            'votes_count': rating_data.get('votes', 0)
                        }
                    )
                    
                    if created:
                        stats['ratings_created'] += 1
                    else:
                        stats['ratings_updated'] += 1
                    
                    stats['sources'].append(Rating.SourceChoices.KINOPOISK)
                    logger.debug(f"Updated Kinopoisk rating for {film.title}: {rating_data['value']}")
                    
                if 'imdb' in kp_ratings and film.imdb_id:
                    rating_data = kp_ratings['imdb']
                    rating, created = Rating.objects.update_or_create(
                        film=film,
                        source=Rating.SourceChoices.IMDB,
                        defaults={
                            'value': rating_data['value'],
                            'max_value': rating_data['max_value'],
                            'votes_count': rating_data.get('votes', 0)
                        }
                    )
                    
                    if created:
                        stats['ratings_created'] += 1
                    else:
                        stats['ratings_updated'] += 1
                        
        except Exception as e:
            logger.error(f"Error updating Kinopoisk ratings for {film.title}: {str(e)}")
        
        composite_rating = RatingCalculator.calculate_composite_rating(film)
        if composite_rating:
            film.composite_rating = composite_rating
            film.save(update_fields=['composite_rating'])
            logger.info(f"Updated composite rating for {film.title}: {composite_rating}")
            stats['composite_rating'] = float(composite_rating)
        
        stats['status'] = 'success'
        logger.info(f"Successfully updated ratings for {film.title}. "
                   f"Created: {stats['ratings_created']}, Updated: {stats['ratings_updated']}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to update ratings for film {film_id}: {str(e)}")
        self.retry(exc=e)


@shared_task(
    bind=True,
    autoretry_for=(APIRateLimitError, APIRequestError),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    default_retry_delay=60
)
def fetch_film_data(self, tmdb_id: int, update_existing: bool = False) -> dict:
    """
    Задача для получения данных о фильме из TMDB и создания записи в базе.
    
    Args:
        tmdb_id (int): ID фильма в TMDB
        update_existing (bool): Обновить ли существующую запись
    
    Returns:
        dict: Информация о созданном/обновленном фильме
    """
    try:
        film = Film.objects.filter(tmdb_id=tmdb_id).first()
        
        if film and not update_existing:
            logger.info(f"Film with TMDB ID {tmdb_id} already exists")
            return {
                'status': 'exists',
                'film_id': film.id,
                'film_title': film.title
            }
    
        tmdb_service = TMDBService()
        
        movie_data = tmdb_service.get_movie_details(
            tmdb_id,
            append_to_response='credits',
            language='ru-RU'
        )
        
        if not movie_data:
            logger.error(f"No data received for TMDB ID {tmdb_id}")
            return {'status': 'error', 'message': 'No data received from TMDB'}
        
        release_date = movie_data.get('release_date', '')
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
        
        with transaction.atomic():
            film, created = Film.objects.update_or_create(
                tmdb_id=tmdb_id,
                defaults={
                    'title': movie_data.get('title', ''),
                    'original_title': movie_data.get('original_title', ''),
                    'year': year,
                    'description': movie_data.get('overview', ''),
                    'poster_url': f"https://image.tmdb.org/t/p/original{movie_data.get('poster_path', '')}" if movie_data.get('poster_path') else None,
                    'imdb_id': movie_data.get('imdb_id', '')
                }
            )
            
            logger.info(f"{'Created' if created else 'Updated'} film: {film.title}")
            
            credits = movie_data.get('credits', {})
            
            crew = credits.get('crew', [])
            directors = [person for person in crew if person.get('job') == 'Director']
            
            for director_data in directors:
                person_id = director_data.get('id')
                if person_id:
                    person, _ = Person.objects.get_or_create(
                        tmdb_id=person_id,
                        defaults={
                            'name': director_data.get('name', ''),
                            'original_name': director_data.get('original_name', ''),
                            'profession': Person.ProfessionChoices.DIRECTOR
                        }
                    )
                    
                    from .models import FilmPersonRole
                    FilmPersonRole.objects.get_or_create(
                        film=film,
                        person=person,
                        role=FilmPersonRole.RoleChoices.DIRECTOR
                    )
            
            cast = credits.get('cast', [])[:10]  
            
            for i, actor_data in enumerate(cast):
                person_id = actor_data.get('id')
                if person_id:
                    person, _ = Person.objects.get_or_create(
                        tmdb_id=person_id,
                        defaults={
                            'name': actor_data.get('name', ''),
                            'original_name': actor_data.get('original_name', ''),
                            'profession': Person.ProfessionChoices.ACTOR
                        }
                    )
                    
                    from .models import FilmPersonRole
                    FilmPersonRole.objects.get_or_create(
                        film=film,
                        person=person,
                        role=FilmPersonRole.RoleChoices.ACTOR,
                        defaults={
                            'character_name': actor_data.get('character', ''),
                            'order': actor_data.get('order', i)
                        }
                    )
        
        update_film_ratings.delay(film.id)
        
        update_person_data_for_film.delay(film.id)
        
        return {
            'status': 'success',
            'created': created,
            'film_id': film.id,
            'film_title': film.title,
            'year': film.year,
            'actors_count': len(cast),
            'directors_count': len(directors)
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch film data for TMDB ID {tmdb_id}: {str(e)}")
        self.retry(exc=e)


@shared_task(
    bind=True,
    autoretry_for=(APIRateLimitError,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    default_retry_delay=60
)
def update_person_data(self, person_id: int) -> dict:
    """
    Задача для обновления данных о персоне из TMDB.
    
    Args:
        person_id (int): ID персоны в нашей базе данных
    
    Returns:
        dict: Статистика обновления
    """
    try:
        person = Person.objects.get(id=person_id)
    except Person.DoesNotExist:
        logger.error(f"Person with id {person_id} not found")
        return {'status': 'error', 'message': f'Person with id {person_id} not found'}
    
    logger.info(f"Starting update for person: {person.name} (ID: {person_id})")
    
    tmdb_service = TMDBService()
    
    try:
        person_data = tmdb_service.get_person_details(person.tmdb_id, language='ru-RU')
        
        if not person_data:
            logger.error(f"No data received for person TMDB ID {person.tmdb_id}")
            return {'status': 'error', 'message': 'No data received from TMDB'}
        
        updates = {}
        
        if 'biography' in person_data and person_data['biography']:
            updates['biography'] = person_data['biography']
        
        if 'birthday' in person_data and person_data['birthday']:
            updates['birth_date'] = person_data['birthday']
        
        if 'deathday' in person_data and person_data['deathday']:
            updates['death_date'] = person_data['deathday']
        
        if 'profile_path' in person_data and person_data['profile_path']:
            updates['photo_url'] = f"https://image.tmdb.org/t/p/original{person_data['profile_path']}"
        
        if 'name' in person_data and person_data['name']:
            updates['name'] = person_data['name']
        
        if 'original_name' in person_data and person_data['original_name']:
            updates['original_name'] = person_data['original_name']
        
        if updates:
            for field, value in updates.items():
                setattr(person, field, value)
            person.save()
            logger.info(f"Updated person {person.name} with {len(updates)} fields")
        else:
            logger.info(f"No updates needed for person {person.name}")
        
        movie_credits = tmdb_service.get_person_movie_credits(person.tmdb_id, language='ru-RU')
        
        # Будущая логика обновления фильмографии
        
        return {
            'status': 'success',
            'person_id': person_id,
            'person_name': person.name,
            'updates_applied': len(updates),
            'updated_fields': list(updates.keys())
        }
        
    except Exception as e:
        logger.error(f"Failed to update person data for {person_id}: {str(e)}")
        self.retry(exc=e)


@shared_task(
    bind=True,
    default_retry_delay=30
)
def calculate_composite_ratings(self, film_ids: Optional[List[int]] = None) -> dict:
    """
    Задача для пересчета комплексных рейтингов для фильмов.
    Если film_ids не указан, пересчитывает для всех фильмов.
    
    Args:
        film_ids (List[int], optional): Список ID фильмов для пересчета
    
    Returns:
        dict: Статистика пересчета
    """
    try:
        if film_ids:
            films = Film.objects.filter(id__in=film_ids)
        else:
            films = Film.objects.all()
        
        total_films = films.count()
        updated_films = 0
        failed_films = 0
        
        logger.info(f"Starting composite rating calculation for {total_films} films")
        
        for film in films:
            try:
                composite_rating = RatingCalculator.calculate_composite_rating(film)
                
                if composite_rating:
                    film.composite_rating = composite_rating
                    film.save(update_fields=['composite_rating'])
                    updated_films += 1
                    logger.debug(f"Updated composite rating for {film.title}: {composite_rating}")
                else:
                    if film.composite_rating is not None:
                        film.composite_rating = None
                        film.save(update_fields=['composite_rating'])
                        logger.debug(f"Cleared composite rating for {film.title} (no ratings)")
                        
            except Exception as e:
                failed_films += 1
                logger.error(f"Failed to calculate composite rating for film {film.id}: {str(e)}")
        
        logger.info(f"Completed composite rating calculation. "
                   f"Updated: {updated_films}, Failed: {failed_films}, Total: {total_films}")
        
        return {
            'status': 'success',
            'total_films': total_films,
            'updated_films': updated_films,
            'failed_films': failed_films
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate composite ratings: {str(e)}")
        self.retry(exc=e)


@shared_task
def update_person_data_for_film(film_id: int) -> dict:
    """
    Вспомогательная задача для обновления данных всех персон фильма.
    
    Args:
        film_id (int): ID фильма
    
    Returns:
        dict: Статистика обновления
    """
    try:
        film = Film.objects.get(id=film_id)
    except Film.DoesNotExist:
        return {'status': 'error', 'message': f'Film with id {film_id} not found'}
    
    person_roles = film.film_roles.all()
    person_ids = person_roles.values_list('person_id', flat=True).distinct()
    
    total_persons = len(person_ids)
    updated_persons = 0
    
    logger.info(f"Updating data for {total_persons} persons from film {film.title}")
    
    for person_id in person_ids:
        try:
            update_person_data.delay(person_id)
            updated_persons += 1
        except Exception as e:
            logger.error(f"Failed to schedule update for person {person_id}: {str(e)}")
    
    return {
        'status': 'success',
        'film_id': film_id,
        'film_title': film.title,
        'total_persons': total_persons,
        'scheduled_updates': updated_persons
    }


@shared_task
def update_old_ratings(days_old: int = 7) -> dict:
    """
    Задача для обновления рейтингов фильмов, которые давно не обновлялись.
    
    Args:
        days_old (int): Обновлять рейтинги старше N дней
    
    Returns:
        dict: Статистика обновления
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        films_to_update = Film.objects.filter(
            ratings__last_updated__lt=cutoff_date
        ).distinct()
        
        total_films = films_to_update.count()
        
        logger.info(f"Found {total_films} films with ratings older than {days_old} days")
        
        updated_films = 0
        
        for film in films_to_update:
            try:
                update_film_ratings.delay(film.id)
                updated_films += 1
                logger.debug(f"Scheduled rating update for film {film.title}")
            except Exception as e:
                logger.error(f"Failed to schedule update for film {film.id}: {str(e)}")
        
        return {
            'status': 'success',
            'total_films': total_films,
            'scheduled_updates': updated_films
        }
        
    except Exception as e:
        logger.error(f"Failed to update old ratings: {str(e)}")
        return {'status': 'error', 'message': str(e)}
    

@shared_task
def update_popular_films_data(limit: int = 50) -> dict:
    """
    Задача для обновления данных популярных фильмов.
    Обновляет фильмы с самым высоким composite_rating.
    
    Args:
        limit (int): Количество фильмов для обновления
    
    Returns:
        dict: Статистика обновления
    """
    try:
        popular_films = Film.objects.exclude(
            composite_rating__isnull=True
        ).order_by('-composite_rating')[:limit]
        
        total_films = popular_films.count()
        updated_films = 0
        
        logger.info(f"Updating data for {total_films} popular films")
        
        for film in popular_films:
            try:
                update_film_ratings.delay(film.id)
                updated_films += 1
            except Exception as e:
                logger.error(f"Failed to schedule update for film {film.id}: {str(e)}")
        
        return {
            'status': 'success',
            'total_films': total_films,
            'scheduled_updates': updated_films
        }
        
    except Exception as e:
        logger.error(f"Failed to update popular films data: {str(e)}")
        return {'status': 'error', 'message': str(e)}


@shared_task
def cleanup_old_tasks(days_old: int = 30) -> dict:
    """
    Задача для очистки старых результатов задач.
    Удаляет результаты задач старше указанного количества дней.
    
    Args:
        days_old (int): Удалять результаты старше N дней
    
    Returns:
        dict: Статистика очистки
    """
    try:
        from celery.result import AsyncResult
        from django_celery_results.models import TaskResult
        from django.utils import timezone
        
        try:
            cutoff_date = timezone.now() - timezone.timedelta(days=days_old)
            deleted_count, _ = TaskResult.objects.filter(
                date_done__lt=cutoff_date
            ).delete()
            
            logger.info(f"Cleaned up {deleted_count} old task results")
            
            return {
                'status': 'success',
                'deleted_count': deleted_count,
                'days_old': days_old
            }
            
        except ImportError:
            logger.warning("django-celery-results not installed, skipping cleanup")
            return {
                'status': 'skipped',
                'message': 'django-celery-results not installed'
            }
        
    except Exception as e:
        logger.error(f"Failed to cleanup old tasks: {str(e)}")
        return {'status': 'error', 'message': str(e)}


@shared_task
def check_api_status() -> dict:
    """
    Задача для проверки статуса внешних API.
    
    Returns:
        dict: Статус всех API
    """
    from .services import TMDBService, OMDbService, KinopoiskService
    
    api_status = {}
    
    try:
        tmdb_service = TMDBService()
        tmdb_response = tmdb_service.search_movies("test", page=1)
        api_status['tmdb'] = {
            'status': 'ok' if 'results' in tmdb_response else 'error',
            'message': 'TMDB API is working' if 'results' in tmdb_response else 'TMDB API error'
        }
    except Exception as e:
        api_status['tmdb'] = {
            'status': 'error',
            'message': str(e)
        }
    
    try:
        omdb_service = OMDbService()
        omdb_response = omdb_service.search_movies("test", page=1)
        api_status['omdb'] = {
            'status': 'ok' if 'Search' in omdb_response else 'error',
            'message': 'OMDb API is working' if 'Search' in omdb_response else 'OMDb API error'
        }
    except Exception as e:
        api_status['omdb'] = {
            'status': 'error',
            'message': str(e)
        }
    
    try:
        kinopoisk_service = KinopoiskService()
        kinopoisk_response = kinopoisk_service.search_movies("test", page=1)
        api_status['kinopoisk'] = {
            'status': 'ok' if 'items' in kinopoisk_response else 'error',
            'message': 'Kinopoisk API is working' if 'items' in kinopoisk_response else 'Kinopoisk API error'
        }
    except Exception as e:
        api_status['kinopoisk'] = {
            'status': 'error',
            'message': str(e)
        }
    
    logger.info(f"API status check completed: {api_status}")
    
    return {
        'status': 'success',
        'api_status': api_status,
        'timestamp': timezone.now().isoformat()
    }

@shared_task(
    bind=True,
    autoretry_for=(APIRateLimitError, APIRequestError),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    default_retry_delay=30
)
def search_and_import_film(self, tmdb_id: int) -> dict:
    """
    Задача для поиска и импорта фильма.
    
    Args:
        tmdb_id (int): ID фильма в TMDB
    
    Returns:
        dict: Результат импорта
    """
    try:
        from .services.search_service import SearchService
        
        search_service = SearchService()
        film, created = search_service.search_and_import_film(tmdb_id)
        
        return {
            'status': 'success',
            'created': created,
            'film_id': film.id,
            'film_title': film.title,
            'tmdb_id': tmdb_id,
            'message': f'Фильм {"импортирован" if created else "уже существует"}: {film.title}'
        }
        
    except Exception as e:
        logger.error(f"Failed to search and import film {tmdb_id}: {str(e)}")
        self.retry(exc=e)


@shared_task(
    bind=True,
    autoretry_for=(APIRateLimitError,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 2},
    default_retry_delay=60
)
def batch_import_films(self, tmdb_ids: List[int]) -> dict:
    """
    Пакетный импорт фильмов.
    
    Args:
        tmdb_ids (List[int]): Список TMDB ID
    
    Returns:
        dict: Статистика импорта
    """
    try:
        from .services.search_service import SearchService
        
        search_service = SearchService()
        stats = search_service.batch_import_films(tmdb_ids)
        
        return {
            'status': 'success',
            'stats': stats
        }
        
    except Exception as e:
        logger.error(f"Failed to batch import films: {str(e)}")
        self.retry(exc=e)


@shared_task
def search_trending_films(limit: int = 20) -> dict:
    """
    Поиск и импорт популярных фильмов из TMDB.
    
    Args:
        limit (int): Количество фильмов для импорта
    
    Returns:
        dict: Результаты импорта
    """
    try:
        from .services import TMDBService
        
        tmdb_service = TMDBService()
        
        trending_data = tmdb_service.get("trending/movie/week", params={"language": "ru-RU"})
        
        if not trending_data or 'results' not in trending_data:
            return {'status': 'error', 'message': 'No trending data found'}
        
        trending_films = trending_data['results'][:limit]
        tmdb_ids = [film['id'] for film in trending_films]
        
        task = batch_import_films.delay(tmdb_ids)
        
        return {
            'status': 'started',
            'task_id': task.id,
            'total_films': len(tmdb_ids),
            'message': f'Импорт {len(tmdb_ids)} популярных фильмов начат'
        }
        
    except Exception as e:
        logger.error(f"Failed to search trending films: {str(e)}")
        return {'status': 'error', 'message': str(e)}