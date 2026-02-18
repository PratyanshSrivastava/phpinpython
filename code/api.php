<?php
/**
 * api.php — JSON REST API
 * Routed here by .htaccess: RewriteRule ^api/(.+)$ api.php [L]
 *
 * Endpoints:
 *   GET  /api/ping         — health check
 *   GET  /api/users        — list users
 *   POST /api/users        — create user
 *   GET  /api/echo         — echo request back
 *   GET  /api/time         — current server time
 *   POST /api/calculate    — basic math
 */

// Always respond with JSON
header('Content-Type: application/json; charset=UTF-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With');
header('X-Powered-By: PHPyServer');

// Handle preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// Parse route
$uri    = $_SERVER['REQUEST_URI'] ?? '/api/';
$path   = ltrim(parse_url($uri, PHP_URL_PATH), '/');
$route  = preg_replace('#^api/?#', '', $path);
$method = $_SERVER['REQUEST_METHOD'];

// Parse JSON body
$raw  = file_get_contents('php://stdin');
$body = json_decode($raw, true) ?? [];

// Response helper
function respond(array $data, int $status = 200): void {
    http_response_code($status);
    echo json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
    exit;
}

// ── Sample data (in-memory — use a real DB in production) ─────────────────
$users_db = [
    ['id' => 1, 'name' => 'Alice',   'email' => 'alice@example.com',   'role' => 'admin'],
    ['id' => 2, 'name' => 'Bob',     'email' => 'bob@example.com',     'role' => 'editor'],
    ['id' => 3, 'name' => 'Charlie', 'email' => 'charlie@example.com', 'role' => 'viewer'],
];

// ── Router ─────────────────────────────────────────────────────────────────
switch (true) {

    // GET /api/ping
    case $route === 'ping':
        respond([
            'pong'      => true,
            'timestamp' => date('c'),
            'server'    => 'PHPyServer',
        ]);

    // GET /api/echo
    case $route === 'echo':
        respond([
            'method'       => $method,
            'route'        => $route,
            'query_string' => $_GET,
            'body'         => $body,
            'headers'      => getallheaders() ?: [],
            'server'       => [
                'php'     => PHP_VERSION,
                'remote'  => $_SERVER['REMOTE_ADDR'] ?? 'unknown',
                'time'    => date('c'),
            ],
        ]);

    // GET /api/users
    case $route === 'users' && $method === 'GET':
        respond([
            'users' => $users_db,
            'total' => count($users_db),
            '_note' => 'This is demo data. Connect to a database for real apps.',
        ]);

    // POST /api/users
    case $route === 'users' && $method === 'POST':
        if (empty($body['name']) || empty($body['email'])) {
            respond(['error' => 'name and email are required'], 400);
        }
        $new_user = [
            'id'    => rand(100, 999),
            'name'  => htmlspecialchars($body['name']),
            'email' => htmlspecialchars($body['email']),
            'role'  => $body['role'] ?? 'viewer',
        ];
        respond(['created' => true, 'user' => $new_user], 201);

    // GET /api/time
    case $route === 'time':
        respond([
            'utc'       => gmdate('Y-m-d H:i:s'),
            'local'     => date('Y-m-d H:i:s'),
            'timezone'  => date_default_timezone_get(),
            'unix'      => time(),
            'formatted' => date('l, F j, Y g:i A'),
        ]);

    // POST /api/calculate
    case $route === 'calculate':
        $a  = (float)($body['a'] ?? 0);
        $b  = (float)($body['b'] ?? 0);
        $op = $body['op'] ?? '+';
        $result = match($op) {
            '+'  => $a + $b,
            '-'  => $a - $b,
            '*'  => $a * $b,
            '/'  => $b != 0 ? $a / $b : null,
            '%'  => $b != 0 ? fmod($a, $b) : null,
            '**' => $a ** $b,
            default => null,
        };
        if ($result === null) {
            respond(['error' => 'Invalid operation or division by zero'], 400);
        }
        respond(['expression' => "$a $op $b", 'result' => $result]);

    // GET /api/status
    case $route === 'status':
        respond([
            'status'  => 'ok',
            'php'     => PHP_VERSION,
            'sapi'    => PHP_SAPI,
            'memory'  => round(memory_get_usage(true) / 1024) . ' KB',
            'peak'    => round(memory_get_peak_usage(true) / 1024) . ' KB',
            'uptime'  => date('c'),
        ]);

    // 404
    default:
        respond([
            'error'  => "Unknown route: /$route",
            'method' => $method,
            'available_routes' => [
                'GET  /api/ping',
                'GET  /api/echo',
                'GET  /api/users',
                'POST /api/users',
                'GET  /api/time',
                'POST /api/calculate',
                'GET  /api/status',
            ],
        ], 404);
}
