import os
import sys
from dotenv import load_dotenv 

load_dotenv('/home/Mudwin/cinema-aggregator/.env') 

path = '/home/Mudwin/cinema-aggregator'
if path not in sys.path:
    sys.path.append(path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cinema_aggregator.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
