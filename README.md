# 🐘 PHPyServer

> High-performance PHP/Flask hybrid web server — run PHP scripts on-demand with full `.htaccess` emulation, in-memory caching, and zero Apache dependency.

---

## Features

| Feature | Detail |
|---|---|
| **PHP Execution** | Subprocess CLI, stdin piping, full `$_GET`/`$_POST`/`$_SERVER`/`$_COOKIE` |
| **.htaccess Parser** | `RewriteRule`, `Redirect`, `AuthType Basic`, `Deny`, `Options Indexes` |
| **Pretty URLs** | `/blog` → `blog.php` automatically |
| **Basic Auth** | APR1-MD5, SHA1, bcrypt `.htpasswd` formats |
| **Static Serving** | MIME types, TTL in-memory cache, directory auto-index |
| **File Upload** | `POST /upload` multipart, configurable size limit |
| **REST API** | `/health`, `/api/*`, `/api/cache` (DELETE) |
| **Custom 404** | Drop `404.php` or `404.html` in `code/` |
| **Production** | Gunicorn config included, Docker + Compose ready |

---

## Quick Start

```bash
# 1. Clone / download
git clone https://github.com/you/phpyserver && cd phpyserver

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env config
cp .env.example .env

# 4. Drop your PHP/HTML files in code/
#    (sample files are already there)

# 5. Start the server
python app.py
# → http://127.0.0.1:5000
```

### Docker

```bash
docker-compose up --build
```

### Production (Gunicorn)

```bash
pip install gunicorn
gunicorn -c gunicorn_config.py app:app
```

---

## Project Structure

```
phpyserver/
├── app.py                  ← Main server (Flask + all logic)
├── gunicorn_config.py      ← Production WSGI config
├── benchmark.py            ← Smoke test & benchmark tool
├── requirements.txt
├── Makefile                ← make dev / test / bench / docker
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── tests/
│   └── test_server.py      ← Unit & integration tests (pytest)
└── code/                   ← Your DocumentRoot (edit freely)
    ├── .htaccess            ← Apache-style rewrite rules
    ├── index.php            ← Demo home page
    ├── blog.php             ← Accessible as /blog (pretty URL)
    ├── api.php              ← JSON REST API routed from /api/*
    ├── 404.php              ← Custom 404 handler
    ├── style.css            ← Shared stylesheet
    ├── upload.html          ← Drag-and-drop upload demo
    └── uploads/             ← Upload destination
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind address (`0.0.0.0` for Docker) |
| `PORT` | `5000` | Listen port |
| `DEBUG` | `false` | Verbose logs + auto-reloader |
| `CODE_DIR` | `code` | DocumentRoot path |
| `PHP_BINARY` | `php` | PHP CLI binary name or full path |
| `PHP_TIMEOUT` | `30` | Max seconds per PHP execution |
| `MAX_UPLOAD_MB` | `10` | Upload size cap |
| `CACHE_TTL` | `60` | Static file cache TTL (seconds) |
| `LOG_FILE` | `logs/access.log` | Access log path |
| `SECRET_KEY` | *(change me)* | Flask session secret |

---

## `.htaccess` Support

Place a `.htaccess` in `code/`. It's parsed at startup and hot-reloaded on change.

```apache
RewriteEngine On

# Pretty URL
RewriteRule ^blog$         blog.php      [L]

# Capture group  →  back-reference
RewriteRule ^post/([0-9]+)$ post.php?id=$1 [L]

# API passthrough
RewriteRule ^api/(.+)$    api.php        [L]

# 301 redirect
Redirect 301 /old /new

# Basic auth
AuthType Basic
AuthName "Members Only"
AuthUserFile .htpasswd
Require valid-user

# Directory listing on/off
Options +Indexes
```

### Generating `.htpasswd` entries

```bash
make htpasswd          # interactive prompt, appends to code/.htpasswd
# or manually:
htpasswd -BC 10 code/.htpasswd username
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Server health + PHP availability |
| `GET` | `/api/info` | Server configuration |
| `DELETE` | `/api/cache` | Clear in-memory static cache |
| `POST` | `/upload` | Upload files (`multipart/form-data`, field: `file`) |
| `GET` | `/api/ping` | PHP-side JSON ping |
| `GET` | `/api/users` | Sample user list |
| `POST` | `/api/echo` | Echo request back as JSON |

---

## PHP Environment Variables

Every PHP script receives a full CGI environment:

```
DOCUMENT_ROOT, SCRIPT_FILENAME, SCRIPT_NAME, REQUEST_URI,
REQUEST_METHOD, QUERY_STRING, CONTENT_TYPE, CONTENT_LENGTH,
SERVER_NAME, SERVER_PORT, REMOTE_ADDR, HTTP_HOST,
HTTP_USER_AGENT, HTTP_COOKIE, HTTP_ACCEPT, … all HTTP_* headers
```

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Benchmarking

```bash
# With server running in another terminal:
python benchmark.py

# Against a different host/port:
python benchmark.py http://0.0.0.0:5000 100
```

---

## Known Limitations

- `RewriteCond` is parsed but not enforced (complex condition logic not emulated).
- No `.htaccess` in subdirectories — only `code/.htaccess` is read.
- PHP sessions use the server's default `session.save_path`; in Docker you may want to mount `/tmp`.
- `MD5`/`APR1` `.htpasswd` requires `passlib`; bcrypt requires `bcrypt` (both in `requirements.txt`).

---

## License

MIT — use freely, contribute back if you improve it.
