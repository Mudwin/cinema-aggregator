import logging
import time
from functools import wraps
from typing import Optional, Dict, Any

import requests
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class APIClientError(Exception):
    """Базовое исключение для ошибок API клиента"""
    pass


class APIRequestError(APIClientError):
    """Исключение для ошибок запросов к API"""
    pass


class APIRateLimitError(APIClientError):
    """Исключение для превышения лимита запросов"""
    pass


class BaseAPIClient:
    """
    Базовый класс для всех API клиентов.
    Обеспечивает обработку ошибок, логирование, кэширование и retry механизм.
    """
    
    BASE_URL: str = None
    DEFAULT_TIMEOUT: int = 10
    DEFAULT_RETRIES: int = 3
    RETRY_DELAY: float = 1.0 
    CACHE_TIMEOUT: int = 3600  
    
    def __init__(self):
        if not self.BASE_URL:
            raise ValueError("BASE_URL должен быть определен в дочернем классе")
        
        self.session = requests.Session()
        self.setup_session()
        
    def setup_session(self):
        """Настройка сессии (заголовки, авторизация и т.д.)"""
        self.session.headers.update({
            'User-Agent': 'CinemaAggregator/1.0',
            'Accept': 'application/json',
        })
    
    def get_cache_key(self, method: str, params: Dict, endpoint: str = "") -> str:
        """
        Генерация ключа для кэша на основе метода, параметров и эндпоинта.
        """
        import hashlib
        import json
        
        cache_str = f"{method}:{self.BASE_URL}:{endpoint}:{json.dumps(params, sort_keys=True)}"
        return f"api_cache:{hashlib.md5(cache_str.encode()).hexdigest()}"
    
    def should_cache_request(self, method: str, params: Dict) -> bool:
        """
        Определяет, нужно ли кэшировать запрос.
        По умолчанию кэшируем только GET запросы.
        """
        return method.upper() == 'GET'
    
    def handle_error(self, response: requests.Response, url: str, params: Dict):
        """
        Обработка ошибок HTTP запросов.
        """
        status_code = response.status_code
        
        if status_code == 429: 
            raise APIRateLimitError(f"Превышен лимит запросов к API. URL: {url}")
        
        elif 400 <= status_code < 500:
            raise APIRequestError(
                f"Ошибка клиента {status_code} при запросе к {url}. "
                f"Ответ: {response.text[:200]}"
            )
        
        elif status_code >= 500:
            raise APIRequestError(
                f"Ошибка сервера {status_code} при запросе к {url}"
            )
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        timeout: Optional[int] = None,
        use_cache: bool = False,
        cache_timeout: Optional[int] = None,
        retries: Optional[int] = None,
    ) -> Dict:
        """
        Основной метод для выполнения HTTP-запросов с кэшированием
        """
        if params is None:
            params = {}
        if headers is None:
            headers = {}
        
        url = f"{self.BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
        timeout = timeout or self.DEFAULT_TIMEOUT
        retries = retries or self.DEFAULT_RETRIES
        cache_timeout = cache_timeout or self.CACHE_TIMEOUT
        
        cache_key = None
        if use_cache and self.should_cache_request(method, params):
            cache_key = self.get_cache_key(method, params, endpoint)
            cached_response = cache.get(cache_key)
            if cached_response:
                return cached_response
        
        last_exception = None
        
        for attempt in range(retries):
            try:
                request_headers = self.session.headers.copy()
                request_headers.update(headers)
                
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=data,
                    headers=request_headers,
                    timeout=timeout,
                )
                
                if response.status_code >= 400:
                    self.handle_error(response, url, params)
                
                try:
                    result = response.json()
                except ValueError as e:
                    raise APIRequestError(f"Не удалось распарсить JSON ответ: {str(e)}")
                
                if cache_key:
                    cache.set(cache_key, result, cache_timeout)
                
                return result
                
            except APIRateLimitError:
                wait_time = self.RETRY_DELAY * (attempt + 1) * 2
                time.sleep(wait_time)
                last_exception = APIRateLimitError
                
            except (APIRequestError, requests.exceptions.RequestException) as e:
                last_exception = e
                if attempt < retries - 1:
                    wait_time = self.RETRY_DELAY * (attempt + 1)
                    time.sleep(wait_time)
                else:
                    raise APIRequestError(f"Запрос не удался после {retries} попыток: {str(e)}")
        
        raise APIRequestError(f"Все {retries} попытки запроса не удались. Последняя ошибка: {last_exception}")
    
    def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        **kwargs
    ) -> Dict:
        """
        Выполнение GET запроса.
        """
        return self._make_request('GET', endpoint, params=params, **kwargs)
    
    def post(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        **kwargs
    ) -> Dict:
        """
        Выполнение POST запроса.
        """
        return self._make_request('POST', endpoint, data=data, **kwargs)
    
    def clear_cache_for_request(self, method: str, params: Dict):
        """
        Очистка кэша для конкретного запроса.
        """
        cache_key = self.get_cache_key(method, params)
        cache.delete(cache_key)
    
    def clear_all_cache(self):
        """
        Очистка всего кэша для этого API клиента.
        """
        from django.core.cache import cache
        
        keys_to_delete = []
        
        for key in cache._cache.keys():
            if isinstance(key, str) and key.startswith('api_cache:'):
                keys_to_delete.append(key)
        
        cache.delete_many(keys_to_delete)


def api_request_logger(func):
    """
    Декоратор для логирования вызовов API методов.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"Вызов API метода: {func.__name__}")
        
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed_time = time.time() - start_time
            
            logger.debug(f"Тип результата: {type(result)}")
            
            return result
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"API метод упал с ошибкой {func.__name__} через {elapsed_time:.2f}s: {str(e)}")
            raise
    
    return wrapper