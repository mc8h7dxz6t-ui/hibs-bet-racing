# Gunicorn config for hibs-racing (gthread — avoids wedging on /cards).
import multiprocessing
import os

_sock_dir = os.getenv("HIBS_RACING_SOCKET_DIR", "/opt/hibs-racing/run")
_unix_sock = os.getenv(
    "HIBS_RACING_UNIX_SOCKET",
    f"unix:{_sock_dir}/racing_execution.sock",
)
bind = _unix_sock
umask = int(os.getenv("HIBS_RACING_GUNICORN_UMASK", "0o007"), 0)
workers = int(os.getenv("HIBS_RACING_GUNICORN_WORKERS", "2"))
worker_class = "gthread"
threads = int(os.getenv("HIBS_RACING_GUNICORN_THREADS", "4"))
timeout = int(os.getenv("HIBS_RACING_GUNICORN_TIMEOUT", "180"))
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("HIBS_RACING_GUNICORN_LOGLEVEL", "info")
control_socket_disable = True
wsgi_app = os.getenv("HIBS_RACING_GUNICORN_APP", "hibs_racing.web:create_app()")
