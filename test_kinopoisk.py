# test_kinopoisk.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cinema_aggregator.settings')
django.setup()

from core.services import KinopoiskService

kinopoisk_service = KinopoiskService()

# Тест 1: Поиск по названию "Матрица"
print("Тест 1: Поиск 'Матрица' 1999")
results = kinopoisk_service.search_movies("Матрица", year=1999, page=1)
if results.get("items"):
    print(f"Найдено фильмов: {len(results['items'])}")
    for film in results["items"][:3]:
        print(f"  - {film.get('nameRu', film.get('nameEn', 'Нет названия'))} (ID: {film.get('kinopoiskId')})")
        
    # Получаем рейтинг для первого найденного фильма
    if results["items"][0].get("kinopoiskId"):
        kinopoisk_id = results["items"][0]["kinopoiskId"]
        ratings = kinopoisk_service.get_movie_rating({"kinopoiskId": kinopoisk_id})
        print(f"Рейтинги: {ratings}")
else:
    print("Фильмы не найдены")

# Тест 2: Поиск по IMDb ID
print("\nТест 2: Поиск по IMDb ID 'tt0133093'")
film_data = kinopoisk_service.get_movie_by_imdb_id("tt0133093", film_title="Матрица", year=1999)
if film_data:
    print(f"Найден фильм: {film_data.get('nameRu', film_data.get('nameEn', 'Нет названия'))}")
    ratings = kinopoisk_service.get_movie_rating(film_data)
    print(f"Рейтинги: {ratings}")
else:
    print("Фильм не найден по IMDb ID")

# Тест 3: Получение деталей фильма по Kinopoisk ID (если известен)
print("\nТест 3: Детали фильма по Kinopoisk ID 301")
try:
    details = kinopoisk_service.get_movie_details(301)
    print(f"Название: {details.get('nameRu', details.get('nameEn', 'Нет названия'))}")
    print(f"Год: {details.get('year')}")
    print(f"Рейтинг Кинопоиска: {details.get('ratingKinopoisk')}")
except Exception as e:
    print(f"Ошибка: {e}")