"""Gunicorn configuration for tacit-knowledge-externalization.

Use a single worker to avoid JSON workspace file races across processes.
Long timeouts accommodate LLM streaming and heavy Excel operations.
"""

bind = "0.0.0.0:5000"
workers = 1
threads = 4
worker_class = "gthread"
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
preload_app = False
accesslog = "-"
errorlog = "-"
capture_output = True
enable_stdio_inheritance = True
