"""
server.py — PHPyServer main request handler (localhost:5000)
Serves your code/ directory: PHP execution, static files, .htaccess support.
"""

import time
import mimetypes
from pathlib import Path
from datetime import datetime

from flask import (
    Flask, request, Response, redirect,
    abort, render_template_string, jsonify
)
from werkzeug.utils import secure_filename

from core import (
    config, cache, stats, htaccess, php,
    STATIC_EXTS, safe_path, format_size, logger,
)

app = Flask(__name__)


# ─── Directory listing template ───────────────────────────────────────────────

DIR_TMPL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Index of {{ path }}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f8fafc; color: #1e293b; }
    header { background: #1e293b; color: #f1f5f9; padding: 1rem 2rem; display: flex; align-items: center; gap: .75rem; }
    header h1 { font-size: 1.1rem; font-weight: 600; }
    .breadcrumb { padding: .6rem 2rem; background: #fff; border-bottom: 1px solid #e2e8f0;
      font-size: .85rem; color: #64748b; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #f1f5f9; text-align: left; padding: .6rem 2rem;
      font-size: .8rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em;
      border-bottom: 1px solid #e2e8f0; }
    td { padding: .65rem 2rem; border-bottom: 1px solid #f1f5f9; font-size: .9rem; }
    tr:hover td { background: #f8fafc; }
    a { color: #4f46e5; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .icon { margin-right: .4rem; }
    .size, .date { color: #94a3b8; font-size: .85rem; }
    .php-badge { font-size: .7rem; background: #ede9fe; color: #7c3aed;
      padding: .1rem .4rem; border-radius: 4px; margin-left: .4rem; }
    footer { padding: 1.5rem 2rem; color: #94a3b8; font-size: .8rem; }
  </style>
</head>
<body>
  <header>
    <span style="font-size:1.5rem">📂</span>
    <h1>Index of {{ path }}</h1>
  </header>
  <div class="breadcrumb">PHPyServer &rsaquo; {{ path }}</div>
  <table>
    <tr>
      <th>Name</th><th>Size</th><th>Modified</th>
    </tr>
    {% if parent %}
    <tr>
      <td><span class="icon">⬆</span><a href="{{ parent }}">Parent Directory</a></td>
      <td></td><td></td>
    </tr>
    {% endif %}
    {% for e in entries %}
    <tr>
      <td>
        {% if e.is_dir %}
          <span class="icon">📁</span><a href="{{ e.href }}">{{ e.name }}/</a>
        {% else %}
          <span class="icon">{{ e.icon }}</span><a href="{{ e.href }}">{{ e.name }}</a>
          {% if e.name.endswith('.php') %}<span class="php-badge">PHP</span>{% endif %}
        {% endif %}
      </td>
      <td class="size">{{ e.size }}</td>
      <td class="date">{{ e.mtime }}</td>
    </tr>
    {% endfor %}
  </table>
  <footer>PHPyServer &bull; Admin panel at <a href="http://{{ admin_host }}">localhost:{{ admin_port }}</a> &bull; {{ now }}</footer>
</body>
</html>"""

FILE_ICONS = {
    ".php": "🐘", ".html": "🌐", ".htm": "🌐", ".css": "🎨",
    ".js": "⚡", ".json": "📋", ".png": "🖼", ".jpg": "🖼",
    ".jpeg": "🖼", ".gif": "🖼", ".svg": "🖼", ".pdf": "📄",
    ".zip": "📦", ".txt": "📝", ".md": "📝", ".mp4": "🎬",
}


def render_dir_index(fs_path: Path, url_path: str) -> str:
    try:
        items = sorted(fs_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        items = []

    entries = []
    for item in items:
        if item.name.startswith("."):
            continue
        href = url_path.rstrip("/") + "/" + item.name
        size = ""
        if item.is_file():
            size = format_size(item.stat().st_size)
        mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        icon = "📁" if item.is_dir() else FILE_ICONS.get(item.suffix.lower(), "📄")
        entries.append({"name": item.name, "href": href, "is_dir": item.is_dir(),
                        "size": size, "mtime": mtime, "icon": icon})

    parent = str(Path(url_path).parent) if url_path not in ("/", "") else None
    return render_template_string(
        DIR_TMPL,
        path=url_path or "/",
        entries=entries,
        parent=parent,
        admin_host=f"{config.get('ADMIN_HOST')}:{config.get('ADMIN_PORT')}",
        admin_port=config.get("ADMIN_PORT"),
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ─── Serve helpers ────────────────────────────────────────────────────────────

def serve_static(fs_path: Path, url_path: str) -> Response:
    key = str(fs_path)
    ttl = config.cache_ttl
    cached = cache.get(key, ttl) if ttl > 0 else None
    kind = "cache"

    if cached:
        mime, data = cached["mime"], cached["data"]
    else:
        kind = "static"
        try:
            data = fs_path.read_bytes()
        except OSError:
            abort(404)
        mime = mimetypes.guess_type(fs_path.name)[0] or "application/octet-stream"
        if ttl > 0 and fs_path.suffix.lower() in STATIC_EXTS:
            cache.set(key, {"data": data, "mime": mime})

    resp = Response(data, mimetype=mime)
    resp.headers["Cache-Control"] = f"public, max-age={ttl}" if ttl > 0 else "no-cache"
    return resp, kind


def serve_php(fs_path: Path) -> tuple:
    post_data = request.get_data()
    stdout, stderr, rc, ms = php.execute(
        fs_path, config,
        query_string=request.query_string.decode(),
        post_data=post_data,
    )

    if rc == -2:
        return Response(
            f"<h1>503 — PHP Not Available</h1><pre>Binary: {config.php_binary}\n{stderr}</pre>",
            503, mimetype="text/html"
        ), ms

    if rc == -1:
        return Response("<h1>504 — PHP Timeout</h1>", 504, mimetype="text/html"), ms

    if stderr and config.debug:
        logger.debug(f"PHP stderr from {fs_path.name}:\n{stderr}")

    headers, body = php.parse_cgi_output(stdout)
    status = headers.pop("_status", 200)

    if "Location" in headers:
        code = status if status in (301, 302, 303, 307, 308) else 302
        return redirect(headers["Location"], code=code), ms

    mime = headers.pop("Content-Type", "text/html; charset=UTF-8")
    resp = Response(body, status=status, mimetype=mime)
    for k, v in headers.items():
        try:
            resp.headers[k] = v
        except Exception:
            pass
    return resp, ms


def require_auth_response() -> Response:
    realm = htaccess.auth.get("realm", "Restricted Area")
    return Response(
        "Authentication required.",
        401,
        {"WWW-Authenticate": f'Basic realm="{realm}"'},
    )


# ─── Main catch-all route ─────────────────────────────────────────────────────

@app.route("/", defaults={"url_path": ""},
           methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
@app.route("/<path:url_path>",
           methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def catch_all(url_path: str):
    t0 = time.perf_counter()
    original_path = "/" + url_path
    code_dir = config.code_dir

    # Ensure .htaccess is loaded (hot-reload on file change)
    htaccess.load(code_dir)

    # 1. Deny hidden files
    if htaccess.is_denied(url_path):
        ms = (time.perf_counter() - t0) * 1000
        stats.record(request.method, original_path, 403, ms)
        abort(403)

    # 2. Rewrite / redirect rules
    rewritten, redir_code = htaccess.apply_rewrites(original_path)
    if redir_code:
        ms = (time.perf_counter() - t0) * 1000
        stats.record(request.method, original_path, redir_code, ms)
        return redirect(rewritten, code=redir_code)

    lookup = rewritten if rewritten != original_path else original_path

    # 3. Basic auth
    if not htaccess.check_auth(code_dir):
        ms = (time.perf_counter() - t0) * 1000
        stats.record(request.method, original_path, 401, ms)
        return require_auth_response()

    # 4. Resolve filesystem path
    fs_path = safe_path(lookup, code_dir)
    if fs_path is None:
        abort(403)

    # 5. Directory handling
    if fs_path.is_dir():
        index_files = htaccess.options.get("directoryindex", ["index.php", "index.html"])
        for idx in index_files:
            candidate = fs_path / idx
            if candidate.exists():
                fs_path = candidate
                break
        else:
            if htaccess.options.get("indexes", True):
                html = render_dir_index(fs_path, "/" + url_path)
                ms = (time.perf_counter() - t0) * 1000
                stats.record(request.method, original_path, 200, ms, "static")
                return Response(html, mimetype="text/html")
            else:
                abort(403)

    # 6. Pretty URL: /blog → blog.php
    if not fs_path.exists():
        for candidate in [
            fs_path.with_suffix(".php"),
            safe_path(lookup.rstrip("/") + ".php", code_dir),
        ]:
            if candidate and candidate.exists():
                fs_path = candidate
                break
        else:
            ms = (time.perf_counter() - t0) * 1000
            stats.record(request.method, original_path, 404, ms)
            abort(404)

    # 7. Serve
    if fs_path.suffix.lower() == ".php":
        resp, ms = serve_php(fs_path)
        status = resp.status_code
        kind = "php"
    else:
        resp, kind = serve_static(fs_path, lookup)
        ms = (time.perf_counter() - t0) * 1000
        status = 200

    elapsed = (time.perf_counter() - t0) * 1000
    stats.record(request.method, original_path, status, elapsed, kind)
    logger.info(f'{request.remote_addr} "{request.method} {original_path}" {status} {elapsed:.1f}ms [{kind}]')
    return resp


# ─── Built-in endpoints ───────────────────────────────────────────────────────

@app.route("/__health")
def health():
    return jsonify({
        "status":    "ok",
        "php":       "available" if php.is_available(config.php_binary) else "not found",
        "requests":  stats.total_requests,
        "uptime":    stats.uptime,
    })


@app.route("/__upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file field"}), 400
    saved, errors = [], []
    upload_dir = config.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    for f in request.files.getlist("file"):
        if not f.filename:
            continue
        name = secure_filename(f.filename)
        try:
            f.save(upload_dir / name)
            saved.append({"filename": name, "size": (upload_dir / name).stat().st_size})
        except Exception as e:
            errors.append({"filename": name, "error": str(e)})
    return jsonify({"saved": saved, "errors": errors}), 200 if saved else 400


# ─── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(403)
def forbidden(_):
    code_dir = config.code_dir
    for name in ("403.php", "403.html"):
        p = code_dir / name
        if p.exists():
            if name.endswith(".php"):
                resp, _ = serve_php(p)
                return resp, 403
            return serve_static(p, "/" + name)[0], 403
    return Response("<h1>403 Forbidden</h1><p>Access denied.</p>", 403, mimetype="text/html")


@app.errorhandler(404)
def not_found(_):
    code_dir = config.code_dir
    for name in ("404.php", "404.html"):
        p = code_dir / name
        if p.exists():
            if name.endswith(".php"):
                resp, _ = serve_php(p)
                return resp, 404
            return serve_static(p, "/" + name)[0], 404
    return Response("<h1>404 Not Found</h1>", 404, mimetype="text/html")


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": f"File exceeds {config.max_upload_mb}MB limit"}), 413


@app.errorhandler(500)
def server_error(e):
    logger.exception("Internal error")
    return Response(f"<h1>500 Internal Server Error</h1><pre>{e}</pre>", 500, mimetype="text/html")
