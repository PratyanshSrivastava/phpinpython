<?php
http_response_code(404);
header('Content-Type: text/html; charset=UTF-8');
$uri = htmlspecialchars($_SERVER['REQUEST_URI'] ?? '/');
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>404 — Not Found</title>
  <link rel="stylesheet" href="/style.css">
  <style>
    body { display: flex; flex-direction: column; min-height: 100vh; }
    .error-page { flex: 1; display: flex; align-items: center; justify-content: center; padding: 3rem; }
    .error-box  { text-align: center; max-width: 500px; }
    .big-code   { font-size: 8rem; font-weight: 900; color: #e2e8f0; line-height: 1; }
  </style>
</head>
<body>
  <?php include __DIR__ . '/partials/nav.php'; ?>

  <div class="error-page">
    <div class="error-box">
      <div class="big-code">404</div>
      <h2 style="color:var(--accent);margin-bottom:.6rem">Page Not Found</h2>
      <p style="color:var(--muted);margin-bottom:1.5rem">
        The path <code><?= $uri ?></code> doesn't exist.<br>
        Check your <code>.htaccess</code> rewrite rules or file names.
      </p>
      <a href="/" class="btn btn-primary">← Go Home</a>
      <a href="http://localhost:8080/files" class="btn btn-outline" style="background:var(--text);color:#fff;margin-left:.5rem" target="_blank">📁 File Manager</a>
    </div>
  </div>

  <?php include __DIR__ . '/partials/footer.php'; ?>
</body>
</html>
