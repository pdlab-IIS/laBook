<?php
declare(strict_types=1);
require __DIR__ . '/../src/AssetCache.php';
use LaBookGateway\AssetCache;
$root = sys_get_temp_dir() . '/labook-cache-test-' . bin2hex(random_bytes(8));
umask(0077); $checks = 0;
function check(bool $ok): void { global $checks; ++$checks; if (!$ok) { throw new RuntimeException('Cache check failed: ' . $checks); } }
try {
    foreach ([200, 304] as $status) {
        foreach (['GET', 'HEAD'] as $method) {
            check(AssetCache::browserPolicy($method, '/covers/123_456.jpg', $status, ['content-type'=>'image/jpeg']) === 'private, max-age=604800');
            check(AssetCache::browserPolicy($method, '/static/book-solid.svg', $status, ['content-type'=>'image/svg+xml']) === 'private, max-age=300');
        }
    }
    check(AssetCache::browserPolicy('GET', '/covers/123.jpg', 304, []) === 'private, max-age=604800');
    foreach (['js'=>'text/javascript', 'css'=>'text/css', 'woff2'=>'font/woff2', 'mp3'=>'audio/mpeg'] as $ext=>$mime) {
        check(AssetCache::browserPolicy('GET', '/static/app.'.$ext, 200, ['content-type'=>$mime]) === 'private, max-age=300');
        check(AssetCache::browserPolicy('GET', '/static/app.'.$ext.'?v=abcdef0123456789', 200, ['content-type'=>$mime]) === 'private, max-age=604800, immutable');
        check(AssetCache::eligible('GET', '/static/app.'.$ext.'?v=abcdef0123456789'));
    }
    foreach (['/', '/?location=A', '/scan', '/scan/', '/scan/A'] as $path) {
        check(AssetCache::browserPolicy('GET', $path, 200, ['content-type'=>'text/html; charset=utf-8']) === 'private, max-age=300, must-revalidate');
        check(!AssetCache::eligible('GET', $path)); // Never share HTML in the server asset cache.
    }
    foreach (['/books/manage?isbn=123', '/users/manage', '/_auth/login', '/books'] as $path) {
        check(AssetCache::browserPolicy('GET', $path, 200, ['content-type'=>'text/html']) === 'private, no-store');
    }
    check(!AssetCache::eligible('GET', '/static/a.js?v=123&secret=x'));
    check(AssetCache::browserPolicy('GET', '/static/a.js?v=abcdef0123456789', 200, ['content-type'=>'text/html']) === 'private, no-store');
    foreach (['/books', '/', '/_auth/session', '/static/runtime.js', '/static/style.css', '/covers/a.jpg?v=1', '/covers/../a.jpg'] as $path) {
        check(AssetCache::browserPolicy('GET', $path, 200, ['content-type'=>'image/jpeg']) === 'private, no-store');
    }
    foreach ([201, 206, 302, 401, 403, 404, 500] as $status) {
        check(AssetCache::browserPolicy('GET', '/covers/a.jpg', $status, ['content-type'=>'image/jpeg']) === 'private, no-store');
    }
    foreach (['POST', 'PUT', 'DELETE'] as $method) {
        check(AssetCache::browserPolicy($method, '/covers/a.jpg', 200, ['content-type'=>'image/jpeg']) === 'private, no-store');
    }
    foreach ([[], ['content-type'=>'text/html'], ['content-type'=>'image/jpeg','set-cookie'=>'session=x'], ['content-type'=>'image/jpeg','location'=>'/login']] as $headers) {
        check(AssetCache::browserPolicy('GET', '/covers/a.jpg', 200, $headers) === 'private, no-store');
    }
    foreach (['/static/runtime.js', '/static/nested/icon.svg', '/covers/123_456.jpg'] as $path) {
        check(AssetCache::eligible('GET', $path));
        check(!AssetCache::eligible('POST', $path));
    }
    foreach (['/books','/_auth/session','/static/../secret.js','/static/a.js?token=x','/covers/a.php','/covers/a%2ejpg'] as $path) {
        check(!AssetCache::eligible('GET', $path));
    }
    $cache = new AssetCache($root, 'https://upstream.example', '/static/runtime.js');
    check($cache->load(100) === null);
    $cache->store(200, ['content-type'=>'text/javascript','etag'=>'"test"','cache-control'=>'public'], 'safe', 100);
    check($cache->load(101) === ['headers'=>['content-type'=>'text/javascript','etag'=>'"test"'],'body'=>'safe']);
    check($cache->load(399)['body'] === 'safe');
    check($cache->load(400) === null);
    check((new AssetCache($root, 'https://other.example', '/static/runtime.js'))->load(101) === null);
    check((new AssetCache($root, 'https://upstream.example', '/static/other.js'))->load(101) === null);
    $cache->store(403, [], 'denied', 101); check($cache->load(102)['body'] === 'safe');
    $cache->store(200, ['set-cookie'=>'private'], 'private', 101); check($cache->load(102)['body'] === 'safe');
    $cache->store(200, ['location'=>'/elsewhere'], 'redirect', 101); check($cache->load(102)['body'] === 'safe');
    $cache->store(200, [], str_repeat('x',2097153), 101); check($cache->load(102)['body'] === 'safe');
    $cover = new AssetCache($root, 'https://upstream.example', '/covers/123.jpg');
    $cover->store(200, ['content-type'=>'image/jpeg'], "\x00\xff", 100);
    check($cover->load(3699)['body'] === "\x00\xff"); check($cover->load(3700) === null);
    $versioned = new AssetCache($root, 'https://upstream.example', '/static/app.js?v=abcdef0123456789');
    $versioned->store(200, ['content-type'=>'text/javascript'], 'versioned', 100);
    check($versioned->load(604899)['body'] === 'versioned');
    check($versioned->load(604900) === null);
    check((new AssetCache($root, 'https://upstream.example', '/static/app.js?v=0123456789abcdef'))->load(101) === null);
    foreach (glob($root.'/*.json') as $file) { file_put_contents($file, '{broken'); }
    check($cache->load(101) === null);
    echo json_encode(['checks'=>$checks,'status'=>'passed']) . "\n";
} finally {
    foreach (glob($root.'/*') ?: [] as $file) { unlink($file); }
    if (is_dir($root)) { rmdir($root); }
}
