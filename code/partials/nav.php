<?php
/**
 * partials/nav.php — Shared navigation bar
 * Include in any PHP page: <?php include 'partials/nav.php'; ?>
 */
$current_path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
$current_path = rtrim($current_path, '/') ?: '/';

function nav_active(string $path): string {
    global $current_path;
    return str_starts_with($current_path, $path) ? 'active' : '';
}
?>
<nav class="navbar">
  <div class="nav-brand">
    <a href="/">🐘 PHPyServer</a>
  </div>
  <div class="nav-links">
    <a href="/"         class="nav-link <?= $current_path === '/' ? 'active' : '' ?>">Home</a>
    <a href="/blog"     class="nav-link <?= nav_active('/blog') ?>">Blog</a>
    <a href="/gallery"  class="nav-link <?= nav_active('/gallery') ?>">Gallery</a>
    <a href="/api/ping" class="nav-link" target="_blank">API</a>
  </div>
  <div class="nav-right">
    <a href="http://localhost:8080" class="btn btn-sm btn-outline" target="_blank">⚙️ Admin</a>
  </div>
</nav>
