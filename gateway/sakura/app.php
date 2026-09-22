<?php
declare(strict_types=1);

use LaBookGateway\AuthStore;
use LaBookGateway\GatewayConfig;
use LaBookGateway\LoginTransactions;
use LaBookGateway\RequestTarget;
use LaBookGateway\SessionPolicy;
use LaBookGateway\SessionStore;
use LaBookGateway\Relay;
use LaBookSlackDemo\Oidc;

ini_set('display_errors', '0');
umask(0077);
header('Cache-Control: private, no-store');
header('Referrer-Policy: no-referrer');
header('X-Content-Type-Options: nosniff');
header('X-Robots-Tag: noindex, nofollow');
header("Content-Security-Policy: frame-ancestors 'none'; base-uri 'self'");

function escaped(string $s): string { return htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
function scalar(array $source, string $key): string { return is_string($source[$key] ?? null) ? $source[$key] : ''; }
function jsonReply(int $status, array $value): never {
    http_response_code($status); header('Content-Type: application/json; charset=utf-8');
    echo json_encode($value, JSON_UNESCAPED_UNICODE); exit;
}
function gotoPage(string $url): never { header('Location: ' . $url, true, 303); exit; }
function sessionCookie(string $value, string $path, int $expires): void {
    setcookie('LABOOK_GATE_SESSION', $value, ['expires' => $expires, 'path' => $path,
        'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
}
function authPage(string $content, bool $autoLogin = false): never {
    header('Content-Type: text/html; charset=utf-8');
    // Ordinary form POSTs need a real Origin for CSRF checks; paths stay private.
    header('Referrer-Policy: strict-origin');
    $nonce = base64_encode(random_bytes(24));
    $scriptPolicy = $autoLogin ? "; script-src 'nonce-" . $nonce . "'" : '';
    header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'" . $scriptPolicy);
    echo '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        . '<title>laBook ログイン</title><style>body{font:16px/1.7 system-ui;max-width:640px;margin:60px auto;padding:24px}button{font:inherit;padding:10px 20px}</style>'
        . '<main>' . $content . '</main>'
        . ($autoLogin ? '<script nonce="' . escaped($nonce) . '">document.getElementById("slack-login").submit();</script>' : '')
        . '</html>'; exit;
}

$store = null;
try {
    foreach (['RequestTarget', 'SessionPolicy', 'SessionStore', 'AuthStore', 'LoginTransactions', 'Security', 'Relay', 'GatewayConfig'] as $name) {
        require __DIR__ . '/src/' . $name . '.php';
    }
    require __DIR__ . '/vendor/autoload.php';
    require __DIR__ . '/oidc/Oidc.php';
    $c = GatewayConfig::validate(json_decode(file_get_contents(__DIR__ . '/config.local.json'), true, 32, JSON_THROW_ON_ERROR));
    if ($c['expires_at'] !== null && time() >= $c['expires_at']) { jsonReply(410, ['error' => 'trial_expired']); }
    if (($_SERVER['HTTPS'] ?? '') !== 'on'
        || strtolower($_SERVER['HTTP_HOST'] ?? '') !== strtolower(substr($c['public_origin'], 8))) {
        jsonReply(400, ['error' => 'origin_invalid']);
    }
    $method = $_SERVER['REQUEST_METHOD'];
    $prefix = $c['public_prefix'];
    $cookiePath = parse_url($c['public_url'], PHP_URL_PATH) . '/';
    $stateDir = __DIR__ . '/state';
    $policy = new SessionPolicy($c);
    $db = new AuthStore($stateDir . '/auth.sqlite');
    $sessionToken = scalar($_COOKIE, 'LABOOK_GATE_SESSION');
    if (($gatewayAction ?? '') === 'callback') {
        if (!in_array($method, ['GET', 'POST'], true) || (int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 16384
            || strlen($_SERVER['QUERY_STRING'] ?? '') > 16384) { throw new RuntimeException('state_invalid'); }
        $input = $method === 'POST' ? $_POST : $_GET;
        $tx = (new LoginTransactions($stateDir . '/transactions.sqlite'))->consume(
            scalar($input, 'state'), scalar($_COOKIE, 'LABOOK_GATE_TX'));
        setcookie('LABOOK_GATE_TX', '', ['expires' => 1, 'path' => $cookiePath,
            'secure' => true, 'httponly' => true, 'samesite' => 'None']);
        if (scalar($input, 'error') !== '') { throw new RuntimeException('access_denied'); }
        $code = scalar($input, 'code');
        if ($code === '' || strlen($code) > 4096) { throw new RuntimeException('state_invalid'); }
        $verified = Oidc::exchange($c, $code, $tx['nonce']);
        $session = $db->establish($verified, $sessionToken, $policy, time());
        sessionCookie($session['token'], $cookiePath, $session['expires_at']);
        gotoPage($c['public_origin'] . RequestTarget::returnPath($tx['return_path'], $prefix));
    }
    $raw = $_SERVER['REQUEST_URI'];
    RequestTarget::validate($raw);
    [$rawPath] = explode('?', $raw, 2);
    if ($rawPath === $prefix && in_array($method, ['GET', 'HEAD'], true)) {
        gotoPage($prefix . '/' . (isset(explode('?', $raw, 2)[1]) ? '?' . explode('?', $raw, 2)[1] : ''));
    }
    $target = RequestTarget::stripPrefix($raw, $prefix);
    $path = rawurldecode(explode('?', $target, 2)[0]);
    if (!in_array($method, ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'], true)) {
        jsonReply(405, ['error' => 'method_not_allowed']);
    }
    if ($path === '/_auth/logged-out' && $method === 'GET') {
        authPage('<h1>ログアウトしました</h1><p><a href="' . escaped($prefix . '/_auth/login') . '">再ログイン</a></p>');
    }
    if ($path === '/_auth/login') {
        $store = new SessionStore($stateDir . '/sessions', $cookiePath);
        $return = RequestTarget::returnPath(scalar($method === 'POST' ? $_POST : $_GET, 'return'), $prefix);
        if ($method === 'GET') {
            $csrf = $_SESSION['login_csrf']; $store->close();
            authPage('<p>Slackへ移動しています…</p>'
                . '<form id="slack-login" method="post" action="' . escaped($prefix . '/_auth/login') . '">'
                . '<input type="hidden" name="csrf" value="' . escaped($csrf) . '">'
                . '<input type="hidden" name="return" value="' . escaped($return) . '">'
                . '<noscript><button>Slackでログイン</button></noscript></form>', true);
        }
        if ($method !== 'POST') { jsonReply(405, ['error' => 'method_not_allowed']); }
        $policy->checkCsrf(['csrf' => $_SESSION['login_csrf']], $method, scalar($_SERVER, 'HTTP_ORIGIN'), scalar($_POST, 'csrf'));
        if (time() - ($_SESSION['last_start'] ?? 0) < 5) { jsonReply(429, ['error' => 'try_later']); }
        $_SESSION['last_start'] = time();
        $db->revoke($sessionToken, time());
        sessionCookie('', $cookiePath, 1);
        $tx = (new LoginTransactions($stateDir . '/transactions.sqlite'))->create($return);
        setcookie('LABOOK_GATE_TX', $tx['browser'], ['expires' => time() + 300, 'path' => $cookiePath,
            'secure' => true, 'httponly' => true, 'samesite' => 'None']);
        $store->close();
        $destination = Oidc::authorizationUrl($c, $tx, $c['login_flow']);
        authPage('<meta http-equiv="refresh" content="0;url=' . escaped($destination) . '"><p>Slackへ移動します。</p>'
            . '<p><a rel="noreferrer" href="' . escaped($destination) . '">移動しない場合はこちら</a></p>');
    }
    try { $identity = $db->session($sessionToken, $policy, time()); $subject = $identity['subject']; }
    catch (RuntimeException $e) {
        if ($e->getMessage() !== 'login_required') { throw $e; }
        if ($method === 'GET' && (in_array($path, ['/', '/books/manage', '/users/manage', '/scan', '/scan/', '/L'], true)
            || str_starts_with($path, '/scan/') || str_starts_with($path, '/L/'))
            && str_contains(scalar($_SERVER, 'HTTP_ACCEPT'), 'text/html')) {
            gotoPage($prefix . '/_auth/login?return=' . rawurlencode($raw));
        }
        jsonReply(401, ['error' => 'login_required', 'description' => 'ログインが必要です。画面を開き直してください。']);
    }
    $token = scalar($_SERVER, 'HTTP_X_LABOOK_CSRF');
    if ($path === '/_auth/logout' && $token === '') { $token = scalar($_POST, 'csrf'); }
    $policy->checkCsrf($identity, $method, scalar($_SERVER, 'HTTP_ORIGIN'), $token);
    $csrf = $identity['csrf'];
    if ($path === '/_auth/logout') {
        if ($method !== 'POST') { jsonReply(405, ['error' => 'method_not_allowed']); }
        $db->revoke($sessionToken, time());
        sessionCookie('', $cookiePath, 1);
        if (scalar($_SERVER, 'HTTP_X_LABOOK_CSRF') !== '') { jsonReply(200, ['logged_out' => true]); }
        gotoPage($prefix . '/_auth/logged-out');
    }
    unset($db); // No database transaction or PHP session lock during upstream I/O.
    if ($path === '/_auth/session') {
        if ($method !== 'GET') { jsonReply(405, ['error' => 'method_not_allowed']); }
        jsonReply(200, ['csrf' => $csrf]);
    }
    if ($path === '/_auth' || str_starts_with($path, '/_auth/')) { jsonReply(404, ['error' => 'not_found']); }
    if (!$c['relay_enabled']) {
        if ($path !== '/' || $method !== 'GET') { jsonReply(503, ['error' => 'relay_not_enabled']); }
        authPage('<h1>Slackログインを確認しました</h1><p>ログインは30日間有効です。laBookへの中継は準備中です。</p>'
            . '<form method="post" action="' . escaped($prefix . '/_auth/logout') . '">'
            . '<input type="hidden" name="csrf" value="' . escaped($csrf) . '"><button>ログアウト</button></form>');
    }
    $relay = new Relay($c);
    $relay->forward($method, $target, $subject);
} catch (Throwable $e) {
    if ($store !== null) { try { $store->close(); } catch (Throwable $ignored) {} }
    $status = match ($e->getMessage()) {
        'csrf_rejected', 'workspace_mismatch', 'identity_rejected' => 403, 'state_invalid', 'access_denied', 'target_invalid' => 400,
        'body_too_large' => 413, 'body_invalid' => 400, 'upstream_timeout' => 504,
        'upstream_failed' => 502, default => 503
    };
    // Bounded private diagnostics: no URL, query, identity, cookie or secret.
    $record = ['time' => gmdate('c'), 'status' => $status,
        'reason' => in_array($e->getMessage(), ['csrf_rejected', 'workspace_mismatch', 'identity_rejected',
            'state_invalid', 'access_denied', 'target_invalid', 'body_too_large', 'body_invalid',
            'upstream_timeout', 'upstream_failed'], true) ? $e->getMessage() : 'internal_error',
        'transport' => isset($relay) ? $relay->failure : []];
    $log = @fopen(__DIR__ . '/state/gateway-errors.log', 'c+');
    if ($log !== false) {
        if (flock($log, LOCK_EX)) {
            if (fstat($log)['size'] > 1048576) { ftruncate($log, 0); }
            fseek($log, 0, SEEK_END); fwrite($log, json_encode($record) . "\n");
            flock($log, LOCK_UN);
        }
        fclose($log);
    }
    $description = in_array($status, [502, 504], true)
        ? 'サーバーとの通信に失敗しました。少し待ってから再度お試しください。再ログインは不要です。'
        : '処理を完了できませんでした。ログイン画面からやり直してください。';
    jsonReply($status, ['error' => $status === 503 ? 'gateway_unavailable' : 'request_rejected',
        'description' => $description]);
}
