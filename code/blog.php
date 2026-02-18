<?php
/**
 * blog.php — Accessible as /blog (pretty URL via .htaccess)
 * Demonstrates: pretty URLs, query strings, PHP arrays as a "database"
 */

// ── Sample blog posts ──────────────────────────────────────────────────────
$posts = [
    1 => [
        'title'   => 'Getting Started with PHPyServer',
        'date'    => '2025-01-10',
        'author'  => 'Admin',
        'tags'    => ['setup', 'beginner'],
        'emoji'   => '🚀',
        'color'   => '#dbeafe',
        'excerpt' => 'PHPyServer lets you run PHP inside a Python Flask app with full .htaccess support — no Apache required.',
        'body'    => '<p>PHPyServer is a Python/Flask app that executes your PHP files on demand using the PHP CLI. It emulates Apache\'s DocumentRoot, .htaccess rewrite rules, basic auth, and static file serving.</p>
<p>Getting started is as simple as:</p>
<pre><code>git clone https://github.com/you/phpyserver
pip install -r requirements.txt
python run.py</code></pre>
<p>Then drop your PHP files in the <code>code/</code> folder and visit <code>http://localhost:5000</code>!</p>',
    ],
    2 => [
        'title'   => 'Pretty URLs Without Apache',
        'date'    => '2025-01-15',
        'author'  => 'Admin',
        'tags'    => ['htaccess', 'urls'],
        'emoji'   => '🔀',
        'color'   => '#dcfce7',
        'excerpt' => 'RewriteRule and auto-resolution turn /blog into blog.php transparently — your visitors never see .php extensions.',
        'body'    => '<p>Add these lines to your <code>code/.htaccess</code>:</p>
<pre><code>RewriteEngine On
RewriteRule ^blog$         blog.php      [L]
RewriteRule ^about$        about.php     [L]
RewriteRule ^post/([0-9]+)$ post.php?id=$1 [L]</code></pre>
<p>PHPyServer also automatically resolves <code>/blog</code> to <code>blog.php</code> even without an explicit rule — great for beginners!</p>',
    ],
    3 => [
        'title'   => 'Building a REST API with PHP',
        'date'    => '2025-01-22',
        'author'  => 'Admin',
        'tags'    => ['api', 'json'],
        'emoji'   => '🔌',
        'color'   => '#fef9c3',
        'excerpt' => 'Route /api/* to a single api.php file and handle different endpoints with a simple switch statement.',
        'body'    => '<p>In your <code>.htaccess</code>:</p>
<pre><code>RewriteRule ^api/(.+)$ api.php [L]</code></pre>
<p>Then in <code>api.php</code>, read the path and dispatch:</p>
<pre><code>$path = ltrim(parse_url($_SERVER[\'REQUEST_URI\'], PHP_URL_PATH), \'/api/\');
switch ($path) {
    case \'ping\': echo json_encode([\'pong\' => true]); break;
    case \'users\': /* ... */ break;
}</code></pre>',
    ],
    4 => [
        'title'   => 'Password-Protecting Pages',
        'date'    => '2025-02-01',
        'author'  => 'Admin',
        'tags'    => ['security', 'auth'],
        'emoji'   => '🔐',
        'color'   => '#fce7f3',
        'excerpt' => 'Use .htpasswd and Basic Auth to protect any directory — the admin panel makes it easy to manage users.',
        'body'    => '<p>Enable basic auth in <code>.htaccess</code>:</p>
<pre><code>AuthType Basic
AuthName "Members Only"
AuthUserFile .htpasswd
Require valid-user</code></pre>
<p>Then add users via the <a href="http://localhost:8080/users">Admin Panel → Users</a> page. PHPyServer supports bcrypt (recommended), SHA1, and APR1-MD5 hashes.</p>',
    ],
];

// ── Single post view ────────────────────────────────────────────────────────
$id = isset($_GET['id']) ? (int)$_GET['id'] : null;

if ($id !== null) {
    $post = $posts[$id] ?? null;
    if (!$post) {
        header("HTTP/1.1 404 Not Found");
        include '404.php';
        exit;
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= $id ? htmlspecialchars($posts[$id]['title']) . ' — ' : '' ?>Blog — PHPyServer</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>

<?php include 'partials/nav.php'; ?>

<?php if ($id && $post): ?>
  <!-- ── Single Post ─────────────────────────────────────────────────────── -->
  <div class="hero" style="padding:3rem 2rem;background:<?= $post['color'] ?>;color:var(--text)">
    <div class="hero-content" style="text-align:left">
      <div style="font-size:3rem"><?= $post['emoji'] ?></div>
      <h1 style="font-size:2rem;color:var(--text);margin-top:.5rem"><?= htmlspecialchars($post['title']) ?></h1>
      <div style="color:var(--muted);font-size:.88rem;margin-top:.5rem">
        By <?= $post['author'] ?> &bull; <?= $post['date'] ?>
        &nbsp;<?php foreach ($post['tags'] as $t): ?>
          <span class="tag"><?= $t ?></span>
        <?php endforeach; ?>
      </div>
    </div>
  </div>

  <section class="section">
    <div class="container" style="max-width:700px">
      <div style="font-size:1rem;line-height:1.85;color:var(--text)">
        <?= $post['body'] ?>
      </div>
      <div style="margin-top:2.5rem;padding-top:1.5rem;border-top:1px solid var(--border)">
        <a href="/blog" class="btn btn-outline" style="background:var(--accent);color:#fff">← All Posts</a>
      </div>
    </div>
  </section>

<?php else: ?>
  <!-- ── Post Listing ──────────────────────────────────────────────────────── -->
  <div class="hero" style="padding:3rem 2rem">
    <h1 style="font-size:2rem">📝 Blog</h1>
    <p>Pretty URL: <code>/blog</code> → <code>blog.php</code></p>
  </div>

  <section class="section">
    <div class="container">
      <div class="post-grid">
        <?php foreach ($posts as $pid => $post): ?>
        <div class="post-card">
          <div class="post-thumb" style="background:<?= $post['color'] ?>"><?= $post['emoji'] ?></div>
          <div class="post-body">
            <div class="post-meta"><?= $post['date'] ?> &bull; <?= $post['author'] ?></div>
            <h3><a href="/blog?id=<?= $pid ?>"><?= htmlspecialchars($post['title']) ?></a></h3>
            <p class="post-excerpt"><?= htmlspecialchars($post['excerpt']) ?></p>
            <div style="margin-top:.8rem">
              <?php foreach ($post['tags'] as $t): ?>
                <span class="tag"><?= $t ?></span>
              <?php endforeach; ?>
            </div>
          </div>
        </div>
        <?php endforeach; ?>
      </div>
    </div>
  </section>
<?php endif; ?>

<?php include 'partials/footer.php'; ?>
</body>
</html>
