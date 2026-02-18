"""
run.py — PHPyServer startup script
Starts both servers in separate threads:
  • PHP Server  → http://localhost:5000  (your PHP site)
  • Admin Panel → http://localhost:8080  (control panel)

Usage:
  python run.py
"""

import sys
import time
import threading
import shutil

from core import config, htaccess, logger

# ─── Startup checks ───────────────────────────────────────────────────────────

def check_php():
    binary = config.php_binary
    if shutil.which(binary):
        import subprocess
        try:
            r = subprocess.run([binary, "-v"], capture_output=True, text=True, timeout=3)
            version = r.stdout.split("\n")[0] if r.returncode == 0 else "unknown"
            return True, version
        except Exception:
            return True, "PHP (version unknown)"
    return False, None


def print_banner(php_ok: bool, php_version: str):
    php_status = f"✅  {php_version}" if php_ok else "❌  PHP not found — install PHP and check PHP_BINARY in .env"
    code_dir   = config.code_dir

    print(f"""
╔══════════════════════════════════════════════════════════╗
║              🐘  PHPyServer — Starting Up                ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  PHP Site   →  http://{config.get('HOST')}:{config.get('PORT'):<5}                      ║
║  Admin UI   →  http://{config.get('ADMIN_HOST')}:{config.get('ADMIN_PORT'):<5}                      ║
║                                                          ║
║  Code dir:  {str(code_dir)[:44]:<44}  ║
║  PHP:       {php_status[:44]:<44}  ║
║  Debug:     {'ON ⚡' if config.debug else 'OFF':<44}  ║
║                                                          ║
║  Press  Ctrl+C  to stop                                  ║
╚══════════════════════════════════════════════════════════╝
""")


# ─── Server runners ───────────────────────────────────────────────────────────

def run_php_server():
    from server import app
    app.config["MAX_CONTENT_LENGTH"] = config.max_upload_mb * 1024 * 1024
    app.config["SECRET_KEY"]         = config.get("SECRET_KEY", "dev-secret")
    app.run(
        host=config.get("HOST", "127.0.0.1"),
        port=int(config.get("PORT", 5000)),
        debug=False,       # We handle debug ourselves
        threaded=True,
        use_reloader=False,
    )


def run_admin_server():
    from admin import admin
    admin.secret_key = config.get("SECRET_KEY", "admin-secret")
    admin.run(
        host=config.get("ADMIN_HOST", "127.0.0.1"),
        port=int(config.get("ADMIN_PORT", 8080)),
        debug=False,
        threaded=True,
        use_reloader=False,
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Ensure code dir exists
    code_dir = config.code_dir
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "uploads").mkdir(exist_ok=True)

    # Load .htaccess at startup
    htaccess.load(code_dir)

    # Pre-flight checks
    php_ok, php_version = check_php()
    print_banner(php_ok, php_version or "")

    if not php_ok:
        print("⚠️  Warning: PHP not found. PHP files will return 503 errors.")
        print(f"   Set PHP_BINARY in .env to your PHP path, or install PHP.")
        print()

    # Start both servers in daemon threads
    t1 = threading.Thread(target=run_php_server,   name="PHPServer",  daemon=True)
    t2 = threading.Thread(target=run_admin_server,  name="AdminPanel", daemon=True)

    t1.start()
    time.sleep(0.3)  # slight stagger so port-bind logs don't interleave
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋  PHPyServer stopped. Goodbye!\n")
        sys.exit(0)
