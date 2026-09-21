<?php
declare(strict_types=1);

// This preview has no upstream proxy, Google login, or access to application data.
// The generated public entry supplies $probeConfig from outside the web root.
ini_set('display_errors', '0');
header('Cache-Control: private, no-store, max-age=0');
header('Pragma: no-cache');
header('Expires: 0');
header('X-Content-Type-Options: nosniff');
header('X-Robots-Tag: noindex, nofollow');
header('Content-Type: application/json; charset=utf-8');

function result(int $status, array $value): never
{
    // Private diagnostic evidence distinguishes PHP decisions from HTTP-layer rewriting.
    file_put_contents(__DIR__ . '/probe-status.log', time() . ' ' . $status . "\n", FILE_APPEND | LOCK_EX);
    http_response_code($status);
    echo json_encode($value, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    exit;
}

$supplied = $_SERVER['HTTP_X_LABOOK_PREVIEW_TOKEN'] ?? '';
if (empty($probeConfig['token']) || empty($probeConfig['expires'])
    || time() >= $probeConfig['expires'] || !hash_equals($probeConfig['token'], $supplied)) {
    result(404, ['error' => 'not_found']);
}
if (($_SERVER['HTTPS'] ?? '') !== 'on') {
    result(400, ['error' => 'https_required']);
}

$action = $_GET['action'] ?? 'runtime';
$method = $_SERVER['REQUEST_METHOD'];
if ($action === 'runtime' && $method === 'GET') {
    $required = ['curl', 'openssl', 'session', 'hash', 'json', 'mbstring'];
    $extensions = [];
    foreach ($required as $name) {
        $extensions[$name] = extension_loaded($name);
    }
    result(200, [
        'php' => PHP_VERSION, 'sapi' => PHP_SAPI, 'extensions' => $extensions,
        'limits' => array_combine(
            ['post_max_size', 'upload_max_filesize', 'memory_limit', 'max_execution_time'],
            array_map('ini_get', ['post_max_size', 'upload_max_filesize', 'memory_limit', 'max_execution_time'])
        ),
        'oauth' => 'not_configured', 'application_proxy' => 'disabled',
    ]);
}
if ($action === 'egress' && $method === 'GET') {
    // Fixed diagnostic service; never accepts a user-supplied destination.
    $curl = curl_init('https://api.ipify.org?format=json');
    curl_setopt_array($curl, [CURLOPT_RETURNTRANSFER => true, CURLOPT_FOLLOWLOCATION => false,
        CURLOPT_CONNECTTIMEOUT => 5, CURLOPT_TIMEOUT => 10,
        CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
        CURLOPT_IPRESOLVE => CURL_IPRESOLVE_V4, CURLOPT_PROTOCOLS => CURLPROTO_HTTPS]);
    $body = curl_exec($curl);
    $status = curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    curl_close($curl);
    $ip = is_string($body) ? (json_decode($body, true)['ip'] ?? null) : null;
    if ($status !== 200 || !is_string($ip) || !filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) {
        result(502, ['error' => 'egress_probe_failed']);
    }
    result(200, ['family' => 'IPv4', 'ip' => $ip]);
}
if ($action === 'transport' && in_array($method, ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], true)) {
    // Deliberately small diagnostic limit, independent of future proxy limits.
    $body = file_get_contents('php://input', false, null, 0, 8193);
    if ($body === false || strlen($body) > 8192 || (int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 8192) {
        result(413, ['error' => 'too_large']);
    }
    $files = [];
    foreach ($_FILES as $key => $file) {
        if (is_array($file['error']) || $file['error'] !== UPLOAD_ERR_OK) {
            result(400, ['error' => 'invalid_upload']);
        }
        $files[$key] = ['bytes' => $file['size'], 'sha256' => hash_file('sha256', $file['tmp_name'])];
    }
    result(200, ['method' => $method, 'bytes' => strlen($body),
        'sha256' => hash('sha256', $body), 'files' => $files]);
}
result(404, ['error' => 'not_found']);
