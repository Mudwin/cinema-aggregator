from django.core.management.base import BaseCommand
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Очистка всего API кэша'
    
    def handle(self, *args, **options):
        keys_deleted = 0
        
        try:
            if hasattr(cache, 'keys'):
                all_keys = cache.keys('*')
                for key in all_keys:
                    if isinstance(key, str) and key.startswith('api_cache:'):
                        cache.delete(key)
                        keys_deleted += 1
                self.stdout.write(self.style.SUCCESS(f'Удалены {keys_deleted} ключей кэширования API'))
            else:
                cache.clear()
                self.stdout.write(self.style.SUCCESS('Очищен весь кэш'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка очистки кэша: {str(e)}'))
            cache.clear()