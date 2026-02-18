<?php
/**
 * index.php — PHPyServer Demo Homepage
 * This file lives in your code/ folder, which acts like Apache's DocumentRoot.
 *
 * Try editing this file via the Admin Panel at http://localhost:8080
 */

session_start();

// Simple visit counter using session
$_SESSION['visits'] = ($_SESSION['visits'] ?? 0) + 1;

// Handle the contact form
$form_message = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['contact'])) {
    $name  = htmlspecialchars(trim($_POST['name']  ?? ''));
    $email = htmlspecialchars(trim($_POST['email'] ?? ''));
    $msg   = htmlspecialchars(trim($_POST['msg']   ?? ''));
    if ($name && $email && $msg) {
        $form_message = "<div class='alert alert-success'>✅ Thanks $name! Message received (demo only).</div>";
    } else {
        $form_message = "<div class='alert alert-error'>❌ Please fill in all fields.</div>";
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PHPyServer — Home</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>

  <?php include 'partials/nav.php'; ?>

  <!-- Hero -->
  <section class="hero">
    <div class="hero-content">
      <h1>🐘 PHPyServer</h1>
      <p>PHP running inside Python Flask — with zero Apache needed.</p>
      <div class="hero-badges">
        <span class="badge">PHP <?= PHP_VERSION ?></span>
        <span class="badge">Flask</span>
        <span class="badge">.htaccess Support</span>
        <span class="badge">Visit #<?= $_SESSION['visits'] ?></span>
      </div>
      <div style="margin-top:1.5rem">
        <a href="/blog" class="btn btn-primary">📝 Blog (Pretty URL)</a>
        <a href="/api/users" class="btn btn-outline" target="_blank">🔌 API Demo</a>
      </div>
    </div>
  </section>

  <!-- Feature cards -->
  <section class="section">
    <div class="container">
      <h2 class="section-title">What's included</h2>
      <div class="card-grid">

        <div class="card">
          <div class="card-icon">🔀</div>
          <h3>Rewrite Rules</h3>
          <p>Full <code>.htaccess</code> support: pretty URLs, redirects, and capture groups — just like Apache.</p>
          <p><code>/blog</code> → <code>blog.php</code></p>
        </div>

        <div class="card">
          <div class="card-icon">⚡</div>
          <h3>Fast Static Files</h3>
          <p>CSS, JS, and images are served from memory cache. TTL configurable in the admin panel.</p>
        </div>

        <div class="card">
          <div class="card-icon">🔐</div>
          <h3>Basic Auth</h3>
          <p>Protect routes with <code>.htpasswd</code>. Supports bcrypt, SHA1, and APR1-MD5 hashing.</p>
        </div>

        <div class="card">
          <div class="card-icon">🎛️</div>
          <h3>Admin Panel</h3>
          <p>Live control panel at <a href="http://localhost:8080" target="_blank">localhost:8080</a> — edit files, view logs, manage settings.</p>
        </div>

        <div class="card">
          <div class="card-icon">🔌</div>
          <h3>REST API</h3>
          <p>JSON API at <a href="/api/users" target="_blank">/api/users</a> — routed via .htaccess to <code>api.php</code>.</p>
        </div>

        <div class="card">
          <div class="card-icon">📁</div>
          <h3>File Uploads</h3>
          <p>Multipart uploads via <code>POST /__upload</code>. Saved to <code>code/uploads/</code>.</p>
        </div>

      </div>
    </div>
  </section>

  <!-- Server info table -->
  <section class="section" style="background:#f8fafc">
    <div class="container">
      <h2 class="section-title">🖥️ Server Info</h2>
      <div class="table-wrapper">
        <table>
          <tr><th>Variable</th><th>Value</th></tr>
          <tr><td>PHP Version</td><td><code><?= PHP_VERSION ?></code></td></tr>
          <tr><td>PHP SAPI</td><td><code><?= PHP_SAPI ?></code></td></tr>
          <tr><td>Server Time</td><td><code><?= date('Y-m-d H:i:s T') ?></code></td></tr>
          <tr><td>Document Root</td><td><code><?= htmlspecialchars($_SERVER['DOCUMENT_ROOT']) ?></code></td></tr>
          <tr><td>Request Method</td><td><code><?= $_SERVER['REQUEST_METHOD'] ?></code></td></tr>
          <tr><td>Remote Addr</td><td><code><?= $_SERVER['REMOTE_ADDR'] ?></code></td></tr>
          <tr><td>User Agent</td><td><code><?= htmlspecialchars(substr($_SERVER['HTTP_USER_AGENT'] ?? '', 0, 60)) ?>…</code></td></tr>
          <tr><td>Session ID</td><td><code><?= session_id() ?></code></td></tr>
          <tr><td>Memory Usage</td><td><code><?= number_format(memory_get_usage(true) / 1024) ?> KB</code></td></tr>
        </table>
      </div>
    </div>
  </section>

  <!-- Contact form demo -->
  <section class="section">
    <div class="container" style="max-width:580px">
      <h2 class="section-title">📬 Contact Form Demo</h2>
      <p style="color:#64748b;margin-bottom:1.2rem">Demonstrates POST handling, <code>$_POST</code>, session, and form validation.</p>
      <?= $form_message ?>
      <form method="POST" class="form-card">
        <input type="hidden" name="contact" value="1">
        <div class="form-group">
          <label>Your Name</label>
          <input type="text" name="name" placeholder="Alice" required>
        </div>
        <div class="form-group">
          <label>Email Address</label>
          <input type="email" name="email" placeholder="alice@example.com" required>
        </div>
        <div class="form-group">
          <label>Message</label>
          <textarea name="msg" rows="4" placeholder="Hello from PHP!" required></textarea>
        </div>
        <button type="submit" class="btn btn-primary" style="width:100%">Send Message</button>
      </form>
    </div>
  </section>

  <?php include 'partials/footer.php'; ?>

</body>
</html>
