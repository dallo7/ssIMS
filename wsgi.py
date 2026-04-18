"""
WSGI entry point for production servers (Gunicorn, Waitress).

  gunicorn -w 2 --threads 4 -b 0.0.0.0:8050 wsgi:application
  waitress-serve --listen=0.0.0.0:8050 wsgi:application
"""
from app import server as application

__all__ = ["application"]
