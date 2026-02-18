"""
core.py — Shared state and utilities used by both the PHP server and admin panel.
Everything lives here so both Flask apps (port 5000 & 8080) share the same objects.
"""

import os
import re
import time
import base64
import hashlib
import logging
import mimetypes
import subprocess
import threading
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv, set_key, dotenv_values

# ─── Logging ──────────────────────────────────────────────────────────────────

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("phpyserver")

_file_handler = logging.FileHandler("logs/access.log")
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(_file_handler)


# ─── Config ───────────────────────────────────────────────────────────────────

ENV_FILE = Path(".env")

DEFAULTS = {
    "HOST":          "127.0.0.1",
    "PORT":          "5000",
    "ADMIN_HOST":    "127.0.0.1",
    "ADMIN_PORT":    "8080",
    "DEBUG":         "false",
    "CODE_DIR":      "code",
    "PHP_BINARY":    "php",
    "PHP_TIMEOUT":   "30",
    "MAX_UPLOAD_MB": "10",
    "CACHE_TTL":     "60",
    "LOG_FILE":      "logs/access.log",
    "SECRET_KEY":    "change-me-in-production",
}

# Setting metadata for the admin UI
SETTING_META = {
    "HOST":          {"label": "Server Host",        "desc": "IP address to bind the PHP server to. Use 0.0.0.0 to accept connections from any device.",       "type": "text"},
    "PORT":          {"label": "Server Port",        "desc": "Port for the main PHP server. Default is 5000.",                                                   "type": "number"},
    "ADMIN_HOST":    {"label": "Admin Host",         "desc": "IP address to bind the admin panel to.",                                                           "type": "text"},
    "ADMIN_PORT":    {"label": "Admin Panel Port",   "desc": "Port for this admin panel. Default is 8080.",                                                      "type": "number"},
    "DEBUG":         {"label": "Debug Mode",         "desc": "When true, shows PHP errors, enables auto-reload, and prints verbose logs.",                       "type": "bool"},
    "CODE_DIR":      {"label": "Code Directory",     "desc": "Folder containing your PHP/HTML files. Acts like Apache's DocumentRoot.",                         "type": "text"},
    "PHP_BINARY":    {"label": "PHP Binary",         "desc": "Path to your PHP CLI executable. Usually 'php', 'php8.2', or a full path like /usr/bin/php.",     "type": "text"},
    "PHP_TIMEOUT":   {"label": "PHP Timeout (sec)",  "desc": "Maximum seconds a PHP script can run before it's forcefully stopped.",                             "type": "number"},
    "MAX_UPLOAD_MB": {"label": "Max Upload (MB)",    "desc": "Maximum file upload size in megabytes.",                                                           "type": "number"},
    "CACHE_TTL":     {"label": "Cache TTL (sec)",    "desc": "How long static files (CSS, JS, images) stay in memory cache. 0 disables caching.",               "type": "number"},
    "LOG_FILE":      {"label": "Log File Path",      "desc": "Where access logs are written. Relative to the project root.",                                     "type": "text"},
    "SECRET_KEY":    {"label": "Secret Key",         "desc": "Flask session secret. Change this to a random string in production!",                             "type": "password"},
}


class Config:
    """Live config that reads from .env, with hot-reload support."""
    _lock = threading.Lock()

    def __init__(self):
        self._values: dict = {}
        self.load()

    def load(self):
        with self._lock:
            load_dotenv(ENV_FILE, override=True)
            self._values = {k: os.getenv(k, v) for k, v in DEFAULTS.items()}
            # Apply debug level
            if self._values["DEBUG"].lower() == "true":
                logger.setLevel(logging.DEBUG)

    def get(self, key: str, fallback=None):
        return self._values.get(key, fallback)

    def all(self) -> dict:
        return dict(self._values)

    def save(self, updates: dict):
        """Write updates to .env file and reload."""
        if not ENV_FILE.exists():
            ENV_FILE.write_text("")
        for k, v in updates.items():
            if k in DEFAULTS:
                set_key(str(ENV_FILE), k, str(v))
        self.load()

    # Convenience properties
    @property
    def code_dir(self) -> Path:
        return Path(self._values["CODE_DIR"]).resolve()

    @property
    def php_binary(self) -> str:
        return self._values["PHP_BINARY"]

    @property
    def php_timeout(self) -> int:
        return int(self._values["PHP_TIMEOUT"])

    @property
    def max_upload_mb(self) -> int:
        return int(self._values["MAX_UPLOAD_MB"])

    @property
    def cache_ttl(self) -> int:
        return int(self._values["CACHE_TTL"])

    @property
    def debug(self) -> bool:
        return self._values["DEBUG"].lower() == "true"

    @property
    def upload_dir(self) -> Path:
        return self.code_dir / "uploads"


# ─── Stats ────────────────────────────────────────────────────────────────────

class Stats:
    """Thread-safe request counters."""
    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = time.time()
        self.total_requests = 0
        self.php_executions = 0
        self.cache_hits = 0
        self.errors = 0
        self.recent: list = []  # last N log entries for dashboard

    def record(self, method: str, path: str, status: int, ms: float, kind: str = "static"):
        with self._lock:
            self.total_requests += 1
            if kind == "php":
                self.php_executions += 1
            elif kind == "cache":
                self.cache_hits += 1
            if status >= 400:
                self.errors += 1
            self.recent.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "method": method,
                "path": path,
                "status": status,
                "ms": round(ms, 1),
                "kind": kind,
            })
            self.recent = self.recent[-200:]  # keep last 200

    @property
    def uptime(self) -> str:
        s = int(time.time() - self.start_time)
        h, m = divmod(s, 3600)
        m, s = divmod(m, 60)
        return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total_requests": self.total_requests,
                "php_executions": self.php_executions,
                "cache_hits":     self.cache_hits,
                "errors":         self.errors,
                "uptime":         self.uptime,
                "recent":         list(self.recent[-50:]),
            }


# ─── In-Memory Cache ──────────────────────────────────────────────────────────

class FileCache:
    def __init__(self):
        self._store: dict = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl: int):
        with self._lock:
            entry = self._store.get(key)
            if entry and ttl > 0 and (time.time() - entry["ts"]) < ttl:
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
            n = len(self._store)
            self._store.clear()
            return n

    @property
    def size(self) -> int:
        return len(self._store)


# ─── .htaccess Parser ─────────────────────────────────────────────────────────

class HtaccessParser:
    def __init__(self):
        self.rules: list = []
        self.auth: dict = {}
        self.deny_all = False
        self.options: dict = {"indexes": True, "directoryindex": ["index.php", "index.html"]}
        self._lock = threading.Lock()
        self._mtime: float = 0

    def load(self, code_dir: Path):
        htaccess = code_dir / ".htaccess"
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

        rules, auth, options = [], {}, {"indexes": True, "directoryindex": ["index.php", "index.html"]}
        deny_all = False
        rewrite_on = False

        for raw in htaccess.read_text(errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            tokens = line.split()
            d = tokens[0].lower()

            if d == "rewriteengine":
                rewrite_on = len(tokens) > 1 and tokens[1].lower() == "on"
            elif d == "rewriterule" and rewrite_on and len(tokens) >= 3:
                flags = self._parse_flags(tokens[3] if len(tokens) > 3 else "")
                try:
                    rules.append({"type": "rewrite", "pattern": re.compile(tokens[1]),
                                  "raw_pattern": tokens[1], "target": tokens[2],
                                  "flags": flags, "raw_flags": tokens[3] if len(tokens) > 3 else ""})
                except re.error:
                    pass
            elif d == "redirect" and len(tokens) >= 3:
                try:
                    code = int(tokens[1])
                    src, dest = tokens[2], tokens[3] if len(tokens) > 3 else "/"
                except ValueError:
                    code, src, dest = 302, tokens[1], tokens[2]
                rules.append({"type": "redirect", "src": src, "dest": dest, "code": code})
            elif d == "authtype":
                auth["type"] = tokens[1] if len(tokens) > 1 else "Basic"
            elif d == "authname":
                auth["realm"] = " ".join(tokens[1:]).strip('"\'')
            elif d == "authuserfile":
                auth["userfile"] = tokens[1] if len(tokens) > 1 else ""
            elif d == "require":
                auth["require"] = tokens[1] if len(tokens) > 1 else "valid-user"
            elif d == "deny" and len(tokens) > 1:
                if tokens[-1].lower() == "all":
                    deny_all = True
            elif d == "options":
                for opt in tokens[1:]:
                    if opt.lstrip("+-").lower() == "indexes":
                        options["indexes"] = not opt.startswith("-")
            elif d == "directoryindex":
                options["directoryindex"] = tokens[1:]

        with self._lock:
            self.rules = rules
            self.auth = auth
            self.deny_all = deny_all
            self.options = options
            logger.info(f".htaccess loaded — {len(rules)} rules, auth={'yes' if auth else 'no'}")

    def force_reload(self, code_dir: Path):
        with self._lock:
            self._mtime = 0
        self.load(code_dir)

    @staticmethod
    def _parse_flags(s: str) -> dict:
        flags: dict = {}
        m = re.match(r"\[(.+)\]", s)
        if not m:
            return flags
        for f in m.group(1).split(","):
            f = f.strip()
            if "=" in f:
                k, v = f.split("=", 1)
                flags[k.upper()] = v
            else:
                flags[f.upper()] = True
        return flags

    def apply_rewrites(self, path: str) -> tuple:
        for rule in self.rules:
            if rule["type"] == "redirect":
                if path == rule["src"] or path.startswith(rule["src"]):
                    return rule["dest"], rule["code"]
            elif rule["type"] == "rewrite":
                m = rule["pattern"].match(path.lstrip("/"))
                if m:
                    target = rule["target"]
                    for i, g in enumerate(m.groups(), 1):
                        if g is not None:
                            target = target.replace(f"${i}", g)
                    flags = rule["flags"]
                    if "R" in flags:
                        code = 301 if flags["R"] is True else int(flags["R"])
                        return target, code
                    if "R=301" in " ".join(str(v) for v in flags):
                        return target, 301
                    if "L" in flags:
                        return target, None
        return path, None

    def check_auth(self, code_dir: Path) -> bool:
        from flask import request
        if not self.auth or "userfile" not in self.auth:
            return True
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth_header[6:]).decode()
            username, password = decoded.split(":", 1)
        except Exception:
            return False
        return self._verify_htpasswd(self.auth["userfile"], username, password, code_dir)

    def _verify_htpasswd(self, userfile: str, username: str, password: str, code_dir: Path) -> bool:
        fp = Path(userfile)
        if not fp.is_absolute():
            fp = code_dir / userfile
        if not fp.exists():
            return False
        for line in fp.read_text().splitlines():
            line = line.strip()
            if not line or ":" not in line or line.startswith("#"):
                continue
            u, h = line.split(":", 1)
            if u != username:
                continue
            if h.startswith("$apr1$") or h.startswith("$1$"):
                try:
                    from passlib.hash import apr_md5_crypt, md5_crypt
                    fn = apr_md5_crypt if h.startswith("$apr1$") else md5_crypt
                    return fn.verify(password, h)
                except ImportError:
                    return False
            if h.startswith("{SHA}"):
                import base64 as b64
                digest = b64.b64encode(hashlib.sha1(password.encode()).digest()).decode()
                return digest == h[5:]
            if h.startswith("$2y$") or h.startswith("$2b$"):
                try:
                    import bcrypt
                    return bcrypt.checkpw(password.encode(), h.replace("$2y$", "$2b$").encode())
                except ImportError:
                    return False
            return h == password  # plain text fallback
        return False

    def is_denied(self, path: str) -> bool:
        name = Path(path).name
        if name.startswith("."):
            return True
        return self.deny_all


# ─── PHP Executor ─────────────────────────────────────────────────────────────

class PHPExecutor:
    def __init__(self):
        self._available: bool | None = None

    def is_available(self, binary: str) -> bool:
        import shutil
        return shutil.which(binary) is not None

    def execute(self, script_path: Path, config: Config,
                query_string: str = "", post_data: bytes = b"") -> tuple:
        from flask import request
        env = {
            **os.environ,
            "DOCUMENT_ROOT":     str(config.code_dir),
            "SCRIPT_FILENAME":   str(script_path),
            "SCRIPT_NAME":       "/" + script_path.relative_to(config.code_dir).as_posix(),
            "REQUEST_URI":       request.path + ("?" + query_string if query_string else ""),
            "REQUEST_METHOD":    request.method,
            "QUERY_STRING":      query_string,
            "CONTENT_TYPE":      request.content_type or "",
            "CONTENT_LENGTH":    str(len(post_data)),
            "SERVER_NAME":       request.host.split(":")[0],
            "SERVER_PORT":       request.host.split(":")[-1] if ":" in request.host else "80",
            "SERVER_PROTOCOL":   "HTTP/1.1",
            "GATEWAY_INTERFACE": "CGI/1.1",
            "REMOTE_ADDR":       request.remote_addr or "127.0.0.1",
            "HTTP_HOST":         request.host,
            "HTTP_USER_AGENT":   request.user_agent.string,
            "HTTP_ACCEPT":       request.headers.get("Accept", ""),
            "HTTP_COOKIE":       "; ".join(f"{k}={v}" for k, v in request.cookies.items()),
            "REDIRECT_STATUS":   "200",
        }
        for h, v in request.headers:
            env["HTTP_" + h.upper().replace("-", "_")] = v

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [config.php_binary, "-f", str(script_path)],
                input=post_data, capture_output=True,
                timeout=config.php_timeout, env=env,
                cwd=str(script_path.parent),
            )
            ms = (time.perf_counter() - t0) * 1000
            logger.debug(f"PHP {script_path.name} → {ms:.1f}ms rc={proc.returncode}")
            return proc.stdout, proc.stderr.decode(errors="replace"), proc.returncode, ms
        except subprocess.TimeoutExpired:
            return b"", "Timeout", -1, config.php_timeout * 1000
        except FileNotFoundError:
            return b"", f"PHP binary '{config.php_binary}' not found", -2, 0

    @staticmethod
    def parse_cgi_output(raw: bytes) -> tuple:
        sep = b"\r\n\r\n" if b"\r\n\r\n" in raw else b"\n\n"
        if sep in raw:
            head_raw, body = raw.split(sep, 1)
        else:
            return {"_status": 200}, raw
        headers: dict = {"_status": 200}
        for line in head_raw.decode(errors="replace").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip()
                if k.lower() == "status":
                    try:
                        headers["_status"] = int(v.split()[0])
                    except ValueError:
                        pass
                else:
                    headers[k] = v
        return headers, body


# ─── Module-level singletons (shared between both Flask apps) ─────────────────

config  = Config()
cache   = FileCache()
stats   = Stats()
htaccess = HtaccessParser()
php     = PHPExecutor()

# Static file extensions that can be cached
STATIC_EXTS = {
    ".html", ".htm", ".css", ".js", ".json", ".txt", ".xml",
    ".svg", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".mp4", ".webm",
    ".pdf", ".zip", ".csv", ".map",
}

# Text file extensions editable in the admin file manager
TEXT_EXTS = {
    ".php", ".html", ".htm", ".css", ".js", ".json", ".txt",
    ".xml", ".md", ".htaccess", ".htpasswd", ".env", ".csv",
    ".svg", ".yaml", ".yml", ".ini", ".conf", ".sh",
}


def safe_path(rel: str, code_dir: Path) -> Path | None:
    """Resolve path inside code_dir, blocking traversal attacks."""
    try:
        p = (code_dir / rel.lstrip("/")).resolve()
        p.relative_to(code_dir)
        return p
    except (ValueError, OSError):
        return None


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"
