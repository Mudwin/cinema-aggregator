import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cinema_aggregator.settings')
django.setup()

from core.services import TMDBService

# Тестируем TMDB ID для Fargo
tmdb_service = TMDBService()

# ID для проверки
test_ids = [
    (275, "Фарго", "Fargo", 1996),
    (680, "Криминальное чтиво", "Pulp Fiction", 1994),
]

for tmdb_id, expected_ru, expected_en, expected_year in test_ids:
    print(f"\nПроверка TMDB ID: {tmdb_id}")
    print(f"Ожидается: {expected_ru} / {expected_en} ({expected_year})")
    
    try:
        data = tmdb_service.get_movie_details(tmdb_id, language='ru-RU')
        print(f"Получено: {data.get('title')} / {data.get('original_title')} ({data.get('release_date')})")
        print(f"IMDb ID: {data.get('imdb_id')}")
        
        # Проверяем соответствие
        if data.get('title') == expected_ru and data.get('original_title') == expected_en:
            print("✓ Данные корректны")
        else:
            print("✗ Данные не соответствуют ожиданиям!")
            
    except Exception as e:
        print(f"Ошибка: {e}")