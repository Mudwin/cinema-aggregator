from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('films/search/', views.film_search, name='film_search'),
    path('films/<int:tmdb_id>/', views.film_detail, name='film_detail'),
    path('films/<int:tmdb_id>/refresh/', views.force_refresh, name='force_refresh'),
]