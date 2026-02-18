"""
tests/test_server.py — PHPyServer unit & integration tests
Run: pytest tests/ -v
"""
import os
import re
import sys
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Point to project root
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Minimal env so app.py doesn't error on import ────────────────────────────
os.environ.setdefault("CODE_DIR", str(Path(__file__).parent.parent / "code"))

from app import app, FileCache, HtaccessParser, PHPExecutor


# ─── FileCache tests ──────────────────────────────────────────────────────────

class TestFileCache(unittest.TestCase):

    def test_set_and_get(self):
        c = FileCache(ttl=10)
        c.set("k", "value")
        self.assertEqual(c.get("k"), "value")

    def test_ttl_expiry(self):
        c = FileCache(ttl=0)   # instant expiry
        c.set("k", "value")
        time.sleep(0.01)
        self.assertIsNone(c.get("k"))

    def test_invalidate(self):
        c = FileCache(ttl=60)
        c.set("k", "value")
        c.invalidate("k")
        self.assertIsNone(c.get("k"))

    def test_clear(self):
        c = FileCache(ttl=60)
        c.set("a", 1); c.set("b", 2)
        c.clear()
        self.assertEqual(c.size, 0)

    def test_size(self):
        c = FileCache(ttl=60)
        c.set("x", 1); c.set("y", 2)
        self.assertEqual(c.size, 2)


# ─── HtaccessParser tests ─────────────────────────────────────────────────────

class TestHtaccessParser(unittest.TestCase):

    def _parser_with(self, content: str) -> HtaccessParser:
        td = tempfile.mkdtemp()
        p  = Path(td)
        (p / ".htaccess").write_text(content)
        parser = HtaccessParser(p)
        return parser

    def test_simple_rewrite(self):
        parser = self._parser_with(
            "RewriteEngine On\nRewriteRule ^blog$ blog.php [L]\n"
        )
        rewritten, code = parser.apply_rewrites("/blog")
        self.assertEqual(rewritten, "blog.php")
        self.assertIsNone(code)

    def test_redirect_301(self):
        parser = self._parser_with(
            "RewriteEngine On\nRewriteRule ^old$ /new [R=301,L]\n"
        )
        rewritten, code = parser.apply_rewrites("/old")
        self.assertEqual(code, 301)
        self.assertEqual(rewritten, "/new")

    def test_redirect_directive(self):
        parser = self._parser_with("Redirect 301 /old-page /new-page\n")
        rewritten, code = parser.apply_rewrites("/old-page")
        self.assertEqual(code, 301)
        self.assertEqual(rewritten, "/new-page")

    def test_no_match(self):
        parser = self._parser_with(
            "RewriteEngine On\nRewriteRule ^blog$ blog.php [L]\n"
        )
        path, code = parser.apply_rewrites("/about")
        self.assertEqual(path, "/about")
        self.assertIsNone(code)

    def test_hidden_file_denied(self):
        parser = self._parser_with("")
        self.assertTrue(parser.is_denied(".htpasswd"))
        self.assertTrue(parser.is_denied(".env"))

    def test_normal_file_not_denied(self):
        parser = self._parser_with("")
        self.assertFalse(parser.is_denied("index.php"))
        self.assertFalse(parser.is_denied("style.css"))

    def test_backreference_rewrite(self):
        parser = self._parser_with(
            "RewriteEngine On\nRewriteRule ^post/([0-9]+)$ post.php?id=$1 [L]\n"
        )
        path, code = parser.apply_rewrites("/post/42")
        self.assertIn("42", path)
        self.assertIsNone(code)

    def test_comment_lines_ignored(self):
        parser = self._parser_with(
            "# This is a comment\nRewriteEngine On\n# Another comment\n"
        )
        self.assertEqual(len(parser.rules), 0)


# ─── Flask integration tests ──────────────────────────────────────────────────

class TestFlaskRoutes(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health_endpoint(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["status"], "ok")
        self.assertIn("php", data)

    def test_api_info(self):
        r = self.client.get("/api/info")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["server"], "PHPyServer")

    def test_cache_clear(self):
        r = self.client.delete("/api/cache")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["status"], "cleared")

    def test_hidden_file_forbidden(self):
        r = self.client.get("/.htpasswd")
        self.assertEqual(r.status_code, 403)

    def test_upload_no_file(self):
        r = self.client.post("/upload", data={})
        self.assertEqual(r.status_code, 400)

    def test_static_css(self):
        r = self.client.get("/style.css")
        # 200 if file exists, 404 if running without code/ dir
        self.assertIn(r.status_code, (200, 404))
        if r.status_code == 200:
            self.assertIn(b"body", r.data)

    def test_404_custom(self):
        r = self.client.get("/definitely-does-not-exist-xyz")
        self.assertEqual(r.status_code, 404)


# ─── PHPExecutor parse tests ──────────────────────────────────────────────────

class TestPHPExecutor(unittest.TestCase):

    def setUp(self):
        td = tempfile.mkdtemp()
        self.executor = PHPExecutor("php", 30, Path(td))

    def test_parse_cgi_output_basic(self):
        raw = b"Content-Type: text/html\n\n<h1>Hello</h1>"
        headers, body = self.executor.parse_cgi_output(raw)
        self.assertEqual(body, b"<h1>Hello</h1>")
        self.assertIn("Content-Type", headers)

    def test_parse_cgi_output_status(self):
        raw = b"Status: 404 Not Found\nContent-Type: text/html\n\nNot found"
        headers, body = self.executor.parse_cgi_output(raw)
        self.assertEqual(headers["_status"], 404)

    def test_parse_cgi_output_no_headers(self):
        raw = b"plain body with no headers"
        headers, body = self.executor.parse_cgi_output(raw)
        self.assertEqual(body, raw)

    def test_parse_cgi_crlf(self):
        raw = b"Content-Type: text/plain\r\n\r\nBody here"
        headers, body = self.executor.parse_cgi_output(raw)
        self.assertEqual(body, b"Body here")


if __name__ == "__main__":
    unittest.main(verbosity=2)
