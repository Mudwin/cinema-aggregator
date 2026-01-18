from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('films/search/', views.film_search, name='film_search'),
    path('films/<int:kinopoisk_id>/', views.film_detail, name='film_detail'),
    path('films/<int:kinopoisk_id>/refresh/', views.force_refresh, name='force_refresh'),
]