<?php
/**
 * partials/footer.php — Shared footer
 */
?>
<footer class="footer">
  <div class="container">
    <p>
      PHPyServer &bull; PHP <?= PHP_VERSION ?> on Python Flask &bull; <?= date('Y') ?>
    </p>
    <p style="margin-top:.3rem">
      <a href="http://localhost:8080" target="_blank">⚙️ Admin Panel</a> &bull;
      <a href="http://localhost:8080/files" target="_blank">📁 File Manager</a> &bull;
      <a href="http://localhost:8080/logs" target="_blank">📋 Logs</a>
    </p>
  </div>
</footer>
