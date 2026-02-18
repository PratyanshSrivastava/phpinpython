"""
PHPyServer - High-performance PHP/Flask hybrid web server
Emulates Apache .htaccess features for seamless PHP development
"""

import os
import re
import sys
import time
import json
import base64
import hashlib
import logging
import mimetypes
import subprocess
import threading
from pathlib import Path
from functools import wraps
from datetime import datetime

from flask import (
    Flask, request, Response, send_file, jsonify,
    redirect, abort, render_template_string
)
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# ─── Bootstrap ────────────────────────────────────────────────────────────────

load_dotenv()

app = Flask(__name__)
app.config.update(
    CODE_DIR        = Path(os.getenv("CODE_DIR", "code")).resolve(),
    UPLOAD_DIR      = Path(os.getenv("UPLOAD_DIR", "code/uploads")).resolve(),
    LOG_FILE        = os.getenv("LOG_FILE", "logs/access.log"),
    PHP_BINARY      = os.getenv("PHP_BINARY", "php"),
    PHP_TIMEOUT     = int(os.getenv("PHP_TIMEOUT", 30)),
    MAX_UPLOAD_MB   = int(os.getenv("MAX_UPLOAD_MB", 10)),
    CACHE_TTL       = int(os.getenv("CACHE_TTL", 60)),
    SECRET_KEY      = os.getenv("SECRET_KEY", "dev-secret-change-me"),
    DEBUG           = os.getenv("DEBUG", "false").lower() == "true",
)
app.config["MAX_CONTENT_LENGTH"] = app.config["MAX_UPLOAD_MB"] * 1024 * 1024
app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────────────────────

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG if app.config["DEBUG"] else logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("phpyserver")

file_handler = logging.FileHandler(app.config["LOG_FILE"])
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))
logger.addHandler(file_handler)


# ─── In-Memory Cache ──────────────────────────────────────────────────────────

class FileCache:
    def __init__(self, ttl: int = 60):
        self._store: dict = {}
        self._lock = threading.Lock()
        self.ttl = ttl

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
            if entry and (time.time() - entry["ts"]) < self.ttl:
                return entry["data"]
            return None

    def set(self, key: str, data):
        with self._lock:
            self._store[key] = {"data": data, "ts": time.time()}

    def invalidate(self, key: str):
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        with self._lock:
            self._store.clear()

    @property
    def size(self):
        return len(self._store)


cache = FileCache(ttl=app.config["CACHE_TTL"])


# ─── .htaccess Parser ─────────────────────────────────────────────────────────

class HtaccessParser:
    """Parse and apply Apache .htaccess directives."""

    def __init__(self, code_dir: Path):
        self.code_dir = code_dir
        self.rules: list = []
        self.auth: dict = {}
        self.deny_patterns: list = []
        self.options: dict = {}
        self._lock = threading.Lock()
        self._mtime: float = 0
        self._htpasswd_cache: dict = {}
        self.load()

    def load(self):
        htaccess = self.code_dir / ".htaccess"
        if not htaccess.exists():
            return

        try:
            mtime = htaccess.stat().st_mtime
        except OSError:
            return

        with self._lock:
            if mtime == self._mtime:
                return
            self._mtime = mtime
            self.rules.clear()
            self.auth.clear()
            self.deny_patterns.clear()
            self.options.clear()

            rewrite_base = ""
            rewrite_on = False
            auth_block: dict = {}

            for raw_line in htaccess.read_text(errors="replace").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                tokens = line.split()
                directive = tokens[0].lower()

                if directive == "rewriteengine":
                    rewrite_on = tokens[1].lower() == "on" if len(tokens) > 1 else False

                elif directive == "rewritebase":
                    rewrite_base = tokens[1] if len(tokens) > 1 else ""

                elif directive == "rewriterule" and rewrite_on and len(tokens) >= 3:
                    pattern, target = tokens[1], tokens[2]
                    flags_str = tokens[3] if len(tokens) > 3 else ""
                    flags = self._parse_flags(flags_str)
                    self.rules.append({
                        "type": "rewrite",
                        "pattern": re.compile(pattern),
                        "target": target,
                        "flags": flags,
                        "base": rewrite_base,
                    })

                elif directive == "rewritecond":
                    pass  # Basic implementation; conditions logged but not enforced

                elif directive == "redirect" and len(tokens) >= 3:
                    code_or_path = tokens[1]
                    try:
                        code = int(code_or_path)
                        src, dest = tokens[2], tokens[3] if len(tokens) > 3 else "/"
                    except ValueError:
                        code, src, dest = 302, code_or_path, tokens[2]
                    self.rules.append({
                        "type": "redirect",
                        "src": src,
                        "dest": dest,
                        "code": code,
                    })

                elif directive == "authtype":
                    auth_block["type"] = tokens[1] if len(tokens) > 1 else "Basic"

                elif directive == "authname":
                    auth_block["realm"] = " ".join(tokens[1:]).strip('"\'')

                elif directive == "authuserfile":
                    auth_block["userfile"] = tokens[1] if len(tokens) > 1 else ""

                elif directive == "require":
                    auth_block["require"] = tokens[1] if len(tokens) > 1 else "valid-user"

                elif directive == "deny" and len(tokens) > 1:
                    val = tokens[2] if len(tokens) > 2 else tokens[1]
                    if val == "all":
                        self.deny_patterns.append("*")
                    else:
                        self.deny_patterns.append(val)

                elif directive == "options":
                    for opt in tokens[1:]:
                        if opt.startswith("-"):
                            self.options[opt[1:].lower()] = False
                        elif opt.startswith("+"):
                            self.options[opt[1:].lower()] = True
                        else:
                            self.options[opt.lower()] = True

                elif directive == "directoryindex":
                    self.options["directoryindex"] = tokens[1:]

            if "type" in auth_block:
                self.auth = auth_block

            logger.info(
                f".htaccess loaded: {len(self.rules)} rules, "
                f"auth={'yes' if self.auth else 'no'}, "
                f"deny_patterns={self.deny_patterns}"
            )

    @staticmethod
    def _parse_flags(flags_str: str) -> dict:
        flags: dict = {}
        match = re.match(r"\[(.+)\]", flags_str)
        if not match:
            return flags
        for f in match.group(1).split(","):
            f = f.strip()
            if "=" in f:
                k, v = f.split("=", 1)
                flags[k.upper()] = v
            else:
                flags[f.upper()] = True
        return flags

    def apply_rewrites(self, path: str) -> tuple:
        """
        Apply rewrite/redirect rules to path.
        Returns (new_path, redirect_code_or_None).
        """
        self.load()  # hot-reload on change
        for rule in self.rules:
            if rule["type"] == "redirect":
                if path == rule["src"] or path.startswith(rule["src"]):
                    return rule["dest"], rule["code"]

            elif rule["type"] == "rewrite":
                m = rule["pattern"].match(path.lstrip("/"))
                if m:
                    target = rule["target"]
                    # Back-references $1, $2 …
                    for i, g in enumerate(m.groups(), 1):
                        if g is not None:
                            target = target.replace(f"${i}", g)
                    flags = rule["flags"]
                    if "R" in flags or "R=301" in flags or "R=302" in flags:
                        code = 301 if flags.get("R") is True else int(flags.get("R", 302))
                        return target, code
                    if "L" in flags:
                        return target, None
        return path, None

    def check_auth(self, path: str) -> bool:
        """Return True if auth passes or no auth required."""
        if not self.auth:
            return True
        userfile = self.auth.get("userfile", "")
        if not userfile:
            return True

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False

        try:
            decoded = base64.b64decode(auth_header[6:]).decode()
            username, password = decoded.split(":", 1)
        except Exception:
            return False

        return self._verify_htpasswd(userfile, username, password)

    def _verify_htpasswd(self, userfile: str, username: str, password: str) -> bool:
        fp = Path(userfile)
        if not fp.is_absolute():
            fp = self.code_dir / userfile
        if not fp.exists():
            return False

        for line in fp.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            u, h = line.split(":", 1)
            if u != username:
                continue

            # APR1-MD5 ($apr1$)
            if h.startswith("$apr1$"):
                try:
                    from passlib.hash import apr_md5_crypt
                    return apr_md5_crypt.verify(password, h)
                except ImportError:
                    logger.warning("passlib not installed; APR1-MD5 auth unavailable")
                    return False

            # Plain MD5 (legacy)
            if h.startswith("$1$"):
                try:
                    from passlib.hash import md5_crypt
                    return md5_crypt.verify(password, h)
                except ImportError:
                    return False

            # SHA1 {SHA}
            if h.startswith("{SHA}"):
                import hashlib, base64 as b64
                digest = b64.b64encode(hashlib.sha1(password.encode()).digest()).decode()
                return digest == h[5:]

            # Bcrypt
            if h.startswith("$2y$") or h.startswith("$2b$"):
                try:
                    import bcrypt
                    return bcrypt.checkpw(password.encode(), h.replace("$2y$", "$2b$").encode())
                except ImportError:
                    return False

            # Plain text (development only)
            return h == password

        return False

    def is_denied(self, path: str) -> bool:
        """Return True if the path is explicitly denied."""
        self.load()
        name = Path(path).name
        # Always deny hidden files (.htaccess, .htpasswd, etc.)
        if name.startswith("."):
            return True
        for pat in self.deny_patterns:
            if pat == "*":
                return True
        return False


# ─── PHP Executor ─────────────────────────────────────────────────────────────

class PHPExecutor:
    """Execute PHP scripts via CLI subprocess."""

    def __init__(self, php_bin: str, timeout: int, code_dir: Path):
        self.php_bin = php_bin
        self.timeout = timeout
        self.code_dir = code_dir

    def execute(self, script_path: Path, query_string: str = "",
                post_data: bytes = b"", extra_env: dict = None) -> tuple:
        """
        Run PHP script. Returns (stdout_bytes, stderr_str, returncode).
        """
        env = {
            **os.environ,
            "DOCUMENT_ROOT":    str(self.code_dir),
            "SCRIPT_FILENAME":  str(script_path),
            "SCRIPT_NAME":      "/" + script_path.relative_to(self.code_dir).as_posix(),
            "REQUEST_URI":      request.path + ("?" + query_string if query_string else ""),
            "REQUEST_METHOD":   request.method,
            "QUERY_STRING":     query_string,
            "CONTENT_TYPE":     request.content_type or "",
            "CONTENT_LENGTH":   str(len(post_data)),
            "SERVER_NAME":      request.host.split(":")[0],
            "SERVER_PORT":      request.host.split(":")[-1] if ":" in request.host else "80",
            "SERVER_PROTOCOL":  "HTTP/1.1",
            "GATEWAY_INTERFACE":"CGI/1.1",
            "REMOTE_ADDR":      request.remote_addr or "127.0.0.1",
            "HTTP_HOST":        request.host,
            "HTTP_USER_AGENT":  request.user_agent.string,
            "HTTP_ACCEPT":      request.headers.get("Accept", ""),
            "HTTP_COOKIE":      "; ".join(
                f"{k}={v}" for k, v in request.cookies.items()
            ),
            "REDIRECT_STATUS":  "200",   # required for CGI mode
        }

        # Forward all HTTP_ headers
        for h, v in request.headers:
            key = "HTTP_" + h.upper().replace("-", "_")
            env[key] = v

        if extra_env:
            env.update(extra_env)

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [self.php_bin, "-f", str(script_path)],
                input=post_data,
                capture_output=True,
                timeout=self.timeout,
                env=env,
                cwd=str(script_path.parent),
            )
            elapsed = (time.perf_counter() - t0) * 1000
            logger.debug(f"PHP {script_path.name} → {elapsed:.1f}ms, rc={proc.returncode}")
            return proc.stdout, proc.stderr.decode(errors="replace"), proc.returncode

        except subprocess.TimeoutExpired:
            logger.warning(f"PHP timeout after {self.timeout}s: {script_path}")
            return b"", "Timeout", -1
        except FileNotFoundError:
            logger.error(f"PHP binary not found: {self.php_bin}")
            return b"", f"PHP binary '{self.php_bin}' not found", -2

    def parse_cgi_output(self, raw: bytes) -> tuple:
        """
        Split CGI output into (headers_dict, body_bytes).
        PHP outputs headers then blank line then body.
        """
        # Find header/body split
        sep = b"\r\n\r\n" if b"\r\n\r\n" in raw else b"\n\n"
        if sep in raw:
            head_raw, body = raw.split(sep, 1)
        else:
            return {}, raw

        headers: dict = {}
        status = 200
        for line in head_raw.decode(errors="replace").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k, v = k.strip(), v.strip()
                if k.lower() == "status":
                    try:
                        status = int(v.split()[0])
                    except ValueError:
                        pass
                else:
                    headers[k] = v

        return {"_status": status, **headers}, body


# ─── Directory Indexer ────────────────────────────────────────────────────────

DIR_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Index of {{ path }}</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; background: #f5f5f5; color: #333; }
    header { background: #1a1a2e; color: #eee; padding: 1.2rem 2rem; }
    header h1 { margin: 0; font-size: 1.4rem; }
    table { width: 100%; border-collapse: collapse; background: #fff; }
    th { background: #16213e; color: #ddd; text-align: left; padding: .7rem 1.5rem; font-size: .85rem; }
    td { padding: .6rem 1.5rem; border-bottom: 1px solid #eee; font-size: .9rem; }
    tr:hover td { background: #f0f4ff; }
    a { color: #0366d6; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .size { color: #666; }
    .dir  { color: #e36b00; font-weight: 600; }
    .php  { color: #8993be; }
    footer { padding: 1rem 2rem; color: #999; font-size: .8rem; }
  </style>
</head>
<body>
  <header><h1>📁 Index of {{ path }}</h1></header>
  <table>
    <tr><th>Name</th><th>Size</th><th>Modified</th></tr>
    {% if parent %}
    <tr><td><a href="{{ parent }}">⬆ Parent Directory</a></td><td></td><td></td></tr>
    {% endif %}
    {% for entry in entries %}
    <tr>
      <td>
        {% if entry.is_dir %}
        <span class="dir">📂</span> <a href="{{ entry.href }}">{{ entry.name }}/</a>
        {% elif entry.name.endswith('.php') %}
        <span class="php">🐘</span> <a href="{{ entry.href }}">{{ entry.name }}</a>
        {% else %}
        📄 <a href="{{ entry.href }}">{{ entry.name }}</a>
        {% endif %}
      </td>
      <td class="size">{{ entry.size }}</td>
      <td>{{ entry.mtime }}</td>
    </tr>
    {% endfor %}
  </table>
  <footer>PHPyServer • {{ now }}</footer>
</body>
</html>"""


def render_dir_index(fs_path: Path, url_path: str) -> str:
    entries = []
    try:
        items = sorted(fs_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        items = []

    for item in items:
        if item.name.startswith("."):
            continue
        href = url_path.rstrip("/") + "/" + item.name
        size = ""
        if item.is_file():
            s = item.stat().st_size
            size = f"{s:,} B" if s < 1024 else f"{s/1024:.1f} KB"
        mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        entries.append({"name": item.name, "href": href, "is_dir": item.is_dir(),
                        "size": size, "mtime": mtime})

    parent = str(Path(url_path).parent) if url_path != "/" else None
    return render_template_string(
        DIR_TEMPLATE,
        path=url_path,
        entries=entries,
        parent=parent,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ─── Singletons ───────────────────────────────────────────────────────────────

htaccess = HtaccessParser(app.config["CODE_DIR"])
php = PHPExecutor(
    app.config["PHP_BINARY"],
    app.config["PHP_TIMEOUT"],
    app.config["CODE_DIR"],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def log_request(path: str, status: int, duration_ms: float):
    logger.info(
        f'{request.remote_addr} "{request.method} {path}" '
        f'{status} {duration_ms:.1f}ms'
    )


def require_auth(realm: str):
    return Response(
        "Authentication required.",
        401,
        {"WWW-Authenticate": f'Basic realm="{realm}"'},
    )


def safe_path(rel: str) -> Path | None:
    """Resolve path inside CODE_DIR, guarding traversal."""
    try:
        p = (app.config["CODE_DIR"] / rel.lstrip("/")).resolve()
        p.relative_to(app.config["CODE_DIR"])
        return p
    except (ValueError, OSError):
        return None


STATIC_EXTENSIONS = {
    ".html", ".htm", ".css", ".js", ".json", ".txt", ".xml",
    ".svg", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".mp4", ".webm",
    ".pdf", ".zip", ".csv", ".map",
}


def serve_static(fs_path: Path, url_path: str):
    key = str(fs_path)
    cached = cache.get(key)
    if cached:
        mime = cached["mime"]
        data = cached["data"]
    else:
        try:
            data = fs_path.read_bytes()
        except OSError:
            abort(404)
        mime = mimetypes.guess_type(fs_path.name)[0] or "application/octet-stream"
        if fs_path.suffix in STATIC_EXTENSIONS:
            cache.set(key, {"data": data, "mime": mime})

    resp = Response(data, mimetype=mime)
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


def serve_php(fs_path: Path):
    post_data = request.get_data()
    stdout, stderr, rc = php.execute(
        fs_path,
        query_string=request.query_string.decode(),
        post_data=post_data,
    )

    if rc == -2:
        return Response(
            "<h1>503 – PHP Not Available</h1>"
            f"<pre>Binary: {app.config['PHP_BINARY']}\n{stderr}</pre>",
            503, mimetype="text/html"
        )
    if rc == -1:
        return Response("<h1>504 – PHP Timeout</h1>", 504, mimetype="text/html")

    if stderr and app.config["DEBUG"]:
        logger.debug(f"PHP stderr:\n{stderr}")

    headers, body = php.parse_cgi_output(stdout)
    status = headers.pop("_status", 200)

    # Handle Location header (PHP redirect)
    if "Location" in headers:
        resp = redirect(headers["Location"], code=status if status in (301, 302, 303, 307, 308) else 302)
        return resp

    mime = headers.pop("Content-Type", "text/html; charset=UTF-8")
    resp = Response(body, status=status, mimetype=mime)
    for k, v in headers.items():
        try:
            resp.headers[k] = v
        except Exception:
            pass
    return resp


# ─── API Endpoints ────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    """Health check endpoint."""
    import shutil
    php_ok = shutil.which(app.config["PHP_BINARY"]) is not None
    return jsonify({
        "status":       "ok",
        "php":          "available" if php_ok else "not found",
        "php_binary":   app.config["PHP_BINARY"],
        "cache_entries":cache.size,
        "code_dir":     str(app.config["CODE_DIR"]),
        "timestamp":    datetime.utcnow().isoformat() + "Z",
    })


@app.route("/upload", methods=["POST"])
def upload():
    """Multipart file upload endpoint."""
    if "file" not in request.files:
        return jsonify({"error": "No file field in request"}), 400

    uploaded = request.files.getlist("file")
    saved = []
    errors = []

    for f in uploaded:
        if not f.filename:
            continue
        name = secure_filename(f.filename)
        dest = app.config["UPLOAD_DIR"] / name
        try:
            f.save(dest)
            saved.append({"filename": name, "size": dest.stat().st_size})
        except Exception as e:
            errors.append({"filename": name, "error": str(e)})

    return jsonify({"saved": saved, "errors": errors}), 200 if saved else 400


@app.route("/api/cache", methods=["DELETE"])
def clear_cache():
    """Clear the in-memory static file cache."""
    cache.clear()
    return jsonify({"status": "cleared"})


@app.route("/api/info")
def server_info():
    """Return server configuration info."""
    return jsonify({
        "server":       "PHPyServer",
        "php_binary":   app.config["PHP_BINARY"],
        "php_timeout":  app.config["PHP_TIMEOUT"],
        "max_upload":   f"{app.config['MAX_UPLOAD_MB']}MB",
        "cache_ttl":    app.config["CACHE_TTL"],
        "debug":        app.config["DEBUG"],
    })


# ─── Main Request Handler ─────────────────────────────────────────────────────

@app.route("/", defaults={"url_path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
@app.route("/<path:url_path>",             methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def catch_all(url_path: str):
    t0 = time.perf_counter()
    original_path = "/" + url_path

    # ── 1. .htaccess hot-reload & deny hidden files ───────────────────────────
    if htaccess.is_denied(url_path):
        elapsed = (time.perf_counter() - t0) * 1000
        log_request(original_path, 403, elapsed)
        abort(403)

    # ── 2. Apply rewrites / redirects ─────────────────────────────────────────
    rewritten, redir_code = htaccess.apply_rewrites(original_path)
    if redir_code:
        elapsed = (time.perf_counter() - t0) * 1000
        log_request(original_path, redir_code, elapsed)
        return redirect(rewritten, code=redir_code)

    # Use the rewritten path for file lookup
    lookup_path = rewritten if rewritten != original_path else original_path

    # ── 3. Basic auth ─────────────────────────────────────────────────────────
    if not htaccess.check_auth(lookup_path):
        elapsed = (time.perf_counter() - t0) * 1000
        log_request(original_path, 401, elapsed)
        realm = htaccess.auth.get("realm", "Restricted")
        return require_auth(realm)

    # ── 4. Resolve filesystem path ────────────────────────────────────────────
    fs_path = safe_path(lookup_path)
    if fs_path is None:
        abort(403)

    # ── 5. Directory handling ──────────────────────────────────────────────────
    if fs_path.is_dir():
        index_files = htaccess.options.get("directoryindex", ["index.php", "index.html"])
        for idx in index_files:
            candidate = fs_path / idx
            if candidate.exists():
                fs_path = candidate
                break
        else:
            # Auto-index
            if htaccess.options.get("indexes", True):
                html = render_dir_index(fs_path, "/" + url_path)
                elapsed = (time.perf_counter() - t0) * 1000
                log_request(original_path, 200, elapsed)
                return Response(html, mimetype="text/html")
            else:
                abort(403)

    # ── 6. Pretty URLs: /blog → blog.php ──────────────────────────────────────
    if not fs_path.exists():
        php_candidate = fs_path.with_suffix(".php")
        if php_candidate.exists():
            fs_path = php_candidate
        else:
            # Try appending .php to the raw path
            alt = safe_path(lookup_path.rstrip("/") + ".php")
            if alt and alt.exists():
                fs_path = alt
            else:
                elapsed = (time.perf_counter() - t0) * 1000
                log_request(original_path, 404, elapsed)
                abort(404)

    # ── 7. Serve ───────────────────────────────────────────────────────────────
    suffix = fs_path.suffix.lower()

    if suffix == ".php":
        resp = serve_php(fs_path)
        status = resp.status_code
    elif suffix in STATIC_EXTENSIONS or suffix:
        resp = serve_static(fs_path, lookup_path)
        status = 200
    else:
        resp = serve_static(fs_path, lookup_path)
        status = 200

    elapsed = (time.perf_counter() - t0) * 1000
    log_request(original_path, status, elapsed)
    return resp


# ─── Error Handlers ───────────────────────────────────────────────────────────

@app.errorhandler(403)
def forbidden(e):
    return Response("<h1>403 Forbidden</h1>", 403, mimetype="text/html")


@app.errorhandler(404)
def not_found(e):
    # Check for custom 404 PHP/HTML
    for name in ("404.php", "404.html"):
        p = app.config["CODE_DIR"] / name
        if p.exists():
            if name.endswith(".php"):
                return serve_php(p), 404
            return serve_static(p, "/" + name), 404
    return Response("<h1>404 Not Found</h1>", 404, mimetype="text/html")


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": f"Upload exceeds {app.config['MAX_UPLOAD_MB']}MB limit"}), 413


@app.errorhandler(500)
def internal_error(e):
    logger.exception("Internal server error")
    return Response("<h1>500 Internal Server Error</h1>", 500, mimetype="text/html")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "127.0.0.1")

    logger.info(f"PHPyServer starting on http://{host}:{port}")
    logger.info(f"Code directory: {app.config['CODE_DIR']}")
    logger.info(f"PHP binary:     {app.config['PHP_BINARY']}")
    logger.info(f"Debug mode:     {app.config['DEBUG']}")

    app.run(
        host=host,
        port=port,
        debug=app.config["DEBUG"],
        threaded=True,
        use_reloader=app.config["DEBUG"],
    )
