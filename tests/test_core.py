"""
tests/test_core.py — PHPyServer unit tests
Run:  pytest tests/ -v
"""
import os
import re
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Set minimal env before importing app modules
os.environ.setdefault("CODE_DIR", str(Path(__file__).parent.parent / "code"))

from core import FileCache, HtaccessParser, PHPExecutor, Config, Stats, format_size


# ─── FileCache ────────────────────────────────────────────────────────────────

class TestFileCache(unittest.TestCase):

    def setUp(self):
        self.cache = FileCache()

    def test_basic_set_get(self):
        self.cache.set("key1", "hello")
        self.assertEqual(self.cache.get("key1", ttl=60), "hello")

    def test_ttl_zero_no_cache(self):
        self.cache.set("key2", "data")
        # TTL=0 means disabled, always returns None
        self.assertIsNone(self.cache.get("key2", ttl=0))

    def test_expired(self):
        self.cache.set("key3", "data")
        time.sleep(0.05)
        # Very short TTL — should be expired
        result = self.cache.get("key3", ttl=0.01)
        self.assertIsNone(result)

    def test_invalidate(self):
        self.cache.set("key4", "data")
        self.cache.invalidate("key4")
        self.assertIsNone(self.cache.get("key4", ttl=60))

    def test_clear(self):
        self.cache.set("a", 1)
        self.cache.set("b", 2)
        n = self.cache.clear()
        self.assertEqual(n, 2)
        self.assertEqual(self.cache.size, 0)

    def test_size(self):
        self.cache.set("x", 1)
        self.cache.set("y", 2)
        self.assertEqual(self.cache.size, 2)


# ─── HtaccessParser ───────────────────────────────────────────────────────────

def make_parser(content: str) -> HtaccessParser:
    td = Path(tempfile.mkdtemp())
    (td / ".htaccess").write_text(content)
    p = HtaccessParser()
    p.load(td)
    return p


class TestHtaccessParser(unittest.TestCase):

    def test_simple_rewrite(self):
        p = make_parser("RewriteEngine On\nRewriteRule ^blog$ blog.php [L]\n")
        path, code = p.apply_rewrites("/blog")
        self.assertEqual(path, "blog.php")
        self.assertIsNone(code)

    def test_no_match(self):
        p = make_parser("RewriteEngine On\nRewriteRule ^blog$ blog.php [L]\n")
        path, code = p.apply_rewrites("/about")
        self.assertEqual(path, "/about")
        self.assertIsNone(code)

    def test_redirect_301_via_rule(self):
        p = make_parser("RewriteEngine On\nRewriteRule ^old$ /new [R=301,L]\n")
        _, code = p.apply_rewrites("/old")
        self.assertEqual(code, 301)

    def test_redirect_directive(self):
        p = make_parser("Redirect 301 /old /new\n")
        dest, code = p.apply_rewrites("/old")
        self.assertEqual(code, 301)
        self.assertEqual(dest, "/new")

    def test_backreference(self):
        p = make_parser("RewriteEngine On\nRewriteRule ^post/([0-9]+)$ post.php?id=$1 [L]\n")
        path, code = p.apply_rewrites("/post/42")
        self.assertIn("42", path)
        self.assertIsNone(code)

    def test_deny_hidden_files(self):
        p = make_parser("")
        self.assertTrue(p.is_denied(".htpasswd"))
        self.assertTrue(p.is_denied(".env"))
        self.assertTrue(p.is_denied(".htaccess"))

    def test_allow_normal_files(self):
        p = make_parser("")
        self.assertFalse(p.is_denied("index.php"))
        self.assertFalse(p.is_denied("style.css"))

    def test_deny_all(self):
        p = make_parser("Deny from all\n")
        self.assertTrue(p.deny_all)

    def test_comments_ignored(self):
        p = make_parser("# This is a comment\nRewriteEngine On\n# Another\n")
        self.assertEqual(len(p.rules), 0)

    def test_directory_index(self):
        p = make_parser("DirectoryIndex index.php index.html default.php\n")
        self.assertEqual(p.options["directoryindex"], ["index.php", "index.html", "default.php"])

    def test_options_indexes(self):
        p = make_parser("Options +Indexes\n")
        self.assertTrue(p.options.get("indexes", False))

    def test_options_no_indexes(self):
        p = make_parser("Options -Indexes\n")
        self.assertFalse(p.options.get("indexes", True))

    def test_auth_parsed(self):
        p = make_parser("AuthType Basic\nAuthName \"Restricted\"\nAuthUserFile .htpasswd\nRequire valid-user\n")
        self.assertEqual(p.auth.get("realm"), "Restricted")
        self.assertEqual(p.auth.get("userfile"), ".htpasswd")

    def test_rewrite_disabled(self):
        p = make_parser("RewriteEngine Off\nRewriteRule ^blog$ blog.php [L]\n")
        self.assertEqual(len(p.rules), 0)


# ─── Stats ────────────────────────────────────────────────────────────────────

class TestStats(unittest.TestCase):

    def test_record_increments(self):
        s = Stats()
        s.record("GET", "/", 200, 10, "php")
        s.record("GET", "/css", 200, 2, "cache")
        self.assertEqual(s.total_requests, 2)
        self.assertEqual(s.php_executions, 1)
        self.assertEqual(s.cache_hits, 1)

    def test_errors_counted(self):
        s = Stats()
        s.record("GET", "/missing", 404, 1)
        s.record("GET", "/boom", 500, 1)
        self.assertEqual(s.errors, 2)

    def test_recent_capped(self):
        s = Stats()
        for i in range(250):
            s.record("GET", f"/{i}", 200, 1)
        self.assertLessEqual(len(s.recent), 200)

    def test_snapshot(self):
        s = Stats()
        s.record("GET", "/", 200, 5, "php")
        snap = s.snapshot()
        self.assertIn("total_requests", snap)
        self.assertIn("uptime", snap)
        self.assertIn("recent", snap)
        self.assertEqual(snap["php_executions"], 1)


# ─── PHPExecutor ─────────────────────────────────────────────────────────────

class TestPHPExecutorParsing(unittest.TestCase):

    def setUp(self):
        self.executor = PHPExecutor()

    def test_parse_basic(self):
        raw = b"Content-Type: text/html\n\n<h1>Hello</h1>"
        headers, body = self.executor.parse_cgi_output(raw)
        self.assertEqual(body, b"<h1>Hello</h1>")
        self.assertIn("Content-Type", headers)

    def test_parse_status(self):
        raw = b"Status: 404 Not Found\nContent-Type: text/html\n\nNot found"
        headers, body = self.executor.parse_cgi_output(raw)
        self.assertEqual(headers["_status"], 404)

    def test_parse_crlf(self):
        raw = b"Content-Type: text/plain\r\n\r\nBody"
        headers, body = self.executor.parse_cgi_output(raw)
        self.assertEqual(body, b"Body")

    def test_parse_no_headers(self):
        raw = b"just a plain body"
        headers, body = self.executor.parse_cgi_output(raw)
        self.assertEqual(body, raw)
        self.assertEqual(headers["_status"], 200)


# ─── Utilities ────────────────────────────────────────────────────────────────

class TestUtils(unittest.TestCase):

    def test_format_size_bytes(self):
        self.assertEqual(format_size(512), "512 B")

    def test_format_size_kb(self):
        result = format_size(2048)
        self.assertIn("KB", result)

    def test_format_size_mb(self):
        result = format_size(2 * 1024 * 1024)
        self.assertIn("MB", result)


# ─── Flask Routes ─────────────────────────────────────────────────────────────

class TestServerRoutes(unittest.TestCase):

    def setUp(self):
        from server import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health(self):
        r = self.client.get("/__health")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["status"], "ok")

    def test_hidden_file_denied(self):
        r = self.client.get("/.htpasswd")
        self.assertEqual(r.status_code, 403)

    def test_hidden_env_denied(self):
        r = self.client.get("/.env")
        self.assertEqual(r.status_code, 403)

    def test_missing_file_404(self):
        r = self.client.get("/definitely-does-not-exist-xyz-abc")
        self.assertEqual(r.status_code, 404)

    def test_static_css(self):
        r = self.client.get("/style.css")
        self.assertIn(r.status_code, (200, 404))
        if r.status_code == 200:
            self.assertIn(b"body", r.data)


class TestAdminRoutes(unittest.TestCase):

    def setUp(self):
        from admin import admin
        admin.config["TESTING"] = True
        admin.secret_key = "test"
        self.client = admin.test_client()

    def test_dashboard(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"PHPyServer", r.data)

    def test_settings_page(self):
        r = self.client.get("/settings")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Settings", r.data)

    def test_files_page(self):
        r = self.client.get("/files")
        self.assertEqual(r.status_code, 200)

    def test_htaccess_page(self):
        r = self.client.get("/htaccess")
        self.assertEqual(r.status_code, 200)

    def test_logs_page(self):
        r = self.client.get("/logs")
        self.assertEqual(r.status_code, 200)

    def test_users_page(self):
        r = self.client.get("/users")
        self.assertEqual(r.status_code, 200)

    def test_api_stats(self):
        r = self.client.get("/api/stats")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("total_requests", data)

    def test_cache_clear(self):
        r = self.client.post("/cache/clear")
        self.assertIn(r.status_code, (200, 302))


if __name__ == "__main__":
    unittest.main(verbosity=2)
