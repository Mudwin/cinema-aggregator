"""
API модуль для Cinema Aggregator.
"""

from .views import (
    FilmSearchView,
    FilmDetailView,
    FilmAutocompleteView,
    StandardResultsSetPagination
)

from .serializers import (
    FilmListSerializer,
    FilmDetailSerializer,
    RatingSerializer,
    PersonFilmographySerializer,
    FilmSearchSerializer
)

__all__ = [
    'FilmSearchView',
    'FilmDetailView',
    'FilmAutocompleteView',
    'StandardResultsSetPagination',
    'FilmListSerializer',
    'FilmDetailSerializer',
    'RatingSerializer',
    'PersonFilmographySerializer',
    'FilmSearchSerializer'
]