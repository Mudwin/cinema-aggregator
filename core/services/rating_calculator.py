from decimal import Decimal
from django.db.models import Avg


class RatingCalculator:
    """
    Класс для расчета комплексных рейтингов фильмов.
    """
    
    @staticmethod
    def calculate_composite_rating(film):
        """
        Расчет композитного рейтинга для фильма.
        
        Args:
            film: Объект модели Film
        
        Returns:
            Decimal: Среднее значение нормализованных рейтингов
        """
        avg_rating = film.ratings.aggregate(
            avg_normalized=Avg('normalized_value')
        )['avg_normalized']
        
        if avg_rating is not None:
            return Decimal(avg_rating).quantize(Decimal('0.01'))
        return None
    
    @staticmethod
    def calculate_weighted_rating(film, weights=None):
        """
        Расчет взвешенного рейтинга с учетом весов источников.
        
        Args:
            film: Объект модели Film
            weights (dict): Веса для каждого источника
                Например: {'imdb': 0.3, 'kinopoisk': 0.3, 'rotten_tomatoes': 0.2, 'metacritic': 0.2}
        
        Returns:
            Decimal: Взвешенный рейтинг
        """
        if weights is None:
            weights = {
                'imdb': 0.25,
                'kinopoisk': 0.25,
                'rotten_tomatoes': 0.25,
                'metacritic': 0.25
            }
        
        weighted_sum = Decimal('0')
        total_weight = Decimal('0')
        
        for rating in film.ratings.all():
            source = rating.source
            if source in weights and rating.normalized_value:
                weight = Decimal(str(weights[source]))
                weighted_sum += rating.normalized_value * weight
                total_weight += weight
        
        if total_weight > 0:
            return (weighted_sum / total_weight).quantize(Decimal('0.01'))
        return None
    
    @staticmethod
    def get_rating_sources_stats(film):
        """
        Получение статистики по рейтингам из разных источников.
        
        Args:
            film: Объект модели Film
        
        Returns:
            dict: Статистика по рейтингам
        """
        ratings = film.ratings.all()
        stats = {
            'sources_count': ratings.count(),
            'sources': {},
            'min_rating': None,
            'max_rating': None,
            'avg_rating': None
        }
        
        if ratings:
            normalized_values = [r.normalized_value for r in ratings if r.normalized_value]
            if normalized_values:
                stats['min_rating'] = min(normalized_values)
                stats['max_rating'] = max(normalized_values)
                stats['avg_rating'] = sum(normalized_values) / len(normalized_values)
            
            for rating in ratings:
                stats['sources'][rating.source] = {
                    'value': rating.value,
                    'max_value': rating.max_value,
                    'normalized_value': rating.normalized_value,
                    'votes_count': rating.votes_count
                }
        
        return stats