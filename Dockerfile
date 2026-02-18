FROM python:3.12-slim

# Install PHP CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    php-cli \
    php-common \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs code/uploads

EXPOSE 5000

ENV HOST=0.0.0.0 \
    PORT=5000 \
    DEBUG=false \
    PHP_BINARY=php \
    PHP_TIMEOUT=30 \
    MAX_UPLOAD_MB=10 \
    CACHE_TTL=60

# Development: use Flask dev server
CMD ["python", "app.py"]

# Production: uncomment below and comment CMD above
# CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]
