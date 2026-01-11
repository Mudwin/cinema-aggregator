from rest_framework import serializers
from ..models import Film, Person, Rating, FilmPersonRole


class RatingSerializer(serializers.ModelSerializer):
    """
    Сериализатор для рейтингов.
    """
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    
    class Meta:
        model = Rating
        fields = [
            'id', 'source', 'source_display', 'value', 'max_value', 
            'normalized_value', 'votes_count', 'last_updated'
        ]


class PersonFilmographySerializer(serializers.ModelSerializer):
    """
    Сериализатор для фильмографии персоны.
    """
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    film_title = serializers.CharField(source='film.title', read_only=True)
    film_year = serializers.IntegerField(source='film.year', read_only=True)
    film_composite_rating = serializers.DecimalField(
        source='film.composite_rating', 
        max_digits=4, 
        decimal_places=2, 
        read_only=True
    )
    
    class Meta:
        model = FilmPersonRole
        fields = [
            'id', 'role', 'role_display', 'character_name', 'order',
            'film_title', 'film_year', 'film_composite_rating'
        ]


class FilmListSerializer(serializers.ModelSerializer):
    """
    Сериализатор для списка фильмов.
    """
    ratings_count = serializers.IntegerField(read_only=True)
    avg_rating = serializers.DecimalField(max_digits=4, decimal_places=2, read_only=True)
    
    class Meta:
        model = Film
        fields = [
            'id', 'title', 'original_title', 'year', 'poster_url',
            'composite_rating', 'ratings_count', 'avg_rating', 'created_at'
        ]


class FilmDetailSerializer(serializers.ModelSerializer):
    """
    Сериализатор для детальной информации о фильме.
    """
    ratings = RatingSerializer(many=True, read_only=True)
    
    class Meta:
        model = Film
        fields = [
            'id', 'title', 'original_title', 'year', 'description',
            'poster_url', 'composite_rating', 'tmdb_id', 'imdb_id',
            'created_at', 'updated_at', 'ratings'
        ]


class FilmSearchSerializer(serializers.Serializer):
    """
    Сериализатор для поиска фильмов.
    """
    q = serializers.CharField(required=True, max_length=100)
    year = serializers.IntegerField(required=False, min_value=1900, max_value=2100)
    page = serializers.IntegerField(default=1, min_value=1)