from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    FilmSearchView, 
    FilmDetailView,
    FilmAutocompleteView
)

# роутер для API
router = DefaultRouter()
router.register(r'films/search', FilmSearchView, basename='film-search')
router.register(r'films', FilmDetailView, basename='film-detail')
router.register(r'autocomplete/films', FilmAutocompleteView, basename='film-autocomplete')

urlpatterns = [    
    path('api/films/search/external/', 
         FilmSearchView.as_view({'get': 'search_external'}), 
         name='film-search-external'),
    path('api/films/import/', 
         FilmSearchView.as_view({'post': 'import_from_tmdb'}), 
         name='film-import'),
    path('api/', include(router.urls)),
    
    # Для HTMX views (добавить позже)
    # path('search/', views.search_view, name='search'),
    # path('film/<int:id>/', views.film_detail_view, name='film-detail'),
]