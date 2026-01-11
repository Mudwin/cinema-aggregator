import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cinema_aggregator.settings')

app = Celery('cinema_aggregator')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

# (будет также настраиваться через админку)
app.conf.beat_schedule = {
    # Ежедневное обновление старых рейтингов (в 3:00 ночи)
    'update-old-ratings-daily': {
        'task': 'core.tasks.update_old_ratings',
        'schedule': crontab(hour=3, minute=0),
        'args': (7,),  # рейтинги старше 7 дней
    },
    # Ежедневный пересчет комплексных рейтингов (в 4:00 ночи)
    'calculate-composite-ratings-daily': {
        'task': 'core.tasks.calculate_composite_ratings',
        'schedule': crontab(hour=4, minute=0),
    },
    # Еженедельное обновление данных популярных фильмов (в понедельник в 2:00)
    'update-popular-films-weekly': {
        'task': 'core.tasks.update_popular_films_data',
        'schedule': crontab(day_of_week=1, hour=2, minute=0), 
    },
}
app.conf.timezone = 'Europe/Moscow'


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')