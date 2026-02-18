<?php
/**
 * gallery.php — Demo gallery page
 * Accessible as /gallery (pretty URL)
 */

$items = [
    ['emoji' => '🌅', 'label' => 'Sunrise',    'color' => '#fef9c3'],
    ['emoji' => '🌊', 'label' => 'Ocean',       'color' => '#dbeafe'],
    ['emoji' => '🏔️', 'label' => 'Mountains',  'color' => '#dcfce7'],
    ['emoji' => '🌸', 'label' => 'Cherry Blossom','color' => '#fce7f3'],
    ['emoji' => '🦋', 'label' => 'Butterfly',   'color' => '#ede9fe'],
    ['emoji' => '🌌', 'label' => 'Galaxy',      'color' => '#1e1b4b'],
    ['emoji' => '🏙️', 'label' => 'City',        'color' => '#f1f5f9'],
    ['emoji' => '🌿', 'label' => 'Forest',      'color' => '#dcfce7'],
    ['emoji' => '🐬', 'label' => 'Dolphin',     'color' => '#e0f2fe'],
    ['emoji' => '🍄', 'label' => 'Mushroom',    'color' => '#fef3c7'],
    ['emoji' => '🔥', 'label' => 'Campfire',    'color' => '#fee2e2'],
    ['emoji' => '❄️', 'label' => 'Snowflake',   'color' => '#f0f9ff'],
];
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gallery — PHPyServer</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>

<?php include 'partials/nav.php'; ?>

<div class="hero" style="padding:3rem 2rem">
  <h1 style="font-size:2rem">🖼️ Gallery</h1>
  <p>Pretty URL: <code>/gallery</code> → <code>gallery.php</code></p>
</div>

<section class="section">
  <div class="container">
    <div class="gallery-grid">
      <?php foreach ($items as $item): ?>
      <div class="gallery-item" style="background:<?= $item['color'] ?>" title="<?= $item['label'] ?>">
        <div style="text-align:center">
          <div style="font-size:3.5rem"><?= $item['emoji'] ?></div>
          <div style="font-size:.8rem;margin-top:.4rem;color:#475569"><?= $item['label'] ?></div>
        </div>
      </div>
      <?php endforeach; ?>
    </div>
    <div class="alert alert-info" style="margin-top:2rem">
      💡 This page uses <code>/gallery</code> as a pretty URL — no .php extension needed.
      Add <code>RewriteRule ^gallery$ gallery.php [L]</code> to your <code>.htaccess</code>, or PHPyServer
      auto-resolves it for you.
    </div>
  </div>
</section>

<?php include 'partials/footer.php'; ?>
</body>
</html>
