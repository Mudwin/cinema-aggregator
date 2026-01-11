import logging
from typing import List, Optional

from django.db.models import Q, Avg, Count, Max
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from ..models import Film, Person, Rating, FilmPersonRole
from .serializers import (
    FilmListSerializer,
    FilmDetailSerializer,
    RatingSerializer,
    PersonFilmographySerializer,
    FilmSearchSerializer
)
from ..services import TMDBService, OMDbService, KinopoiskService, RatingCalculator
from ..tasks import fetch_film_data

logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    """
    Пагинация для стандартных результатов.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class FilmSearchView(viewsets.ReadOnlyModelViewSet):
    """
    Представление для поиска фильмов.
    Поддерживает поиск по названию, году, а также поиск через внешние API.
    """
    queryset = Film.objects.all()
    serializer_class = FilmListSerializer
    permission_classes = [AllowAny]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['title', 'original_title', 'description']
    filterset_fields = ['year']
    ordering_fields = ['title', 'year', 'composite_rating', 'created_at']
    ordering = ['-composite_rating']
    
    def get_queryset(self):
        """
        Оптимизация запросов для списка фильмов.
        """
        queryset = super().get_queryset()
        
        queryset = queryset.annotate(
            avg_rating=Avg('ratings__normalized_value'),
            ratings_count=Count('ratings')
        )
        
        min_rating = self.request.query_params.get('min_rating')
        min_ratings_count = self.request.query_params.get('min_ratings_count')
        
        if min_rating:
            queryset = queryset.filter(avg_rating__gte=min_rating)
        
        if min_ratings_count:
            queryset = queryset.filter(ratings_count__gte=min_ratings_count)
        
        return queryset.select_related().prefetch_related('ratings')
    
    @action(detail=False, methods=['get'], url_path='search/external')
    def search_external(self, request):
        """
        Поиск фильмов через внешние API (TMDB).
        """
        query = request.query_params.get('q', '').strip()
        year = request.query_params.get('year')
        
        if not query:
            return Response(
                {'error': 'Параметр поиска (q) обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            tmdb_service = TMDBService()
            search_results = tmdb_service.search_movies(
                query=query,
                year=int(year) if year else None,
                page=int(request.query_params.get('page', 1))
            )
            
            films_data = []
            for result in search_results.get('results', [])[:10]:  # 10 результатов
                film_data = {
                    'tmdb_id': result.get('id'),
                    'title': result.get('title', ''),
                    'original_title': result.get('original_title', ''),
                    'year': result.get('release_date', '')[:4] if result.get('release_date') else None,
                    'description': result.get('overview', ''),
                    'poster_url': f"https://image.tmdb.org/t/p/w500{result.get('poster_path')}" if result.get('poster_path') else None,
                    'tmdb_rating': result.get('vote_average'),
                    'tmdb_votes': result.get('vote_count'),
                    'already_in_db': False
                }
                
                existing_film = Film.objects.filter(
                    Q(tmdb_id=result.get('id')) | 
                    Q(title__iexact=result.get('title', ''))
                ).first()
                
                if existing_film:
                    film_data['already_in_db'] = True
                    film_data['db_film_id'] = existing_film.id
                    film_data['db_composite_rating'] = existing_film.composite_rating
                
                films_data.append(film_data)
            
            return Response({
                'query': query,
                'page': search_results.get('page', 1),
                'total_results': search_results.get('total_results', 0),
                'total_pages': search_results.get('total_pages', 1),
                'results': films_data
            })
            
        except Exception as e:
            logger.error(f"Error searching external API: {str(e)}")
            return Response(
                {'error': f'Ошибка при поиске: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='import/tmdb')
    def import_from_tmdb(self, request):
        """
        Импорт фильма из TMDB в нашу базу данных.
        """
        tmdb_id = request.data.get('tmdb_id')
        
        if not tmdb_id:
            return Response(
                {'error': 'Параметр tmdb_id обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        existing_film = Film.objects.filter(tmdb_id=tmdb_id).first()
        if existing_film:
            return Response({
                'status': 'already_exists',
                'film_id': existing_film.id,
                'film_title': existing_film.title,
                'message': 'Фильм уже импортирован'
            })
        
        try:
            task = fetch_film_data.delay(int(tmdb_id))
            
            return Response({
                'status': 'import_started',
                'task_id': task.id,
                'message': f'Импорт фильма с TMDB ID {tmdb_id} начат'
            })
            
        except Exception as e:
            logger.error(f"Error importing film from TMDB: {str(e)}")
            return Response(
                {'error': f'Ошибка при импорте: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FilmDetailView(viewsets.ReadOnlyModelViewSet):
    """
    Представление для детальной страницы фильма.
    """
    queryset = Film.objects.all()
    serializer_class = FilmDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = 'id'
    
    def get_queryset(self):
        """
        Оптимизация запросов для детальной страницы фильма.
        """
        queryset = super().get_queryset()
        return queryset.select_related().prefetch_related(
            'ratings',
            'film_roles',
            'film_roles__person'
        )
    
    def retrieve(self, request, *args, **kwargs):
        """
        Получение детальной информации о фильме.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        ratings_data = []
        for rating in instance.ratings.all():
            ratings_data.append({
                'source': rating.get_source_display(),
                'source_code': rating.source,
                'value': float(rating.value),
                'max_value': float(rating.max_value),
                'normalized_value': float(rating.normalized_value) if rating.normalized_value else None,
                'votes_count': rating.votes_count,
                'last_updated': rating.last_updated
            })
        
        actors = []
        directors = []
        
        for role in instance.film_roles.all().select_related('person'):
            person_info = {
                'id': role.person.id,
                'name': role.person.name,
                'photo_url': role.person.photo_url,
                'profession': role.person.get_profession_display(),
                'character_name': role.character_name,
                'role': role.get_role_display()
            }
            
            if role.role == 'actor':
                actors.append(person_info)
            elif role.role == 'director':
                directors.append(person_info)
        
        actors.sort(key=lambda x: x.get('order', 999))
        
        response_data = serializer.data
        response_data['ratings'] = ratings_data
        response_data['actors'] = actors
        response_data['directors'] = directors
        
        rating_stats = RatingCalculator.get_rating_sources_stats(instance)
        response_data['rating_stats'] = rating_stats
        
        from django.utils import timezone
        from datetime import timedelta
        
        last_rating_update = instance.ratings.aggregate(
            last_update=Max('last_updated')
        )['last_update']
        
        if last_rating_update and (timezone.now() - last_rating_update) > timedelta(days=1):
            response_data['ratings_need_update'] = True
            response_data['last_rating_update'] = last_rating_update
        else:
            response_data['ratings_need_update'] = False
        
        return Response(response_data)
    
    @action(detail=True, methods=['post'])
    def update_ratings(self, request, id=None):
        """
        Запуск обновления рейтингов для фильма.
        """
        film = self.get_object()
        
        try:
            from ..tasks import update_film_ratings
            task = update_film_ratings.delay(film.id)
            
            return Response({
                'status': 'update_started',
                'task_id': task.id,
                'message': f'Обновление рейтингов для фильма "{film.title}" начато'
            })
            
        except Exception as e:
            logger.error(f"Error updating ratings for film {film.id}: {str(e)}")
            return Response(
                {'error': f'Ошибка при обновлении рейтингов: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def similar_films(self, request, id=None):
        """
        Получение списка похожих фильмов.
        """
        film = self.get_object()
        
        similar_films = Film.objects.filter(
            year=film.year
        ).exclude(
            id=film.id
        ).filter(
            composite_rating__isnull=False
        ).order_by('-composite_rating')[:10]
        
        serializer = FilmListSerializer(similar_films, many=True, context={'request': request})
        
        return Response({
            'film': film.title,
            'similar_films': serializer.data,
            'count': len(similar_films)
        })


class FilmAutocompleteView(viewsets.GenericViewSet):
    """
    Представление для автодополнения при поиске фильмов.
    """
    queryset = Film.objects.all()
    serializer_class = FilmListSerializer 
    ordering_fields = ['title', 'year'] 
    permission_classes = [AllowAny]
    
    @action(detail=False, methods=['get'])
    def autocomplete(self, request):
        """
        Автодополнение для поиска фильмов.
        """
        query = request.query_params.get('q', '').strip()
        
        if not query or len(query) < 2:
            return Response({'results': []})
        
        films = Film.objects.filter(
            Q(title__icontains=query) | 
            Q(original_title__icontains=query)
        ).order_by('-composite_rating')[:10]
        
        results = []
        for film in films:
            results.append({
                'id': film.id,
                'title': film.title,
                'original_title': film.original_title,
                'year': film.year,
                'poster_url': film.poster_url,
                'composite_rating': float(film.composite_rating) if film.composite_rating else None
            })
        
        return Response({'results': results})