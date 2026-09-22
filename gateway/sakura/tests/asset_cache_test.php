<?php
declare(strict_types=1);
require __DIR__ . '/../src/AssetCache.php';
use LaBookGateway\AssetCache;
$root = sys_get_temp_dir() . '/labook-cache-test-' . bin2hex(random_bytes(8));
umask(0077); $checks = 0;
function check(bool $ok): void { global $checks; ++$checks; if (!$ok) { throw new RuntimeException('Cache check failed: ' . $checks); } }
try {
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
    check($cache->load(160) === null);
    check((new AssetCache($root, 'https://other.example', '/static/runtime.js'))->load(101) === null);
    check((new AssetCache($root, 'https://upstream.example', '/static/other.js'))->load(101) === null);
    $cache->store(403, [], 'denied', 101); check($cache->load(102)['body'] === 'safe');
    $cache->store(200, ['set-cookie'=>'private'], 'private', 101); check($cache->load(102)['body'] === 'safe');
    $cache->store(200, ['location'=>'/elsewhere'], 'redirect', 101); check($cache->load(102)['body'] === 'safe');
    $cache->store(200, [], str_repeat('x',2097153), 101); check($cache->load(102)['body'] === 'safe');
    $cover = new AssetCache($root, 'https://upstream.example', '/covers/123.jpg');
    $cover->store(200, ['content-type'=>'image/jpeg'], "\x00\xff", 100);
    check($cover->load(399)['body'] === "\x00\xff"); check($cover->load(400) === null);
    foreach (glob($root.'/*.json') as $file) { file_put_contents($file, '{broken'); }
    check($cache->load(101) === null);
    echo json_encode(['checks'=>$checks,'status'=>'passed']) . "\n";
} finally {
    foreach (glob($root.'/*') ?: [] as $file) { unlink($file); }
    if (is_dir($root)) { rmdir($root); }
}
