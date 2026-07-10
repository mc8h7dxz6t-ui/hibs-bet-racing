# Gunicorn config for hibs-racing (gthread — avoids wedging on /cards).
import multiprocessing
import os

bind = "0.0.0.0:5003"
workers = int(os.getenv("HIBS_RACING_GUNICORN_WORKERS", "2"))
worker_class = "gthread"
threads = int(os.getenv("HIBS_RACING_GUNICORN_THREADS", "4"))
timeout = int(os.getenv("HIBS_RACING_GUNICORN_TIMEOUT", "180"))
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("HIBS_RACING_GUNICORN_LOGLEVEL", "info")
wsgi_app = os.getenv("HIBS_RACING_GUNICORN_APP", "hibs_racing.web:create_app()")
