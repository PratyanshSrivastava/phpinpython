"""
gunicorn_config.py — Production WSGI config for PHPyServer
Usage: gunicorn -c gunicorn_config.py app:app
"""
import os
import multiprocessing

bind            = f"{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '5000')}"
workers         = int(os.getenv('WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class    = "sync"          # PHP execution is CPU-bound; sync is fine
threads         = 2               # lightweight within each worker
timeout         = int(os.getenv('PHP_TIMEOUT', 35))
keepalive       = 5
max_requests    = 1000            # recycle workers to prevent memory creep
max_requests_jitter = 100
accesslog       = os.getenv('LOG_FILE', 'logs/access.log')
errorlog        = 'logs/error.log'
loglevel        = 'info'
preload_app     = True            # load once, fork many (avoids repeated .htaccess parse)
