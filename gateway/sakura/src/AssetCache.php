<?php
declare(strict_types=1);
namespace LaBookGateway;

/** Server-private asset cache. Call only after authenticating every request. */
final class AssetCache
{
    private const MAX_FILE = 2097152;
    private const MAX_TOTAL = 67108864;
    private string $file;
    public function __construct(private string $directory, string $origin, private string $target)
    {
        $this->file = $directory . '/' . hash('sha256', $origin . "\n" . $target) . '.json';
    }
    public static function eligible(string $method, string $target): bool
    {
        return $method === 'GET' && preg_match('~\A/(?:static/[A-Za-z0-9_/-]+\.(?:js|css|svg|png|jpg|jpeg|ico|woff2?|mp3)(?:\?v=[A-Za-z0-9_-]{1,64})?|covers/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png))\z~', $target) === 1;
    }
    /** Authenticated browser cache; dynamic forms and APIs remain no-store. */
    public static function browserPolicy(string $method, string $target, int $status, array $headers): string
    {
        if (!in_array($method, ['GET', 'HEAD'], true) || !in_array($status, [200, 304], true)
            || isset($headers['location']) || isset($headers['set-cookie'])) {
            return 'private, no-store';
        }
        $path = explode('?', $target, 2)[0];
        $type = strtolower(trim(explode(';', $headers['content-type'] ?? '')[0]));
        if ($status === 200 && $type === 'text/html'
            && ($path === '/' || preg_match('~\A/scan(?:/[A-Za-z0-9_%.-]*)?\z~', $path))) {
            return 'private, max-age=300, must-revalidate';
        }
        if (!self::eligible('GET', $target)) { return 'private, no-store'; }
        $extension = pathinfo($path, PATHINFO_EXTENSION);
        $mime = ['js'=>['text/javascript','application/javascript'], 'css'=>['text/css'],
            'svg'=>['image/svg+xml'], 'png'=>['image/png'], 'jpg'=>['image/jpeg'], 'jpeg'=>['image/jpeg'],
            'ico'=>['image/x-icon','image/vnd.microsoft.icon'], 'woff'=>['font/woff','application/font-woff'],
            'woff2'=>['font/woff2'], 'mp3'=>['audio/mpeg']];
        if ($status === 200 && !in_array($type, $mime[$extension] ?? [], true)) { return 'private, no-store'; }
        if (preg_match('~\?v=[a-f0-9]{16}\z~', $target)) { return 'private, max-age=604800, immutable'; }
        return 'private, max-age=' . (str_starts_with($target, '/covers/') ? 604800 : 300);
    }
    public function load(int $now): ?array
    {
        if (!is_file($this->file) || filesize($this->file) > self::MAX_FILE * 2) { return null; }
        $data = json_decode((string)@file_get_contents($this->file), true);
        if (!is_array($data) || !is_int($data['expires'] ?? null) || $data['expires'] <= $now
            || !is_array($data['headers'] ?? null) || !is_string($data['body'] ?? null)) { return null; }
        $body = base64_decode($data['body'], true);
        if ($body === false || strlen($body) > self::MAX_FILE) { return null; }
        $headers = $data['headers'];
        foreach ($headers as $name => $value) {
            if (!in_array($name, ['content-type', 'etag', 'last-modified'], true)
                || !is_string($value) || preg_match('/[\x00-\x1f\x7f]/', $value)) { return null; }
        }
        return ['headers' => $headers, 'body' => $body];
    }
    public function store(int $status, array $headers, string $body, int $now): void
    {
        if ($status !== 200 || strlen($body) > self::MAX_FILE || isset($headers['location'])
            || isset($headers['set-cookie'])) { return; }
        if (!is_dir($this->directory) && !@mkdir($this->directory, 0700, true) && !is_dir($this->directory)) { return; }
        $lock = @fopen($this->directory . '/write.lock', 'c');
        if ($lock === false) { return; }
        try {
            if (!flock($lock, LOCK_EX | LOCK_NB)) { return; }
            $allowed = array_intersect_key($headers, array_flip(['content-type', 'etag', 'last-modified']));
            $ttl = preg_match('~\?v=[a-f0-9]{16}\z~', $this->target) ? 604800
                : (str_starts_with($this->target, '/covers/') ? 3600 : 300);
            $encoded = json_encode(['expires' => $now + $ttl, 'headers' => $allowed, 'body' => base64_encode($body)]);
            if ($encoded === false) { return; }
            $files = glob($this->directory . '/*.json') ?: [];
            $total = 0;
            foreach ($files as $file) { $total += (int)@filesize($file); }
            usort($files, static fn($a, $b) => (int)@filemtime($a) <=> (int)@filemtime($b));
            foreach ($files as $file) {
                if ($total + strlen($encoded) <= self::MAX_TOTAL) { break; }
                $size = (int)@filesize($file);
                if (@unlink($file)) { $total -= $size; }
            }
            if ($total + strlen($encoded) > self::MAX_TOTAL) { return; }
            $temp = $this->file . '.next';
            if (@file_put_contents($temp, $encoded) !== false) { @chmod($temp, 0600); @rename($temp, $this->file); }
        } finally { flock($lock, LOCK_UN); fclose($lock); }
    }
}
