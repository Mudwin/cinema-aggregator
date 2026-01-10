from django.contrib import admin
from django.db.models import Avg
from .models import Film, Person, FilmPersonRole, Rating


class RatingInline(admin.TabularInline):
    """
    Inline для отображения рейтингов на странице фильма.
    """
    model = Rating
    extra = 0
    readonly_fields = ('normalized_value', 'last_updated', 'created_at')
    fields = ('source', 'value', 'max_value', 'normalized_value', 'votes_count', 'last_updated')


class FilmPersonRoleInline(admin.TabularInline):
    """
    Inline для отображения ролей персон на странице фильма.
    """
    model = FilmPersonRole
    extra = 0
    fields = ('person', 'role', 'character_name', 'order')
    raw_id_fields = ('person',)
    autocomplete_fields = ['person']


@admin.register(Film)
class FilmAdmin(admin.ModelAdmin):
    """
    Административная конфигурация для модели Film.
    """
    list_display = (
        'title', 
        'year', 
        'composite_rating', 
        'tmdb_id', 
        'imdb_id', 
        'created_at'
    )
    list_filter = (
        'year',
        ('composite_rating', admin.EmptyFieldListFilter),
    )
    search_fields = (
        'title',
        'original_title',
        'tmdb_id',
        'imdb_id',
        'description',
    )
    readonly_fields = ('created_at', 'updated_at', 'composite_rating')
    list_per_page = 20
    list_select_related = False
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'title',
                'original_title',
                'year',
                'description',
            )
        }),
        ('Идентификаторы', {
            'fields': (
                'tmdb_id',
                'imdb_id',
            )
        }),
        ('Медиа', {
            'fields': (
                'poster_url',
            )
        }),
        ('Рейтинги', {
            'fields': (
                'composite_rating',
            )
        }),
        ('Даты', {
            'fields': (
                'created_at',
                'updated_at',
            )
        }),
    )
    inlines = [RatingInline, FilmPersonRoleInline]
    actions = ['update_composite_rating']

    def get_queryset(self, request):
        """
        Оптимизация запросов через select_related и prefetch_related.
        """
        queryset = super().get_queryset(request)
        queryset = queryset.prefetch_related('ratings', 'film_roles')
        return queryset

    def update_composite_rating(self, request, queryset):
        """
        Действие для обновления композитного рейтинга выбранных фильмов.
        """
        updated_count = 0
        for film in queryset:
            avg_rating = film.ratings.aggregate(
                avg_normalized=Avg('normalized_value')
            )['avg_normalized']
            
            if avg_rating is not None:
                film.composite_rating = avg_rating
                film.save(update_fields=['composite_rating'])
                updated_count += 1
        
        self.message_user(
            request, 
            f'Обновлено композитных рейтингов: {updated_count}'
        )
    
    update_composite_rating.short_description = 'Обновить композитный рейтинг для выбранных фильмов'


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    """
    Административная конфигурация для модели Person.
    """
    list_display = (
        'name',
        'original_name',
        'profession',
        'birth_date',
        'tmdb_id',
        'created_at',
    )
    list_filter = (
        'profession',
        ('birth_date', admin.EmptyFieldListFilter),
    )
    search_fields = (
        'name',
        'original_name',
        'tmdb_id',
        'biography',
    )
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 20
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'name',
                'original_name',
                'profession',
            )
        }),
        ('Биография', {
            'fields': (
                'biography',
                'birth_date',
                'death_date',
            )
        }),
        ('Идентификаторы и медиа', {
            'fields': (
                'tmdb_id',
                'photo_url',
            )
        }),
        ('Даты', {
            'fields': (
                'created_at',
                'updated_at',
            )
        }),
    )
    autocomplete_fields = []


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    """
    Административная конфигурация для модели Rating.
    """
    list_display = (
        'film',
        'source',
        'value',
        'max_value',
        'normalized_value',
        'votes_count',
        'last_updated',
    )
    list_filter = (
        'source',
        ('last_updated', admin.DateFieldListFilter),
    )
    search_fields = (
        'film__title',
        'film__original_title',
    )
    readonly_fields = (
        'normalized_value',
        'last_updated',
        'created_at',
    )
    list_per_page = 20
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'film',
                'source',
            )
        }),
        ('Значения рейтинга', {
            'fields': (
                'value',
                'max_value',
                'normalized_value',
                'votes_count',
            )
        }),
        ('Даты', {
            'fields': (
                'last_updated',
                'created_at',
            )
        }),
    )
    raw_id_fields = ('film',)


@admin.register(FilmPersonRole)
class FilmPersonRoleAdmin(admin.ModelAdmin):
    """
    Административная конфигурация для модели FilmPersonRole.
    """
    list_display = (
        'film',
        'person',
        'role',
        'character_name',
        'order',
        'created_at',
    )
    list_filter = (
        'role',
        ('created_at', admin.DateFieldListFilter),
    )
    search_fields = (
        'film__title',
        'person__name',
        'character_name',
    )
    readonly_fields = ('created_at',)
    list_per_page = 20
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'film',
                'person',
                'role',
            )
        }),
        ('Дополнительная информация', {
            'fields': (
                'character_name',
                'order',
            )
        }),
        ('Даты', {
            'fields': (
                'created_at',
            )
        }),
    )
    raw_id_fields = ('film', 'person')
    autocomplete_fields = ['film', 'person']


admin.site.site_header = 'Cinema Aggregator Administration'
admin.site.site_title = 'Cinema Aggregator Admin'
admin.site.index_title = 'Администрирование Cinema Aggregator'