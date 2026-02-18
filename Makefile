# PHPyServer Makefile

.PHONY: install run dev test bench docker docker-up clean

# Install Python dependencies
install:
	pip install -r requirements.txt

# Run with Flask dev server (DEBUG=true, auto-reload)
dev:
	DEBUG=true python app.py

# Run with Gunicorn (production)
run:
	gunicorn -c gunicorn_config.py app:app

# Run tests
test:
	pytest tests/ -v --tb=short

# Run benchmark (server must be running)
bench:
	python benchmark.py

# Docker build
docker:
	docker build -t phpyserver .

# Docker compose up
docker-up:
	docker-compose up --build

# Clean logs and cache
clean:
	rm -f logs/*.log
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Generate a bcrypt-hashed password for .htpasswd
htpasswd:
	@python3 -c "\
import bcrypt, sys, getpass; \
u = input('Username: '); \
p = getpass.getpass('Password: '); \
h = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode().replace('\$$2b\$$', '\$$2y\$$'); \
print(f'{u}:{h}')" >> code/.htpasswd
	@echo "Entry appended to code/.htpasswd"
