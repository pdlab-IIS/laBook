<?php
declare(strict_types=1);
namespace LaBookGateway;
use RuntimeException;
require_once __DIR__ . '/AssetCache.php';

/** Fixed HTTPS upstream; no browser-selected destination or credentials. */
final class Relay
{
    /** Numeric transport diagnostics only; never headers, URLs or payloads. */
    public array $failure = [];
    private string $secret;
    public function __construct(private array $config)
    {
        $origin = $config['upstream_origin'] ?? '';
        $parts = is_string($origin) ? parse_url($origin) : false;
        $secret = is_string($config['signing_key'] ?? null) ? base64_decode($config['signing_key'], true) : false;
        if (!is_array($parts) || ($parts['scheme'] ?? '') !== 'https'
            || !isset($parts['host']) || isset($parts['user']) || isset($parts['pass'])
            || isset($parts['path']) || isset($parts['query']) || isset($parts['fragment'])
            || !preg_match('~\Ahttps://[a-z0-9.-]+(?::[0-9]+)?\z~', $origin)
            || (isset($parts['port']) && $parts['port'] < 1)
            || !is_string($config['signing_key_id'] ?? null)
            || !preg_match('/\A[A-Za-z0-9_-]{1,64}\z/', $config['signing_key_id'])
            || !is_string($secret) || strlen($secret) < 32) {
            throw new RuntimeException('relay_config_invalid');
        }
        $this->secret = $secret;
    }

    public static function body(string $method, string $target): array
    {
        $limit = 8 * 1024 * 1024;
        if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > $limit) { throw new RuntimeException('body_too_large'); }
        $type = $_SERVER['CONTENT_TYPE'] ?? '';
        if (str_starts_with(strtolower($type), 'multipart/form-data')) {
            // laBook's only multipart operation is one JPEG cover. PHP has
            // already parsed it, so sign the exact reconstructed wire bytes.
            if ($method !== 'POST' || !preg_match('~\A/books/[0-9]+/cover(?:\?.*)?\z~', $target)
                || $_POST !== [] || array_keys($_FILES) !== ['cover']) { throw new RuntimeException('body_invalid'); }
            $file = $_FILES['cover'];
            if (($file['error'] ?? null) !== UPLOAD_ERR_OK || !is_string($file['tmp_name'] ?? null)
                || !is_uploaded_file($file['tmp_name'])) { throw new RuntimeException('body_invalid'); }
            $contents = file_get_contents($file['tmp_name'], false, null, 0, $limit + 1);
            if ($contents === false) { throw new RuntimeException('body_invalid'); }
            $boundary = 'labook-' . bin2hex(random_bytes(24));
            $body = '--' . $boundary . "\r\nContent-Disposition: form-data; name=\"cover\"; filename=\"cover.jpg\"\r\n"
                . "Content-Type: image/jpeg\r\n\r\n" . $contents . "\r\n--" . $boundary . "--\r\n";
            $type = 'multipart/form-data; boundary=' . $boundary;
        } else {
            $input = fopen('php://input', 'rb');
            if ($input === false) { throw new RuntimeException('body_invalid'); }
            try { $body = stream_get_contents($input, $limit + 1); } finally { fclose($input); }
            if ($body === false) { throw new RuntimeException('body_invalid'); }
        }
        if (strlen($body) > $limit) { throw new RuntimeException('body_too_large'); }
        if (in_array($method, ['GET', 'HEAD'], true) && $body !== '') { throw new RuntimeException('body_invalid'); }
        return [$type, $body];
    }

    public function location(string $location): string
    {
        $c = $this->config;
        if (str_starts_with($location, $c['public_origin'] . $c['public_prefix'] . '/')) {
            RequestTarget::stripPrefix(substr($location, strlen($c['public_origin'])), $c['public_prefix']);
            return $location;
        }
        if (str_starts_with($location, $c['upstream_origin'] . '/')) {
            $location = substr($location, strlen($c['upstream_origin']));
        }
        RequestTarget::validate($location);
        // Flask with SCRIPT_NAME returns prefix-bearing relative redirects.
        if ($location === $c['public_prefix'] || str_starts_with($location, $c['public_prefix'] . '/')) {
            return $c['public_origin'] . $location;
        }
        return $c['public_origin'] . $c['public_prefix'] . $location;
    }

    public function signedHeaders(string $method, string $target, string $subject, string $type, string $body): array
    {
        RequestTarget::validate($target);
        if (!preg_match('/\Aslack:' . preg_quote($this->config['expected_team_id'], '/') . ':[A-Z][A-Z0-9]+\z/', $subject)) {
            throw new RuntimeException('identity_rejected');
        }
        $r = ['key_id' => $this->config['signing_key_id'], 'method' => $method, 'target' => $target,
            'content_type' => $type, 'timestamp' => (string)time(), 'nonce' => bin2hex(random_bytes(16)), 'subject' => $subject];
        $headers = ['Content-Type: ' . $type, 'Accept-Encoding: identity', 'Expect:', 'ngrok-skip-browser-warning: 1'];
        foreach (['key_id', 'timestamp', 'nonce', 'subject'] as $key) {
            $headers[] = 'X-LaBook-' . str_replace('_', '-', $key) . ': ' . $r[$key];
        }
        $headers[] = 'X-LaBook-Signature: ' . Security::sign($this->secret, $r, $body);
        return $headers;
    }

    public function forward(string $method, string $target, string $subject): never
    {
        [$type, $body] = self::body($method, $target);
        $headers = $this->signedHeaders($method, $target, $subject, $type, $body);
        $cache = AssetCache::eligible($method, $target)
            ? new AssetCache(__DIR__ . '/../state/asset-cache', $this->config['upstream_origin'], $target) : null;
        $cached = $cache?->load(time());
        if ($cached !== null) {
            http_response_code(200);
            header('Cache-Control: ' . AssetCache::browserPolicy($method, $target, 200, $cached['headers']));
            foreach ($cached['headers'] as $name => $value) { header($name . ': ' . $value); }
            header('Content-Length: ' . strlen($cached['body']));
            echo $cached['body']; exit;
        }
        foreach (['HTTP_ACCEPT' => 'Accept', 'HTTP_IF_NONE_MATCH' => 'If-None-Match',
                  'HTTP_IF_MODIFIED_SINCE' => 'If-Modified-Since'] as $source => $name) {
            $value = $_SERVER[$source] ?? '';
            if (is_string($value) && strlen($value) <= 4096 && !preg_match('/[\x00-\x1f\x7f]/', $value)) {
                $headers[] = $name . ': ' . $value;
            }
        }
        $responseHeaders = []; $responseBody = ''; $headerBytes = 0;
        $curl = curl_init($this->config['upstream_origin'] . $target);
        curl_setopt_array($curl, [CURLOPT_CUSTOMREQUEST => $method,
            CURLOPT_FOLLOWLOCATION => false, CURLOPT_CONNECTTIMEOUT => 5, CURLOPT_TIMEOUT => 20,
            CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
            CURLOPT_PROTOCOLS => CURLPROTO_HTTPS, CURLOPT_IPRESOLVE => CURL_IPRESOLVE_V4,
            CURLOPT_HTTPHEADER => $headers, CURLOPT_PATH_AS_IS => true,
            CURLOPT_HEADERFUNCTION => static function ($handle, string $line) use (&$responseHeaders, &$headerBytes): int {
                $headerBytes += strlen($line);
                if ($headerBytes > 32768) { return 0; }
                if (str_starts_with($line, 'HTTP/')) { $responseHeaders = []; }
                elseif (str_contains($line, ':')) {
                    [$key, $value] = explode(':', trim($line), 2);
                    $responseHeaders[strtolower($key)] = trim($value);
                }
                return strlen($line);
            },
            CURLOPT_WRITEFUNCTION => static function ($handle, string $chunk) use (&$responseBody): int {
                if (strlen($responseBody) + strlen($chunk) > 16 * 1024 * 1024) { return 0; }
                $responseBody .= $chunk; return strlen($chunk);
            }]);
        if ($method === 'HEAD') { curl_setopt($curl, CURLOPT_NOBODY, true); }
        elseif (!in_array($method, ['GET', 'OPTIONS'], true) || $body !== '') { curl_setopt($curl, CURLOPT_POSTFIELDS, $body); }
        $success = curl_exec($curl);
        $status = curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
        $errno = curl_errno($curl);
        $elapsed = curl_getinfo($curl, CURLINFO_TOTAL_TIME);
        curl_close($curl);
        if ($success === false || $status < 200 || $status > 599
            || !in_array(strtolower($responseHeaders['content-encoding'] ?? 'identity'), ['', 'identity'], true)) {
            $this->failure = ['upstream_status' => $status, 'curl_errno' => $errno,
                'elapsed_ms' => (int)round($elapsed * 1000), 'header_bytes' => $headerBytes,
                'body_bytes' => strlen($responseBody),
                'encoded_response' => !in_array(strtolower($responseHeaders['content-encoding'] ?? 'identity'), ['', 'identity'], true)];
            throw new RuntimeException($errno === CURLE_OPERATION_TIMEDOUT ? 'upstream_timeout' : 'upstream_failed');
        }
        if (isset($responseHeaders['location'])) {
            try { $responseHeaders['location'] = $this->location($responseHeaders['location']); }
            catch (RuntimeException $e) { throw new RuntimeException('upstream_failed'); }
        }
        $cache?->store($status, $responseHeaders, $responseBody, time());
        http_response_code($status);
        header('Cache-Control: ' . AssetCache::browserPolicy($method, $target, $status, $responseHeaders));
        // Separate cached HTML across login/logout and account changes.
        header('Vary: Cookie, Accept');
        // Cookies, CORS, hop-by-hop fields and upstream cache rules never cross.
        foreach (['content-type', 'content-disposition', 'etag', 'last-modified', 'location', 'allow'] as $name) {
            if (isset($responseHeaders[$name]) && !preg_match('/[\x00-\x1f\x7f]/', $responseHeaders[$name])) {
                header($name . ': ' . $responseHeaders[$name]);
            }
        }
        if ($method !== 'HEAD' && !in_array($status, [204, 304], true)) {
            header('Content-Length: ' . strlen($responseBody)); echo $responseBody;
        }
        exit;
    }
}
