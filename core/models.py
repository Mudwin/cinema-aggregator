from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Film(models.Model):
    """
    Модель фильма.
    """
    title = models.CharField(
        max_length=255,
        verbose_name="Название на русском"
    )
    original_title = models.CharField(
        max_length=255,
        verbose_name="Оригинальное название"
    )
    year = models.IntegerField(
        verbose_name="Год выпуска",
        validators=[
            MinValueValidator(1888),
            MaxValueValidator(2100)
        ]
    )
    description = models.TextField(
        verbose_name="Описание сюжета",
        blank=True,
        null=True
    )
    poster_url = models.URLField(
        max_length=500,
        verbose_name="Ссылка на постер",
        blank=True,
        null=True
    )
    tmdb_id = models.IntegerField(
        unique=True,
        verbose_name="ID в TMDB API"
    )
    imdb_id = models.CharField(
        max_length=20,
        unique=False,
        verbose_name="ID в IMDb",
        blank=True,
        null=True
    )
    composite_rating = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        verbose_name="Композитный рейтинг",
        help_text="Средний рейтинг из всех источников (нормализованный к 10-балльной шкале)",
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания записи"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Фильм"
        verbose_name_plural = "Фильмы"
        ordering = ['-year', 'title']
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['year']),
            models.Index(fields=['composite_rating']),
            models.Index(fields=['tmdb_id']),
            models.Index(fields=['imdb_id']),
        ]

    def __str__(self):
        return f"{self.title} ({self.year})"


class Person(models.Model):
    """
    Модель персоны (актер, режиссер и т.д.).
    """
    class ProfessionChoices(models.TextChoices):
        ACTOR = 'actor', 'Актер'
        DIRECTOR = 'director', 'Режиссер'
        WRITER = 'writer', 'Сценарист'
        PRODUCER = 'producer', 'Продюсер'
        COMPOSER = 'composer', 'Композитор'
        CINEMATOGRAPHER = 'cinematographer', 'Оператор'
        EDITOR = 'editor', 'Монтажер'
        OTHER = 'other', 'Другое'

    name = models.CharField(
        max_length=255,
        verbose_name="Имя и фамилия на русском"
    )
    original_name = models.CharField(
        max_length=255,
        verbose_name="Имя на языке оригинала"
    )
    tmdb_id = models.IntegerField(
        unique=True,
        verbose_name="ID в TMDB API"
    )
    biography = models.TextField(
        verbose_name="Биография",
        blank=True,
        null=True
    )
    photo_url = models.URLField(
        max_length=500,
        verbose_name="Ссылка на фотографию",
        blank=True,
        null=True
    )
    birth_date = models.DateField(
        verbose_name="Дата рождения",
        blank=True,
        null=True
    )
    death_date = models.DateField(
        verbose_name="Дата смерти",
        blank=True,
        null=True
    )
    profession = models.CharField(
        max_length=50,
        choices=ProfessionChoices.choices,
        verbose_name="Основная профессия",
        default=ProfessionChoices.ACTOR
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания записи"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        verbose_name = "Персона"
        verbose_name_plural = "Персоны"
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['tmdb_id']),
            models.Index(fields=['profession']),
        ]

    def __str__(self):
        return self.name


class FilmPersonRole(models.Model):
    """
    Модель связи фильма и персоны с указанием роли.
    """
    class RoleChoices(models.TextChoices):
        ACTOR = 'actor', 'Актер'
        DIRECTOR = 'director', 'Режиссер'
        WRITER = 'writer', 'Сценарист'
        PRODUCER = 'producer', 'Продюсер'
        COMPOSER = 'composer', 'Композитор'
        CINEMATOGRAPHER = 'cinematographer', 'Оператор'
        EDITOR = 'editor', 'Монтажер'
        OTHER = 'other', 'Другое'

    film = models.ForeignKey(
        Film,
        on_delete=models.CASCADE,
        related_name='film_roles',
        verbose_name="Фильм"
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='person_roles',
        verbose_name="Персона"
    )
    role = models.CharField(
        max_length=50,
        choices=RoleChoices.choices,
        verbose_name="Роль в фильме"
    )
    character_name = models.CharField(
        max_length=255,
        verbose_name="Название персонажа",
        blank=True,
        null=True
    )
    order = models.IntegerField(
        verbose_name="Порядок отображения",
        default=0,
        help_text="Чем меньше число, тем важнее роль (для актеров: 0 - главная роль)"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания записи"
    )

    class Meta:
        verbose_name = "Роль в фильме"
        verbose_name_plural = "Роли в фильмах"
        ordering = ['film', 'role', 'order']
        unique_together = ['film', 'person', 'role']
        indexes = [
            models.Index(fields=['film', 'role']),
            models.Index(fields=['person', 'role']),
        ]

    def __str__(self):
        if self.character_name:
            return f"{self.person.name} как {self.character_name} в {self.film.title}"
        return f"{self.person.name} ({self.get_role_display()}) в {self.film.title}"


class Rating(models.Model):
    """
    Модель рейтинга фильма из различных источников.
    """
    class SourceChoices(models.TextChoices):
        IMDB = 'imdb', 'IMDb'
        ROTTEN_TOMATOES = 'rotten_tomatoes', 'Rotten Tomatoes'
        METACRITIC = 'metacritic', 'Metacritic'
        KINOPOISK = 'kinopoisk', 'Кинопоиск'

    film = models.ForeignKey(
        Film,
        on_delete=models.CASCADE,
        related_name='ratings',
        verbose_name="Фильм"
    )
    source = models.CharField(
        max_length=50,
        choices=SourceChoices.choices,
        verbose_name="Источник"
    )
    value = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        verbose_name="Значение рейтинга"
    )
    max_value = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        verbose_name="Максимальное значение шкалы",
        default=10
    )
    normalized_value = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        verbose_name="Нормализованное значение (к 10-балльной шкале)",
        help_text="Значение рейтинга, приведенное к 10-балльной шкале",
        blank=True,
        null=True
    )
    votes_count = models.IntegerField(
        verbose_name="Количество голосов",
        blank=True,
        null=True
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата последнего обновления"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания записи"
    )

    class Meta:
        verbose_name = "Рейтинг"
        verbose_name_plural = "Рейтинги"
        ordering = ['film', 'source']
        unique_together = ['film', 'source']
        indexes = [
            models.Index(fields=['film', 'source']),
            models.Index(fields=['source']),
            models.Index(fields=['normalized_value']),
        ]

    def save(self, *args, **kwargs):
        """
        При сохранении автоматически вычисляем normalized_value.
        normalized_value = (value / max_value) * 10
        """
        if self.value is not None and self.max_value is not None and self.max_value > 0:
            self.normalized_value = (self.value / self.max_value) * 10
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_source_display()}: {self.value}/{self.max_value} для {self.film.title}"