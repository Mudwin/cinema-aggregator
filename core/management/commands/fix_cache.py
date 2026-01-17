import hashlib
import json
from django.core.management.base import BaseCommand
from django.core.cache import cache


class Command(BaseCommand):
    help = 'Исправление проблем с кэшем'

    def add_arguments(self, parser):
        parser.add_argument('--clear-tmdb', action='store_true', help='Очистить кэш TMDB')
        parser.add_argument('--clear-all', action='store_true', help='Очистить весь кэш')

    def handle(self, *args, **options):
        if options['clear_all']:
            cache.clear()
            self.stdout.write(self.style.SUCCESS('Весь кэш очищен'))
            return
        
        if options['clear_tmdb']:
            keys_to_delete = []
            
            cache.clear()
            
            self.stdout.write(self.style.SUCCESS('Кэш TMDB очищен'))