from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, CrontabSchedule, IntervalSchedule
import json


class Command(BaseCommand):
    help = 'Создает или обновляет периодические задачи Celery Beat'

    def handle(self, *args, **options):
        daily_3am, _ = CrontabSchedule.objects.get_or_create(
            minute='0',
            hour='3',
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
            timezone='Europe/Moscow'
        )
        
        daily_4am, _ = CrontabSchedule.objects.get_or_create(
            minute='0',
            hour='4',
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
            timezone='Europe/Moscow'
        )
        
        monday_2am, _ = CrontabSchedule.objects.get_or_create(
            minute='0',
            hour='2',
            day_of_week='1',  
            day_of_month='*',
            month_of_year='*',
            timezone='Europe/Moscow'
        )
        
        hourly, _ = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.HOURS,
        )
        
        every_5min, _ = IntervalSchedule.objects.get_or_create(
            every=5,
            period=IntervalSchedule.MINUTES,
        )
        
        PeriodicTask.objects.update_or_create(
            name='Обновление старых рейтингов',
            defaults={
                'task': 'core.tasks.update_old_ratings',
                'crontab': daily_3am,
                'args': json.dumps([7]),  #
                'description': 'Ежедневное обновление рейтингов, которые давно не обновлялись',
                'enabled': True,
            }
        )
        
        PeriodicTask.objects.update_or_create(
            name='Пересчет комплексных рейтингов',
            defaults={
                'task': 'core.tasks.calculate_composite_ratings',
                'crontab': daily_4am,
                'description': 'Ежедневный пересчет комплексных рейтингов для всех фильмов',
                'enabled': True,
            }
        )
        
        PeriodicTask.objects.update_or_create(
            name='Обновление данных популярных фильмов',
            defaults={
                'task': 'core.tasks.update_popular_films_data',
                'crontab': monday_2am,
                'args': json.dumps([50]), 
                'description': 'Еженедельное обновление данных самых популярных фильмов',
                'enabled': True,
            }
        )
        
        PeriodicTask.objects.update_or_create(
            name='Проверка статуса API',
            defaults={
                'task': 'core.tasks.check_api_status',
                'interval': hourly,
                'description': 'Ежечасная проверка доступности внешних API',
                'enabled': True,
            }
        )
        
        PeriodicTask.objects.update_or_create(
            name='Очистка старых задач',
            defaults={
                'task': 'core.tasks.cleanup_old_tasks',
                'crontab': daily_4am,  
                'args': json.dumps([30]), 
                'description': 'Ежедневная очистка старых результатов задач',
                'enabled': True,
            }
        )
        
        self.stdout.write(
            self.style.SUCCESS('Периодические задачи успешно созданы/обновлены')
        )
        
        tasks = PeriodicTask.objects.all()
        self.stdout.write(f'\nВсего периодических задач: {tasks.count()}')
        for task in tasks:
            self.stdout.write(f'  - {task.name} ({task.task})')