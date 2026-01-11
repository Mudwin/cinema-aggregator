from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .api.views import (
    FilmSearchView, 
    FilmDetailView,
    FilmAutocompleteView,
    search_task_status
)

# роутер для API
router = DefaultRouter()
router.register(r'films/search', FilmSearchView, basename='film-search')
router.register(r'films', FilmDetailView, basename='film-detail')
router.register(r'autocomplete/films', FilmAutocompleteView, basename='film-autocomplete')

urlpatterns = [
    path('', views.home, name='home'),
    path('films/search/', views.film_search, name='film_search'),
    path('films/search/external/', views.film_search_external, name='film_search_external'),
    path('films/import/', views.film_import, name='film_import'),
    path('films/<int:film_id>/', views.film_detail, name='film_detail'),
    path('films/<int:film_id>/update-ratings/', views.update_film_ratings_view, name='update_film_ratings'),
    
    path('api/', include(router.urls)),
    
    path('api/films/search/external/', 
         FilmSearchView.as_view({'get': 'search_external'}), 
         name='api-film-search-external'),
    path('api/films/import/', 
         FilmSearchView.as_view({'post': 'import_from_tmdb'}), 
         name='api-film-import'),
]