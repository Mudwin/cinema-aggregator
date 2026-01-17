from django.core.management.base import BaseCommand
from core.services.search_service import SearchService


class Command(BaseCommand):
    help = 'Быстрый импорт фильма для тестирования'

    def add_arguments(self, parser):
        parser.add_argument('tmdb_id', type=int, help='TMDB ID фильма')

    def handle(self, *args, **options):
        tmdb_id = options['tmdb_id']
        
        self.stdout.write(f'Быстрый импорт фильма с TMDB ID: {tmdb_id}')
        
        search_service = SearchService()
        
        try:
            film, created = search_service.search_and_import_film(tmdb_id)
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'Фильм создан: {film.title} (ID: {film.id})'))
            else:
                self.stdout.write(self.style.WARNING(f'Фильм уже существует: {film.title} (ID: {film.id})'))
            
            self.stdout.write('\nРейтинги:')
            for rating in film.ratings.all():
                self.stdout.write(f'  - {rating.get_source_display()}: {rating.value}/{rating.max_value}')
            
            if film.composite_rating:
                self.stdout.write(f'\nКомпозитный рейтинг: {film.composite_rating}')
            
            self.stdout.write(f'\nURL для просмотра: http://127.0.0.1:8000/films/{film.id}/')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка: {str(e)}'))