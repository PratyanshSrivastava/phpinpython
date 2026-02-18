# 🐘 PHPyServer

> Run PHP files through Python Flask — with a full admin panel, .htaccess support, and zero Apache needed.

---

## Quick Start (3 steps)

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Copy the example config (optional — defaults work out of the box)
cp .env.example .env

# 3. Start both servers
python run.py
```

That's it! Open your browser:

| What | URL |
|---|---|
| 🌐 Your PHP site | http://localhost:5000 |
| ⚙️ Admin panel | http://localhost:8080 |

---

## Project Structure

```
phpyserver/
├── run.py          ← START HERE — launches both servers
├── server.py       ← PHP server (port 5000)
├── admin.py        ← Admin panel (port 8080)
├── core.py         ← Shared utilities (cache, htaccess, php executor)
├── requirements.txt
├── .env.example    ← Copy to .env to configure
│
├── code/           ← YOUR FILES GO HERE (like Apache's DocumentRoot)
│   ├── .htaccess   ← URL rewrites, auth, options
│   ├── index.php   ← Homepage
│   ├── blog.php    ← Accessible as /blog (pretty URL)
│   ├── gallery.php ← Accessible as /gallery
│   ├── api.php     ← REST API at /api/*
│   ├── 404.php     ← Custom 404 page
│   ├── style.css   ← Shared stylesheet
│   ├── partials/   ← Reusable PHP includes
│   └── uploads/    ← File upload destination
│
├── logs/           ← Access logs
└── tests/          ← pytest tests
    └── test_core.py
```

---

## The Admin Panel (localhost:8080)

The admin panel is a full web UI for managing your server without touching the command line.

| Page | What you can do |
|---|---|
| 🏠 Dashboard | Live request stats, server status, quick actions |
| ⚙️ Settings | Edit all server config (PHP binary, ports, cache TTL, etc.) |
| 📁 File Manager | Browse, create, edit, upload, and delete files in `code/` |
| 🔀 Rewrite Rules | Edit `.htaccess` with syntax highlighting, see parsed rules |
| 👥 Users & Auth | Add/remove `.htpasswd` users, enable basic auth |
| 📋 Logs | View and filter access logs in real-time |
| 🐘 PHP Info | Check PHP version, extensions, and INI settings |

---

## Adding Your Own PHP Files

1. Drop `.php` files into the `code/` folder
2. Visit `http://localhost:5000/your-file` — the `.php` extension is optional
3. Use the File Manager in the admin panel to edit files directly in the browser

**Pretty URLs** — PHPyServer automatically maps `/about` → `about.php`. You can also add explicit rules in `code/.htaccess`.

---

## .htaccess Support

Edit `code/.htaccess` to configure routing. The admin panel has a visual editor.

```apache
RewriteEngine On

# Pretty URL: /blog → blog.php
RewriteRule ^blog$  blog.php  [L]

# Capture group: /post/42 → post.php?id=42
RewriteRule ^post/([0-9]+)$  post.php?id=$1  [L]

# API route: /api/* → api.php
RewriteRule ^api/(.+)$  api.php  [L]

# 301 redirect
Redirect 301 /old /new

# Directory listing (remove + to disable)
Options +Indexes

# Basic auth (add users via Admin → Users)
# AuthType Basic
# AuthName "Members Only"
# AuthUserFile .htpasswd
# Require valid-user
```

---

## Configuration

Edit `.env` (or use the Admin → Settings page):

| Variable | Default | Description |
|---|---|---|
| `PORT` | `5000` | PHP server port |
| `ADMIN_PORT` | `8080` | Admin panel port |
| `PHP_BINARY` | `php` | Path to PHP CLI (`php`, `php8.2`, `/usr/bin/php`) |
| `PHP_TIMEOUT` | `30` | Max seconds per PHP script |
| `CODE_DIR` | `code` | Your DocumentRoot folder |
| `CACHE_TTL` | `60` | Static file cache in seconds (0 = off) |
| `MAX_UPLOAD_MB` | `10` | Upload size limit |
| `DEBUG` | `false` | Show PHP errors and verbose logs |

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Tips for Beginners

- **PHP not found?** Run `php -v` in terminal. If it's not installed, download PHP from https://www.php.net/downloads and make sure it's in your PATH.
- **Port already in use?** Change `PORT` or `ADMIN_PORT` in `.env` (or via the Settings page).
- **Edit files live** — use the Admin → File Manager. Changes to `.php` files are instant (no server restart needed).
- **Changes to `.env`** take effect on the next server start for port/host settings, but immediately for most others.
- **Uploads** — files uploaded via `POST /__upload` are saved to `code/uploads/`.

---

## Requirements

- Python 3.10+
- PHP CLI (any version — check with `php -v`)
- pip packages: flask, python-dotenv, werkzeug
