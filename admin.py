"""
admin.py — PHPyServer Admin Panel (localhost:8080)
A beginner-friendly control panel for managing your PHP development server.
"""

import os
import re
import json
import time
import shutil
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime

from flask import (
    Flask, request, redirect, url_for,
    jsonify, render_template_string, flash, session
)

from core import (
    config, cache, stats, htaccess, php,
    SETTING_META, TEXT_EXTS, safe_path, format_size, logger,
)

admin = Flask(__name__)
admin.secret_key = config.get("SECRET_KEY", "admin-secret")


# ═══════════════════════════════════════════════════════════════════════════════
# LAYOUT HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def layout(content: str, page: str = "", title: str = "PHPyServer Admin") -> str:
    php_ok = php.is_available(config.php_binary)
    php_badge = (
        '<span class="badge badge-green">PHP OK</span>'
        if php_ok else
        '<span class="badge badge-red">PHP Missing</span>'
    )
    nav_items = [
        ("dashboard", "🏠", "Dashboard",      "/"),
        ("settings",  "⚙️", "Settings",       "/settings"),
        ("files",     "📁", "File Manager",   "/files"),
        ("htaccess",  "🔀", "Rewrite Rules",  "/htaccess"),
        ("users",     "👥", "Users & Auth",   "/users"),
        ("logs",      "📋", "Logs",           "/logs"),
        ("phpinfo",   "🐘", "PHP Info",       "/phpinfo"),
    ]
    nav_html = ""
    for key, icon, label, href in nav_items:
        active = "nav-active" if page == key else ""
        nav_html += f'<a href="{href}" class="nav-item {active}">{icon} <span>{label}</span></a>\n'

    # Flash messages
    flashes = ""
    for cat, msg in (session.pop("_flashes", None) or []):
        color = "flash-green" if cat == "success" else "flash-red"
        flashes += f'<div class="flash {color}">{msg}</div>'

    return render_template_string(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — PHPyServer Admin</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/dracula.min.css">
  <style>
    /* ── Reset & base ─────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --sidebar:   #0f172a;
      --sidebar2:  #1e293b;
      --accent:    #6366f1;
      --accent-h:  #4f46e5;
      --green:     #22c55e;
      --red:       #ef4444;
      --yellow:    #f59e0b;
      --bg:        #f1f5f9;
      --card:      #ffffff;
      --border:    #e2e8f0;
      --text:      #1e293b;
      --muted:     #64748b;
      --radius:    10px;
    }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg);
      color: var(--text); display: flex; min-height: 100vh; }}

    /* ── Sidebar ───────────────────────────────────────── */
    .sidebar {{ width: 220px; min-height: 100vh; background: var(--sidebar);
      display: flex; flex-direction: column; flex-shrink: 0; position: sticky; top: 0; height: 100vh; overflow-y: auto; }}
    .sidebar-logo {{ padding: 1.4rem 1.2rem; border-bottom: 1px solid #1e293b; }}
    .sidebar-logo h2 {{ font-size: 1rem; color: #f8fafc; font-weight: 700; letter-spacing: .02em; }}
    .sidebar-logo p {{ font-size: .72rem; color: #94a3b8; margin-top: .15rem; }}
    .nav-section {{ padding: .5rem .8rem .2rem; font-size: .7rem; color: #475569;
      text-transform: uppercase; letter-spacing: .08em; margin-top: .5rem; }}
    .nav-item {{ display: flex; align-items: center; gap: .6rem; padding: .6rem 1rem;
      color: #94a3b8; text-decoration: none; font-size: .88rem; border-radius: 7px;
      margin: .1rem .5rem; transition: background .15s, color .15s; }}
    .nav-item:hover  {{ background: #1e293b; color: #f1f5f9; }}
    .nav-active      {{ background: var(--accent) !important; color: #fff !important; }}
    .sidebar-footer  {{ margin-top: auto; padding: 1rem; border-top: 1px solid #1e293b; }}
    .sidebar-footer a {{ font-size: .78rem; color: #64748b; text-decoration: none; display: block; margin-bottom: .3rem; }}
    .sidebar-footer a:hover {{ color: #94a3b8; }}

    /* ── Main area ─────────────────────────────────────── */
    .main {{ flex: 1; display: flex; flex-direction: column; min-width: 0; }}
    .topbar {{ background: var(--card); border-bottom: 1px solid var(--border);
      padding: .8rem 1.8rem; display: flex; align-items: center; justify-content: space-between; }}
    .topbar h1 {{ font-size: 1.1rem; font-weight: 600; }}
    .topbar-right {{ display: flex; align-items: center; gap: 1rem; font-size: .82rem; color: var(--muted); }}
    .content {{ padding: 1.8rem; flex: 1; }}

    /* ── Cards ─────────────────────────────────────────── */
    .card {{ background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 1.4rem; margin-bottom: 1.2rem; }}
    .card-title {{ font-size: .85rem; font-weight: 600; color: var(--muted);
      text-transform: uppercase; letter-spacing: .05em; margin-bottom: 1rem; }}

    /* ── Stat cards ────────────────────────────────────── */
    .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 1.4rem; }}
    .stat-card {{ background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 1.2rem; text-align: center; }}
    .stat-card .num {{ font-size: 2rem; font-weight: 700; color: var(--accent); line-height: 1; }}
    .stat-card .lbl {{ font-size: .78rem; color: var(--muted); margin-top: .35rem; }}
    .stat-card.green .num {{ color: var(--green); }}
    .stat-card.red   .num {{ color: var(--red); }}
    .stat-card.yellow .num {{ color: var(--yellow); }}

    /* ── Tables ────────────────────────────────────────── */
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; padding: .55rem 1rem; font-size: .78rem; color: var(--muted);
      background: #f8fafc; border-bottom: 1px solid var(--border);
      text-transform: uppercase; letter-spacing: .04em; }}
    td {{ padding: .6rem 1rem; border-bottom: 1px solid #f1f5f9; font-size: .875rem; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #f8fafc; }}
    .table-wrapper {{ border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; background: var(--card); }}

    /* ── Forms ─────────────────────────────────────────── */
    .form-group {{ margin-bottom: 1.2rem; }}
    label {{ display: block; font-size: .85rem; font-weight: 500; margin-bottom: .35rem; }}
    .form-desc {{ font-size: .78rem; color: var(--muted); margin-bottom: .4rem; }}
    input[type=text], input[type=number], input[type=password],
    input[type=email], select, textarea {{
      width: 100%; padding: .5rem .8rem; border: 1px solid var(--border);
      border-radius: 6px; font-family: inherit; font-size: .9rem;
      background: #f8fafc; color: var(--text); transition: border-color .15s; }}
    input:focus, select:focus, textarea:focus {{
      outline: none; border-color: var(--accent); background: #fff; }}
    textarea {{ min-height: 120px; resize: vertical; }}

    /* ── Buttons ───────────────────────────────────────── */
    .btn {{ display: inline-flex; align-items: center; gap: .4rem; padding: .5rem 1.1rem;
      border: none; border-radius: 6px; font-size: .875rem; font-weight: 500;
      cursor: pointer; text-decoration: none; transition: background .15s, opacity .15s; }}
    .btn-primary {{ background: var(--accent); color: #fff; }}
    .btn-primary:hover {{ background: var(--accent-h); }}
    .btn-secondary {{ background: #f1f5f9; color: var(--text); border: 1px solid var(--border); }}
    .btn-secondary:hover {{ background: var(--border); }}
    .btn-danger {{ background: #fef2f2; color: var(--red); border: 1px solid #fecaca; }}
    .btn-danger:hover {{ background: #fee2e2; }}
    .btn-green {{ background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }}
    .btn-green:hover {{ background: #dcfce7; }}
    .btn-sm {{ padding: .3rem .7rem; font-size: .8rem; }}
    .btn-group {{ display: flex; gap: .6rem; flex-wrap: wrap; }}

    /* ── Badges ────────────────────────────────────────── */
    .badge {{ display: inline-block; padding: .2rem .6rem; border-radius: 20px;
      font-size: .72rem; font-weight: 600; }}
    .badge-green  {{ background: #dcfce7; color: #16a34a; }}
    .badge-red    {{ background: #fee2e2; color: #dc2626; }}
    .badge-yellow {{ background: #fef9c3; color: #854d0e; }}
    .badge-blue   {{ background: #dbeafe; color: #1d4ed8; }}
    .badge-purple {{ background: #ede9fe; color: #6d28d9; }}
    .badge-gray   {{ background: #f1f5f9; color: #475569; }}

    /* ── Flash messages ────────────────────────────────── */
    .flash {{ padding: .75rem 1rem; border-radius: 7px; margin-bottom: 1rem; font-size: .88rem; }}
    .flash-green {{ background: #f0fdf4; border: 1px solid #bbf7d0; color: #15803d; }}
    .flash-red   {{ background: #fef2f2; border: 1px solid #fecaca; color: #dc2626; }}

    /* ── Log viewer ────────────────────────────────────── */
    .log-box {{ background: #0f172a; color: #94a3b8; font-family: 'Cascadia Code', 'Fira Code', monospace;
      font-size: .8rem; padding: 1rem; border-radius: var(--radius);
      max-height: 500px; overflow-y: auto; line-height: 1.6; }}
    .log-200 {{ color: #4ade80; }}
    .log-3xx {{ color: #60a5fa; }}
    .log-4xx {{ color: #fb923c; }}
    .log-5xx {{ color: #f87171; }}

    /* ── File manager ──────────────────────────────────── */
    .fm-grid {{ display: grid; grid-template-columns: 260px 1fr; gap: 1rem; align-items: start; }}
    .fm-tree {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }}
    .fm-tree-header {{ padding: .7rem 1rem; background: #f8fafc; border-bottom: 1px solid var(--border); font-size: .8rem; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }}
    .fm-item {{ display: flex; align-items: center; gap: .5rem; padding: .45rem 1rem;
      font-size: .85rem; cursor: pointer; text-decoration: none; color: var(--text);
      border-bottom: 1px solid #f8fafc; transition: background .1s; }}
    .fm-item:hover {{ background: #f1f5f9; }}
    .fm-item.active {{ background: #ede9fe; color: var(--accent); font-weight: 500; }}
    .fm-item-name {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .fm-badge {{ font-size: .68rem; }}
    .editor-wrap .CodeMirror {{ height: 420px; font-size: .85rem; border-radius: 0 0 var(--radius) var(--radius); }}

    /* ── Responsive ────────────────────────────────────── */
    @media (max-width: 768px) {{
      .sidebar {{ width: 56px; }}
      .sidebar .nav-item span, .sidebar-logo p, .nav-section, .sidebar-footer a {{ display: none; }}
      .fm-grid {{ grid-template-columns: 1fr; }}
    }}

    /* ── Misc ──────────────────────────────────────────── */
    .row {{ display: flex; gap: 1.2rem; }}
    .row > * {{ flex: 1; }}
    code {{ background: #f1f5f9; padding: .15rem .4rem; border-radius: 4px; font-size: .83em; color: #6d28d9; }}
    .section-title {{ font-size: 1.05rem; font-weight: 600; margin-bottom: .8rem; }}
    .help {{ font-size: .8rem; color: var(--muted); margin-top: 1rem; }}
    hr {{ border: none; border-top: 1px solid var(--border); margin: 1.2rem 0; }}
    .status-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: .4rem; }}
    .dot-green  {{ background: var(--green); }}
    .dot-red    {{ background: var(--red); }}
    .dot-yellow {{ background: var(--yellow); }}
  </style>
</head>
<body>

<!-- SIDEBAR -->
<nav class="sidebar">
  <div class="sidebar-logo">
    <h2>🐘 PHPyServer</h2>
    <p>Admin Panel v1.0</p>
  </div>
  <div class="nav-section">Navigation</div>
  {nav_html}
  <div class="sidebar-footer">
    <a href="http://{config.get('HOST')}:{config.get('PORT')}" target="_blank">🌐 Open Site :5000</a>
    <a href="http://{config.get('HOST')}:{config.get('PORT')}/__health" target="_blank">💚 Health Check</a>
  </div>
</nav>

<!-- MAIN -->
<div class="main">
  <div class="topbar">
    <h1>{'Dashboard' if not title or title == 'PHPyServer Admin' else title}</h1>
    <div class="topbar-right">
      {php_badge}
      <span>⏱ Uptime: <strong id="uptime-val">{stats.uptime}</strong></span>
      <span>📦 Cache: <strong>{cache.size}</strong> entries</span>
    </div>
  </div>
  <div class="content">
    {flashes}
    {content}
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/php/php.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/htmlmixed/htmlmixed.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/css/css.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/javascript/javascript.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/matchbrackets.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/closebrackets.min.js"></script>
</body>
</html>""")


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

# ── Dashboard ─────────────────────────────────────────────────────────────────

@admin.route("/")
def dashboard():
    snap = stats.snapshot()
    php_ok = php.is_available(config.php_binary)

    # Recent requests table rows
    rows = ""
    for r in reversed(snap["recent"][-30:]):
        if r["status"] < 300:
            s_class = "badge-green"
        elif r["status"] < 400:
            s_class = "badge-blue"
        elif r["status"] < 500:
            s_class = "badge-yellow"
        else:
            s_class = "badge-red"
        kind_badge = {
            "php":    "<span class='badge badge-purple'>PHP</span>",
            "cache":  "<span class='badge badge-blue'>cache</span>",
            "static": "<span class='badge badge-gray'>static</span>",
        }.get(r["kind"], "")
        rows += f"""<tr>
          <td>{r['time']}</td>
          <td><code>{r['method']}</code></td>
          <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{r['path']}</td>
          <td><span class="badge {s_class}">{r['status']}</span></td>
          <td>{r['ms']}ms</td>
          <td>{kind_badge}</td>
        </tr>"""

    php_version = ""
    if php_ok:
        try:
            result = subprocess.run([config.php_binary, "-v"], capture_output=True, text=True, timeout=3)
            php_version = result.stdout.split("\n")[0] if result.returncode == 0 else "unknown"
        except Exception:
            php_version = "PHP (available)"

    content = f"""
    <div class="stats-grid">
      <div class="stat-card">
        <div class="num">{snap['total_requests']}</div>
        <div class="lbl">Total Requests</div>
      </div>
      <div class="stat-card">
        <div class="num">{snap['php_executions']}</div>
        <div class="lbl">PHP Executions</div>
      </div>
      <div class="stat-card green">
        <div class="num">{snap['cache_hits']}</div>
        <div class="lbl">Cache Hits</div>
      </div>
      <div class="stat-card {'red' if snap['errors'] > 0 else ''}">
        <div class="num">{snap['errors']}</div>
        <div class="lbl">Errors</div>
      </div>
      <div class="stat-card">
        <div class="num" style="font-size:1.2rem">{cache.size}</div>
        <div class="lbl">Cached Files</div>
      </div>
    </div>

    <div class="row">
      <div class="card" style="flex:2">
        <div class="card-title">Recent Requests</div>
        <div class="table-wrapper" style="border:none">
          <table>
            <tr><th>Time</th><th>Method</th><th>Path</th><th>Status</th><th>Duration</th><th>Type</th></tr>
            {rows if rows else '<tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:2rem">No requests yet — visit <a href="http://{config.get("HOST")}:{config.get("PORT")}" target="_blank">localhost:{config.get("PORT")}</a></td></tr>'}
          </table>
        </div>
        <div style="margin-top:.8rem">
          <a href="/logs" class="btn btn-secondary btn-sm">📋 View full logs</a>
          <button onclick="location.reload()" class="btn btn-secondary btn-sm">🔄 Refresh</button>
        </div>
      </div>

      <div style="flex:1;display:flex;flex-direction:column;gap:1rem">
        <div class="card">
          <div class="card-title">Server Status</div>
          <div style="font-size:.88rem;line-height:2">
            <div><span class="status-dot {'dot-green' if php_ok else 'dot-red'}"></span>PHP: {'✅ ' + php_version.split(' ')[1] if php_ok and php_version else '❌ Not found'}</div>
            <div><span class="status-dot dot-green"></span>Flask server running</div>
            <div><span class="status-dot dot-green"></span>Port: <code>{config.get('PORT')}</code></div>
            <div><span class="status-dot dot-green"></span>Code dir: <code>{config.get('CODE_DIR')}</code></div>
            <div><span class="status-dot {'dot-green' if config.cache_ttl > 0 else 'dot-yellow'}"></span>
              Cache: {'TTL ' + str(config.cache_ttl) + 's' if config.cache_ttl > 0 else 'disabled'}</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">Quick Actions</div>
          <div style="display:flex;flex-direction:column;gap:.6rem">
            <a href="http://{config.get('HOST')}:{config.get('PORT')}" target="_blank" class="btn btn-primary">🌐 Open PHP Site</a>
            <form method="POST" action="/cache/clear">
              <button class="btn btn-secondary" style="width:100%">🗑️ Clear Cache ({cache.size} entries)</button>
            </form>
            <form method="POST" action="/htaccess/reload">
              <button class="btn btn-secondary" style="width:100%">🔄 Reload .htaccess</button>
            </form>
            <a href="/files" class="btn btn-secondary">📁 File Manager</a>
          </div>
        </div>
      </div>
    </div>
    """
    return layout(content, "dashboard", "Dashboard")


# ── Settings ──────────────────────────────────────────────────────────────────

@admin.route("/settings", methods=["GET", "POST"])
def settings():
    message = ""
    if request.method == "POST":
        updates = {}
        from core import DEFAULTS
        for key in DEFAULTS:
            val = request.form.get(key, "").strip()
            if val != "":
                updates[key] = val
            elif key == "DEBUG":
                updates[key] = "false"
        config.save(updates)
        admin.secret_key = config.get("SECRET_KEY", "admin-secret")
        flash("Settings saved! Some changes (like port) require a server restart.", "success")
        return redirect(url_for("settings"))

    current = config.all()

    # Build settings form
    fields_html = ""
    groups = [
        ("🌐 Server",      ["HOST", "PORT", "ADMIN_HOST", "ADMIN_PORT", "DEBUG"]),
        ("🐘 PHP",         ["PHP_BINARY", "PHP_TIMEOUT"]),
        ("📁 Files",       ["CODE_DIR"]),
        ("⚡ Performance", ["CACHE_TTL", "MAX_UPLOAD_MB"]),
        ("🔐 Security",    ["SECRET_KEY", "LOG_FILE"]),
    ]

    for group_name, keys in groups:
        fields_html += f'<div class="card"><div class="card-title">{group_name}</div>'
        for key in keys:
            meta = SETTING_META.get(key, {})
            val = current.get(key, "")
            label = meta.get("label", key)
            desc = meta.get("desc", "")
            typ = meta.get("type", "text")

            if typ == "bool":
                checked_t = "selected" if val.lower() == "true" else ""
                checked_f = "selected" if val.lower() == "false" else ""
                input_html = f"""<select name="{key}">
                  <option value="true" {checked_t}>✅ Enabled (true)</option>
                  <option value="false" {checked_f}>❌ Disabled (false)</option>
                </select>"""
            elif typ == "password":
                input_html = f'<input type="password" name="{key}" value="{val}" placeholder="(hidden)">'
            else:
                input_html = f'<input type="{typ}" name="{key}" value="{val}">'

            fields_html += f"""
            <div class="form-group">
              <label>{label} <code style="font-weight:400">{key}</code></label>
              <div class="form-desc">{desc}</div>
              {input_html}
            </div>"""
        fields_html += "</div>"

    content = f"""
    <form method="POST">
      {fields_html}
      <div class="btn-group">
        <button type="submit" class="btn btn-primary">💾 Save Settings</button>
        <a href="/" class="btn btn-secondary">Cancel</a>
      </div>
      <p class="help">⚠️ Changes to HOST, PORT, or ADMIN_PORT require restarting the server (<code>python run.py</code>) to take effect.</p>
    </form>
    """
    return layout(content, "settings", "Settings")


# ── File Manager ──────────────────────────────────────────────────────────────

@admin.route("/files")
@admin.route("/files/<path:rel_path>")
def files(rel_path: str = ""):
    code_dir = config.code_dir
    current_path = code_dir if not rel_path else (code_dir / rel_path)

    # Security check
    try:
        current_path.resolve().relative_to(code_dir)
    except ValueError:
        flash("Access denied.", "error")
        return redirect(url_for("files"))

    # Build file tree for sidebar (top level)
    def build_tree(base: Path, prefix: str = "") -> str:
        html = ""
        try:
            items = sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return html
        for item in items:
            icon = "📁" if item.is_dir() else _file_icon(item)
            item_rel = str(item.relative_to(code_dir))
            active = "active" if item_rel == rel_path or str(current_path) == str(item) else ""
            href = url_for("files", rel_path=item_rel)
            size_txt = format_size(item.stat().st_size) if item.is_file() else ""
            html += f"""<a href="{href}" class="fm-item {active}" title="{item.name}">
              <span>{icon}</span>
              <span class="fm-item-name" style="padding-left:{len(prefix)*8}px">{item.name}</span>
              <span class="fm-badge" style="color:#94a3b8">{size_txt}</span>
            </a>"""
            if item.is_dir() and item_rel in rel_path:
                html += build_tree(item, prefix + " ")
        return html

    tree_html = build_tree(code_dir)

    # Right panel: directory listing OR file editor
    if current_path.is_dir():
        panel = _dir_panel(current_path, rel_path, code_dir)
    elif current_path.is_file():
        panel = _file_editor(current_path, rel_path, code_dir)
    else:
        panel = '<div class="card"><p>File not found.</p></div>'

    # Breadcrumb
    parts = rel_path.split("/") if rel_path else []
    crumb = '<a href="/files">code/</a>'
    for i, part in enumerate(parts):
        crumb_path = "/".join(parts[:i+1])
        crumb += f' / <a href="/files/{crumb_path}">{part}</a>'

    content = f"""
    <div style="margin-bottom:1rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem">
      <div style="font-size:.9rem;color:var(--muted)">{crumb}</div>
      <div class="btn-group">
        <button onclick="document.getElementById('new-file-modal').style.display='flex'" class="btn btn-primary btn-sm">➕ New File</button>
        <button onclick="document.getElementById('new-folder-modal').style.display='flex'" class="btn btn-secondary btn-sm">📁 New Folder</button>
        <button onclick="document.getElementById('upload-modal').style.display='flex'" class="btn btn-secondary btn-sm">⬆️ Upload</button>
      </div>
    </div>

    <div class="fm-grid">
      <div>
        <div class="fm-tree">
          <div class="fm-tree-header">📁 code/</div>
          {tree_html}
        </div>
      </div>
      <div>{panel}</div>
    </div>

    <!-- New File Modal -->
    <div id="new-file-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:100;align-items:center;justify-content:center">
      <div style="background:#fff;border-radius:12px;padding:2rem;width:400px;max-width:90vw">
        <h3 style="margin-bottom:1rem">New File</h3>
        <form method="POST" action="/files/create">
          <input type="hidden" name="parent" value="{rel_path}">
          <input type="hidden" name="type" value="file">
          <div class="form-group">
            <label>Filename (e.g. <code>about.php</code>)</label>
            <input type="text" name="name" placeholder="filename.php" required autofocus>
          </div>
          <div class="btn-group">
            <button type="submit" class="btn btn-primary">Create</button>
            <button type="button" class="btn btn-secondary" onclick="document.getElementById('new-file-modal').style.display='none'">Cancel</button>
          </div>
        </form>
      </div>
    </div>

    <!-- New Folder Modal -->
    <div id="new-folder-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:100;align-items:center;justify-content:center">
      <div style="background:#fff;border-radius:12px;padding:2rem;width:400px;max-width:90vw">
        <h3 style="margin-bottom:1rem">New Folder</h3>
        <form method="POST" action="/files/create">
          <input type="hidden" name="parent" value="{rel_path}">
          <input type="hidden" name="type" value="folder">
          <div class="form-group">
            <label>Folder name</label>
            <input type="text" name="name" placeholder="my-folder" required autofocus>
          </div>
          <div class="btn-group">
            <button type="submit" class="btn btn-primary">Create</button>
            <button type="button" class="btn btn-secondary" onclick="document.getElementById('new-folder-modal').style.display='none'">Cancel</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Upload Modal -->
    <div id="upload-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:100;align-items:center;justify-content:center">
      <div style="background:#fff;border-radius:12px;padding:2rem;width:440px;max-width:90vw">
        <h3 style="margin-bottom:1rem">Upload Files</h3>
        <form method="POST" action="/files/upload" enctype="multipart/form-data">
          <input type="hidden" name="parent" value="{rel_path}">
          <div class="form-group">
            <input type="file" name="files" multiple>
          </div>
          <div class="btn-group">
            <button type="submit" class="btn btn-primary">Upload</button>
            <button type="button" class="btn btn-secondary" onclick="document.getElementById('upload-modal').style.display='none'">Cancel</button>
          </div>
        </form>
      </div>
    </div>
    """
    return layout(content, "files", "File Manager")


def _file_icon(p: Path) -> str:
    icons = {".php": "🐘", ".html": "🌐", ".css": "🎨", ".js": "⚡",
             ".json": "📋", ".md": "📝", ".txt": "📄",
             ".png": "🖼", ".jpg": "🖼", ".gif": "🖼", ".svg": "🖼",
             ".pdf": "📕", ".zip": "📦", ".htaccess": "🔀"}
    return icons.get(p.suffix.lower(), icons.get(p.name, "📄"))


def _dir_panel(path: Path, rel_path: str, code_dir: Path) -> str:
    try:
        items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return '<div class="card"><p>Permission denied.</p></div>'

    rows = ""
    for item in items:
        item_rel = str(item.relative_to(code_dir))
        icon = "📁" if item.is_dir() else _file_icon(item)
        size = format_size(item.stat().st_size) if item.is_file() else "—"
        mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        editable = item.is_file() and item.suffix.lower() in TEXT_EXTS
        preview_url = "/" + item_rel.replace("\\", "/")
        actions = f'<a href="/files/{item_rel}" class="btn btn-secondary btn-sm">{"✏️ Edit" if editable else "📂 Open"}</a>'
        if item.is_file():
            actions += f' <a href="{preview_url}" target="_blank" class="btn btn-secondary btn-sm">🌐 View</a>'
        actions += f''' <form method="POST" action="/files/delete" style="display:inline">
          <input type="hidden" name="path" value="{item_rel}">
          <button class="btn btn-danger btn-sm" onclick="return confirm('Delete {item.name}?')">🗑️</button>
        </form>'''
        rows += f"""<tr>
          <td>{icon} <a href="/files/{item_rel}">{item.name}</a></td>
          <td>{size}</td>
          <td style="color:#94a3b8">{mtime}</td>
          <td>{actions}</td>
        </tr>"""

    return f"""
    <div class="card">
      <div class="card-title">Contents of code/{rel_path or ''}</div>
      <div class="table-wrapper" style="border:none">
        <table>
          <tr><th>Name</th><th>Size</th><th>Modified</th><th>Actions</th></tr>
          {rows if rows else '<tr><td colspan="4" style="text-align:center;color:#94a3b8;padding:2rem">Empty folder</td></tr>'}
        </table>
      </div>
    </div>"""


def _file_editor(path: Path, rel_path: str, code_dir: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in TEXT_EXTS:
        size = format_size(path.stat().st_size)
        return f"""<div class="card">
          <div class="card-title">Binary File: {path.name}</div>
          <p>Size: {size}  |  Type: <code>{suffix}</code></p>
          <p class="help">Binary files cannot be edited here.</p>
        </div>"""

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f'<div class="card"><p>Cannot read file: {e}</p></div>'

    # CodeMirror mode
    mode_map = {
        ".php": "application/x-httpd-php", ".html": "htmlmixed", ".htm": "htmlmixed",
        ".css": "css", ".js": "javascript", ".json": "application/json",
    }
    cm_mode = mode_map.get(suffix, "text/plain")
    safe_content = content.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    preview_url = "/" + rel_path.replace("\\", "/")
    parent = str(Path(rel_path).parent).replace("\\", "/")
    back_url = f"/files/{parent}" if parent != "." else "/files"

    return f"""
    <div class="card" style="padding:0;overflow:hidden">
      <div style="padding:.8rem 1rem;background:#f8fafc;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem">
        <div style="font-weight:600;font-size:.95rem">{_file_icon(path)} {path.name}</div>
        <div class="btn-group">
          <a href="{preview_url}" target="_blank" class="btn btn-secondary btn-sm">🌐 Preview</a>
          <a href="{back_url}" class="btn btn-secondary btn-sm">← Back</a>
        </div>
      </div>
      <form method="POST" action="/files/save">
        <input type="hidden" name="path" value="{rel_path}">
        <div class="editor-wrap">
          <textarea id="editor" name="content" style="display:none">{content.replace('<', '&lt;')}</textarea>
          <div id="cm-editor"></div>
        </div>
        <div style="padding:.8rem 1rem;background:#f8fafc;border-top:1px solid var(--border);display:flex;gap:.6rem;align-items:center">
          <button type="submit" class="btn btn-primary">💾 Save File</button>
          <span style="font-size:.78rem;color:#94a3b8">{rel_path} — {format_size(path.stat().st_size)}</span>
        </div>
      </form>
    </div>
    <script>
    (function() {{
      var ta = document.getElementById('editor');
      var cm = CodeMirror(document.getElementById('cm-editor'), {{
        value: ta.textContent.replace(/&lt;/g, '<'),
        mode: "{cm_mode}",
        theme: "dracula",
        lineNumbers: true,
        matchBrackets: true,
        autoCloseBrackets: true,
        indentUnit: 2,
        tabSize: 2,
        lineWrapping: false,
        extraKeys: {{
          "Ctrl-S": function(cm) {{ cm.getTextArea().form.submit(); }},
          "Cmd-S":  function(cm) {{ cm.getTextArea().form.submit(); }},
        }}
      }});
      cm.on('change', function() {{ ta.value = cm.getValue(); }});
      // Init textarea value for form submit
      ta.value = cm.getValue();
    }})();
    </script>"""


@admin.route("/files/save", methods=["POST"])
def files_save():
    rel = request.form.get("path", "")
    content = request.form.get("content", "")
    code_dir = config.code_dir
    fs_path = safe_path(rel, code_dir)
    if not fs_path:
        flash("Invalid path.", "error")
        return redirect(url_for("files"))
    try:
        fs_path.write_text(content, encoding="utf-8")
        cache.invalidate(str(fs_path))
        if fs_path.name == ".htaccess":
            htaccess.force_reload(code_dir)
        flash(f"✅ {fs_path.name} saved!", "success")
    except OSError as e:
        flash(f"Error saving: {e}", "error")
    return redirect(url_for("files", rel_path=rel))


@admin.route("/files/create", methods=["POST"])
def files_create():
    parent = request.form.get("parent", "")
    name = request.form.get("name", "").strip()
    kind = request.form.get("type", "file")
    code_dir = config.code_dir

    if not name or "/" in name or "\\" in name or name.startswith("."):
        flash("Invalid name.", "error")
        return redirect(url_for("files", rel_path=parent))

    base = safe_path(parent, code_dir) if parent else code_dir
    if not base:
        flash("Invalid path.", "error")
        return redirect(url_for("files"))

    target = base / name
    try:
        if kind == "folder":
            target.mkdir(parents=True, exist_ok=True)
            flash(f"📁 Folder '{name}' created!", "success")
            rel = str(target.relative_to(code_dir))
        else:
            target.touch()
            flash(f"📄 File '{name}' created!", "success")
            rel = str(target.relative_to(code_dir))
    except OSError as e:
        flash(f"Error: {e}", "error")
        rel = parent

    return redirect(url_for("files", rel_path=rel.replace("\\", "/")))


@admin.route("/files/delete", methods=["POST"])
def files_delete():
    rel = request.form.get("path", "")
    code_dir = config.code_dir
    fs_path = safe_path(rel, code_dir)
    if not fs_path or not fs_path.exists():
        flash("File not found.", "error")
        return redirect(url_for("files"))
    try:
        if fs_path.is_dir():
            shutil.rmtree(fs_path)
        else:
            cache.invalidate(str(fs_path))
            fs_path.unlink()
        flash(f"🗑️ Deleted '{fs_path.name}'", "success")
    except OSError as e:
        flash(f"Error: {e}", "error")
    parent = str(Path(rel).parent).replace("\\", "/")
    return redirect(url_for("files", rel_path="" if parent == "." else parent))


@admin.route("/files/upload", methods=["POST"])
def files_upload():
    from werkzeug.utils import secure_filename as sf
    parent = request.form.get("parent", "")
    code_dir = config.code_dir
    dest_dir = safe_path(parent, code_dir) if parent else code_dir
    if not dest_dir:
        flash("Invalid path.", "error")
        return redirect(url_for("files"))
    saved = 0
    for f in request.files.getlist("files"):
        if f.filename:
            name = sf(f.filename)
            try:
                f.save(dest_dir / name)
                saved += 1
            except Exception:
                pass
    flash(f"✅ Uploaded {saved} file(s)!", "success")
    return redirect(url_for("files", rel_path=parent))


# ── .htaccess Editor ──────────────────────────────────────────────────────────

@admin.route("/htaccess", methods=["GET", "POST"])
def htaccess_page():
    code_dir = config.code_dir
    htaccess_path = code_dir / ".htaccess"

    if request.method == "POST":
        content = request.form.get("content", "")
        try:
            htaccess_path.write_text(content, encoding="utf-8")
            htaccess.force_reload(code_dir)
            flash("✅ .htaccess saved and reloaded!", "success")
        except OSError as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("htaccess_page"))

    content = htaccess_path.read_text(encoding="utf-8") if htaccess_path.exists() else ""
    safe_content = content.replace("<", "&lt;")

    # Parse rules for display
    htaccess.load(code_dir)
    rules_html = ""
    for r in htaccess.rules:
        if r["type"] == "rewrite":
            rules_html += f"""<tr>
              <td><span class="badge badge-purple">Rewrite</span></td>
              <td><code>{r['raw_pattern']}</code></td>
              <td><code>{r['target']}</code></td>
              <td><code>{r.get('raw_flags','')}</code></td>
            </tr>"""
        elif r["type"] == "redirect":
            rules_html += f"""<tr>
              <td><span class="badge badge-blue">Redirect {r['code']}</span></td>
              <td><code>{r['src']}</code></td>
              <td><code>{r['dest']}</code></td>
              <td>—</td>
            </tr>"""

    auth_info = ""
    if htaccess.auth:
        auth_info = f"""<div class="card">
          <div class="card-title">🔐 Auth Active</div>
          <p>Realm: <code>{htaccess.auth.get('realm', 'N/A')}</code> &nbsp;|&nbsp;
             File: <code>{htaccess.auth.get('userfile', 'N/A')}</code></p>
          <p class="help">Use the <a href="/users">Users page</a> to manage .htpasswd entries.</p>
        </div>"""

    page_content = f"""
    <div class="row">
      <div style="flex:1">
        <div class="card">
          <div class="card-title">📜 Current Rules ({len(htaccess.rules)})</div>
          {f'''<div class="table-wrapper" style="border:none">
            <table>
              <tr><th>Type</th><th>Pattern / From</th><th>Target / To</th><th>Flags</th></tr>
              {rules_html}
            </table>
          </div>''' if htaccess.rules else '<p style="color:#94a3b8">No rules found in .htaccess</p>'}
        </div>
        {auth_info}
        <div class="card">
          <div class="card-title">📖 Quick Reference</div>
          <div style="font-size:.83rem;line-height:1.9;color:var(--muted)">
            <code>RewriteEngine On</code> — Enable rewriting<br>
            <code>RewriteRule ^blog$ blog.php [L]</code> — /blog → blog.php<br>
            <code>RewriteRule ^post/([0-9]+)$ post.php?id=$1 [L]</code> — Capture group<br>
            <code>RewriteRule ^api/(.+)$ api.php [L]</code> — API passthrough<br>
            <code>Redirect 301 /old /new</code> — Permanent redirect<br>
            <code>Options +Indexes</code> — Enable directory listing<br>
            <code>Options -Indexes</code> — Disable directory listing<br>
            <code>DirectoryIndex index.php index.html</code> — Default files<br>
            <code>AuthType Basic</code> + <code>AuthUserFile .htpasswd</code> — Basic auth
          </div>
        </div>
      </div>

      <div style="flex:1.4">
        <form method="POST">
          <div class="card" style="padding:0;overflow:hidden">
            <div style="padding:.8rem 1rem;background:#f8fafc;border-bottom:1px solid var(--border);font-weight:600">
              ✏️ Edit .htaccess
            </div>
            <div class="editor-wrap">
              <textarea id="editor" name="content" style="display:none">{safe_content}</textarea>
              <div id="cm-editor"></div>
            </div>
            <div style="padding:.8rem 1rem;background:#f8fafc;border-top:1px solid var(--border);display:flex;gap:.6rem">
              <button type="submit" class="btn btn-primary">💾 Save & Reload</button>
            </div>
          </div>
        </form>
      </div>
    </div>

    <script>
    (function() {{
      var ta = document.getElementById('editor');
      var cm = CodeMirror(document.getElementById('cm-editor'), {{
        value: ta.textContent.replace(/&lt;/g,'<'),
        mode: "text/plain",
        theme: "dracula",
        lineNumbers: true,
        lineWrapping: true,
        extraKeys: {{"Ctrl-S": function(cm) {{ ta.value = cm.getValue(); cm.getTextArea().form.submit(); }} }}
      }});
      cm.on('change', function() {{ ta.value = cm.getValue(); }});
      ta.value = cm.getValue();
    }})();
    </script>
    """
    return layout(page_content, "htaccess", "Rewrite Rules")


@admin.route("/htaccess/reload", methods=["POST"])
def htaccess_reload():
    htaccess.force_reload(config.code_dir)
    flash("✅ .htaccess reloaded!", "success")
    return redirect(url_for("dashboard"))


# ── Users (.htpasswd) ─────────────────────────────────────────────────────────

@admin.route("/users", methods=["GET"])
def users():
    code_dir = config.code_dir
    htpasswd_path = code_dir / ".htpasswd"

    user_list = []
    if htpasswd_path.exists():
        for line in htpasswd_path.read_text().splitlines():
            line = line.strip()
            if line and ":" in line and not line.startswith("#"):
                u, h = line.split(":", 1)
                hash_type = (
                    "APR1-MD5" if h.startswith("$apr1$") else
                    "bcrypt"   if h.startswith("$2y$") or h.startswith("$2b$") else
                    "SHA1"     if h.startswith("{SHA}") else
                    "plain"
                )
                badge = {
                    "bcrypt": "badge-green", "APR1-MD5": "badge-blue",
                    "SHA1": "badge-yellow", "plain": "badge-red"
                }.get(hash_type, "badge-gray")
                user_list.append({"name": u, "hash_type": hash_type, "badge": badge})

    rows = ""
    for u in user_list:
        rows += f"""<tr>
          <td>👤 <strong>{u['name']}</strong></td>
          <td><span class="badge {u['badge']}">{u['hash_type']}</span></td>
          <td>
            <form method="POST" action="/users/delete" style="display:inline">
              <input type="hidden" name="username" value="{u['name']}">
              <button class="btn btn-danger btn-sm" onclick="return confirm('Remove {u['name']}?')">🗑️ Remove</button>
            </form>
          </td>
        </tr>"""

    auth_status = ""
    if htaccess.auth:
        auth_status = f"""<div class="flash flash-green">
          ✅ Basic auth is <strong>active</strong> in .htaccess — realm: <code>{htaccess.auth.get('realm','?')}</code>
        </div>"""
    else:
        auth_status = """<div class="flash flash-red">
          ⚠️ Basic auth is <strong>not enabled</strong> in .htaccess. Add these lines to enable it:
          <pre style="margin-top:.5rem;background:#fef2f2;padding:.5rem;border-radius:4px;font-size:.8rem">AuthType Basic
AuthName "Members Only"
AuthUserFile .htpasswd
Require valid-user</pre>
        </div>"""

    page_content = f"""
    {auth_status}
    <div class="row">
      <div style="flex:1.5">
        <div class="card">
          <div class="card-title">👥 Users ({len(user_list)})</div>
          {f'''<div class="table-wrapper" style="border:none">
            <table>
              <tr><th>Username</th><th>Hash Type</th><th>Actions</th></tr>
              {rows}
            </table>
          </div>''' if user_list else '<p style="color:#94a3b8">No users yet. Add one using the form.</p>'}
        </div>
      </div>

      <div style="flex:1">
        <div class="card">
          <div class="card-title">➕ Add User</div>
          <form method="POST" action="/users/add">
            <div class="form-group">
              <label>Username</label>
              <input type="text" name="username" required placeholder="alice">
            </div>
            <div class="form-group">
              <label>Password</label>
              <input type="password" name="password" required placeholder="••••••••">
            </div>
            <div class="form-group">
              <label>Hash Method</label>
              <div class="form-desc">bcrypt is the most secure. SHA1 is widely compatible.</div>
              <select name="method">
                <option value="bcrypt">bcrypt (recommended)</option>
                <option value="sha1">SHA1</option>
                <option value="plain">Plain text (dev only)</option>
              </select>
            </div>
            <button type="submit" class="btn btn-primary">Add User</button>
          </form>
        </div>

        <div class="card">
          <div class="card-title">📖 Notes</div>
          <div style="font-size:.82rem;color:var(--muted);line-height:1.8">
            <strong>bcrypt</strong> — Recommended for production.<br>
            <strong>SHA1</strong> — Compatible with most Apache installs.<br>
            <strong>Plain</strong> — Only for local dev, never production!<br><br>
            The <code>.htpasswd</code> file is at <code>code/.htpasswd</code>.<br>
            It is automatically blocked from web access.
          </div>
        </div>
      </div>
    </div>
    """
    return layout(page_content, "users", "Users & Auth")


@admin.route("/users/add", methods=["POST"])
def users_add():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    method   = request.form.get("method", "bcrypt")
    code_dir = config.code_dir
    htpasswd_path = code_dir / ".htpasswd"

    if not username or not password:
        flash("Username and password are required.", "error")
        return redirect(url_for("users"))

    if method == "bcrypt":
        try:
            import bcrypt
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode().replace("$2b$", "$2y$")
        except ImportError:
            flash("bcrypt package not installed. Run: pip install bcrypt", "error")
            return redirect(url_for("users"))
    elif method == "sha1":
        import base64
        hashed = "{SHA}" + base64.b64encode(hashlib.sha1(password.encode()).digest()).decode()
    else:
        hashed = password  # plain

    # Remove existing entry for this user
    lines = []
    if htpasswd_path.exists():
        for line in htpasswd_path.read_text().splitlines():
            if not line.startswith(username + ":"):
                lines.append(line)
    lines.append(f"{username}:{hashed}")
    htpasswd_path.write_text("\n".join(lines) + "\n")
    flash(f"✅ User '{username}' added ({method})!", "success")
    return redirect(url_for("users"))


@admin.route("/users/delete", methods=["POST"])
def users_delete():
    username = request.form.get("username", "")
    code_dir = config.code_dir
    htpasswd_path = code_dir / ".htpasswd"
    if htpasswd_path.exists():
        lines = [l for l in htpasswd_path.read_text().splitlines() if not l.startswith(username + ":")]
        htpasswd_path.write_text("\n".join(lines) + "\n")
    flash(f"🗑️ User '{username}' removed.", "success")
    return redirect(url_for("users"))


# ── Logs ──────────────────────────────────────────────────────────────────────

@admin.route("/logs")
def logs():
    log_path = Path(config.get("LOG_FILE", "logs/access.log"))
    lines = []
    if log_path.exists():
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
            lines = text.strip().splitlines()[-500:]  # last 500 lines
        except OSError:
            pass

    filter_val = request.args.get("filter", "").strip()
    if filter_val:
        lines = [l for l in lines if filter_val in l]

    log_html = ""
    for line in reversed(lines):
        css = "log-200"
        if " 3" in line:  css = "log-3xx"
        if " 4" in line:  css = "log-4xx"
        if " 5" in line:  css = "log-5xx"
        safe = line.replace("&", "&amp;").replace("<", "&lt;")
        log_html += f'<div class="{css}">{safe}</div>'

    snap = stats.snapshot()
    recent_html = ""
    for r in reversed(snap["recent"][-100:]):
        if r["status"] < 300:
            s = "log-200"
        elif r["status"] < 400:
            s = "log-3xx"
        elif r["status"] < 500:
            s = "log-4xx"
        else:
            s = "log-5xx"
        recent_html += f'<div class="{s}">[{r["time"]}] {r["method"]} {r["path"]} {r["status"]} {r["ms"]}ms [{r["kind"]}]</div>'

    page_content = f"""
    <div class="row">
      <div style="flex:2">
        <div class="card">
          <div class="card-title" style="display:flex;align-items:center;justify-content:space-between">
            <span>📋 Access Log ({log_path})</span>
            <div class="btn-group">
              <form method="GET" style="display:flex;gap:.5rem;align-items:center">
                <input type="text" name="filter" value="{filter_val}" placeholder="Filter…" style="width:160px;padding:.3rem .6rem;font-size:.82rem">
                <button class="btn btn-secondary btn-sm">Filter</button>
              </form>
              <form method="POST" action="/logs/clear">
                <button class="btn btn-danger btn-sm" onclick="return confirm('Clear log file?')">🗑️ Clear</button>
              </form>
            </div>
          </div>
          <div class="log-box">
            {log_html if log_html else '<span style="color:#475569">Log file is empty or not found.</span>'}
          </div>
        </div>
      </div>
      <div style="flex:1">
        <div class="card">
          <div class="card-title">⚡ Live Requests (in-memory)</div>
          <div class="log-box" style="max-height:300px">
            {recent_html if recent_html else '<span style="color:#475569">No requests yet.</span>'}
          </div>
        </div>
        <div class="card">
          <div class="card-title">📊 Session Stats</div>
          <div style="font-size:.88rem;line-height:2">
            Total: <strong>{snap['total_requests']}</strong><br>
            PHP: <strong>{snap['php_executions']}</strong><br>
            Cache hits: <strong>{snap['cache_hits']}</strong><br>
            Errors: <strong style="color:{'#ef4444' if snap['errors'] else 'inherit'}">{snap['errors']}</strong><br>
            Uptime: <strong>{snap['uptime']}</strong>
          </div>
          <form method="POST" action="/cache/clear" style="margin-top:.8rem">
            <button class="btn btn-secondary btn-sm">🗑️ Clear Cache ({cache.size} entries)</button>
          </form>
        </div>
      </div>
    </div>
    """
    return layout(page_content, "logs", "Logs")


@admin.route("/logs/clear", methods=["POST"])
def logs_clear():
    log_path = Path(config.get("LOG_FILE", "logs/access.log"))
    try:
        log_path.write_text("")
        flash("✅ Log file cleared.", "success")
    except OSError as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("logs"))


@admin.route("/cache/clear", methods=["POST"])
def cache_clear():
    n = cache.clear()
    flash(f"✅ Cache cleared ({n} entries removed).", "success")
    return redirect(request.referrer or url_for("dashboard"))


# ── PHP Info ──────────────────────────────────────────────────────────────────

@admin.route("/phpinfo")
def phpinfo():
    php_ok = php.is_available(config.php_binary)
    info_html = ""
    version_html = ""

    if not php_ok:
        info_html = f"""<div class="flash flash-red">
          ❌ PHP binary not found: <code>{config.php_binary}</code><br>
          Install PHP and make sure it's in your PATH, or set <code>PHP_BINARY</code> in <a href="/settings">Settings</a>.
        </div>"""
    else:
        try:
            # Version
            r = subprocess.run([config.php_binary, "-v"], capture_output=True, text=True, timeout=5)
            version_html = r.stdout.strip()

            # Extensions
            r2 = subprocess.run([config.php_binary, "-m"], capture_output=True, text=True, timeout=5)
            modules = [m.strip() for m in r2.stdout.strip().splitlines() if m.strip() and not m.startswith("[")]

            # INI settings
            r3 = subprocess.run([config.php_binary, "-i"], capture_output=True, text=True, timeout=5)
            ini_lines = r3.stdout.strip().splitlines()
            ini_table = ""
            for line in ini_lines[:80]:  # first 80 settings
                if " => " in line:
                    parts = line.split(" => ", 2)
                    if len(parts) >= 2:
                        k = parts[0].strip().replace("<", "&lt;")
                        v = parts[-1].strip().replace("<", "&lt;")
                        ini_table += f"<tr><td><code>{k}</code></td><td>{v}</td></tr>"

            mods_html = " ".join(f'<span class="badge badge-gray">{m}</span>' for m in modules[:80])

            info_html = f"""
            <div class="card">
              <div class="card-title">PHP Version</div>
              <pre style="font-size:.85rem;color:#1e293b;background:#f8fafc;padding:.8rem;border-radius:6px">{version_html}</pre>
            </div>
            <div class="card">
              <div class="card-title">Loaded Extensions ({len(modules)})</div>
              <div style="display:flex;flex-wrap:wrap;gap:.3rem">{mods_html}</div>
            </div>
            <div class="card">
              <div class="card-title">PHP INI Settings (first 80)</div>
              <div class="table-wrapper" style="border:none;max-height:400px;overflow-y:auto">
                <table><tr><th>Setting</th><th>Value</th></tr>{ini_table}</table>
              </div>
            </div>"""
        except Exception as e:
            info_html = f'<div class="flash flash-red">Error running PHP: {e}</div>'

    page_content = f"""
    <div style="margin-bottom:1rem">
      <div class="flash flash-{'green' if php_ok else 'red'}">
        {'✅ PHP is available at: <code>' + config.php_binary + '</code>' if php_ok else '❌ PHP not found'}
      </div>
    </div>
    {info_html}
    """
    return layout(page_content, "phpinfo", "PHP Info")


# ── API endpoints (used by dashboard auto-refresh) ────────────────────────────

@admin.route("/api/stats")
def api_stats():
    return jsonify(stats.snapshot())


@admin.route("/api/status")
def api_status():
    return jsonify({
        "php_ok":    php.is_available(config.php_binary),
        "cache":     cache.size,
        "uptime":    stats.uptime,
        "requests":  stats.total_requests,
    })
