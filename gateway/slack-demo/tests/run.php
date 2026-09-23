<?php
declare(strict_types=1);
require __DIR__ . '/../vendor/autoload.php';
require __DIR__ . '/../src/Oidc.php';
require __DIR__ . '/../src/Transactions.php';
use Firebase\JWT\JWT;
use LaBookSlackDemo\Oidc;
use LaBookSlackDemo\Transactions;

$count = 0;
function check(bool $value): void { global $count; ++$count; if (!$value) { throw new RuntimeException('Test failed at ' . $count); } }
function rejects(callable $f): void {
    try { $f(); } catch (Throwable $e) { check(true); return; }
    throw new RuntimeException('Expected rejection');
}
function b64(string $s): string { return rtrim(strtr(base64_encode($s), '+/', '-_'), '='); }

$rsa = openssl_pkey_new(['private_key_bits' => 2048, 'private_key_type' => OPENSSL_KEYTYPE_RSA]);
openssl_pkey_export($rsa, $private);
$details = openssl_pkey_get_details($rsa);
$jwks = ['keys' => [['kty' => 'RSA', 'alg' => 'RS256', 'use' => 'sig', 'kid' => 'test',
    'n' => b64($details['rsa']['n']), 'e' => b64($details['rsa']['e'])]]];
$config = ['client_id' => '123.456', 'client_secret' => 'test-only', 'expected_team_id' => 'TTEST',
    'public_url' => 'https://demo.example/slack-signin-demo'];
$nonce = bin2hex(random_bytes(32));
$access = 'test-access-token';
$claims = ['iss' => 'https://slack.com', 'aud' => '123.456', 'sub' => 'UTEST',
    'iat' => time(), 'exp' => time() + 300, 'nonce' => $nonce,
    'https://slack.com/user_id' => 'UTEST', 'https://slack.com/team_id' => 'TTEST',
    'name' => '試験ユーザー', 'email' => 'test@example.invalid', 'email_verified' => true,
    'at_hash' => b64(substr(hash('sha256', $access, true), 0, 16))];
$encode = static fn (array $payload) => JWT::encode($payload, $private, 'RS256', 'test');
$valid = $encode($claims);
$identity = Oidc::verify($valid, $jwks, $config, $nonce, $access);
check($identity['team_id'] === 'TTEST' && $identity['workspace_checked']);
check(!isset($identity['access_token']) && !isset($identity['id_token']));
foreach ([['iss' => 'https://other.invalid'], ['aud' => 'other'], ['exp' => time() - 90],
    ['iat' => time() + 90], ['nonce' => 'wrong'], ['https://slack.com/team_id' => 'TOTHER'],
    ['https://slack.com/user_id' => 'UOTHER'], ['sub' => ''], ['at_hash' => 'bad'],
    ['aud' => ['123.456', 'another']], ['azp' => 'other']] as $change) {
    rejects(fn () => Oidc::verify($encode(array_replace($claims, $change)), $jwks, $config, $nonce, $access));
}
$missing = $claims; unset($missing['exp']);
rejects(fn () => Oidc::verify($encode($missing), $jwks, $config, $nonce, $access));
$parts = explode('.', $valid); $parts[2][0] = $parts[2][0] === 'A' ? 'B' : 'A';
rejects(fn () => Oidc::verify(implode('.', $parts), $jwks, $config, $nonce, $access));
$hs = JWT::encode($claims, str_repeat('test', 16), 'HS256', 'test');
rejects(fn () => Oidc::verify($hs, $jwks, $config, $nonce, $access));
$discover = Oidc::verify($valid, $jwks, array_replace($config, ['expected_team_id' => '']), $nonce, $access);
check(!$discover['workspace_checked']);

$path = tempnam(sys_get_temp_dir(), 'labook-slack-test-');
try {
    $transactions = new Transactions($path);
    $tx = $transactions->create();
    rejects(fn () => $transactions->consume($tx['state'], bin2hex(random_bytes(32))));
    check($transactions->consume($tx['state'], $tx['browser']) === $tx['nonce']);
    rejects(fn () => $transactions->consume($tx['state'], $tx['browser']));
    $expired = $transactions->create();
    $db = new PDO('sqlite:' . $path); $db->exec('UPDATE transactions SET expires=0'); $db = null;
    rejects(fn () => $transactions->consume($expired['state'], $expired['browser']));
    rejects(fn () => $transactions->consume('../invalid', $expired['browser']));
    $url = Oidc::authorizationUrl($config, $tx, 'current');
    parse_str(parse_url($url, PHP_URL_QUERY), $params);
    check($params['scope'] === 'openid profile email' && $params['response_mode'] === 'form_post');
    check($params['redirect_uri'] === $config['public_url'] . '/callback.php' && $params['team'] === 'TTEST');
    $standardUrl = Oidc::authorizationUrl($config, $tx, 'standard');
    parse_str(parse_url($standardUrl, PHP_URL_QUERY), $standardParams);
    unset($params['response_mode']);
    check($standardParams === $params);
    $selectionUrl = Oidc::authorizationUrl($config, $tx, 'select-workspace');
    parse_str(parse_url($selectionUrl, PHP_URL_QUERY), $selectionParams);
    unset($standardParams['team']);
    check($selectionParams === $standardParams);
    check(Oidc::authorizationUrl($config, $tx) === $selectionUrl);
    check($config['expected_team_id'] === 'TTEST');
    $entryConfig = array_replace($config, ['workspace_login_url' => 'https://test-workspace.slack.com/']);
    $entry = Oidc::authorizationUrl($entryConfig, $tx, 'workspace-entry');
    check(parse_url($entry, PHP_URL_HOST) === 'test-workspace.slack.com');
    parse_str(parse_url($entry, PHP_URL_QUERY), $outer);
    check(str_starts_with($outer['redir'], '/oauth?') && !str_starts_with($outer['redir'], '//'));
    parse_str(parse_url($outer['redir'], PHP_URL_QUERY), $inner);
    check($inner['state'] === $tx['state'] && $inner['nonce'] === $tx['nonce']);
    check($inner['redirect_uri'] === $config['public_url'] . '/callback.php'
        && $inner['openid_connect'] === '1' && $inner['response_type'] === 'code');
    check($inner['scope'] === '' && $inner['user_scope'] === 'openid,profile,email'
        && $inner['team'] === '' && !isset($inner['client_secret']));
    foreach (['https://slack.com.evil.invalid/', 'https://user@demo.slack.com/',
        'https://demo.slack.com/?redir=bad', 'https://demo.slack.com:443/', 'http://demo.slack.com/'] as $badHome) {
        rejects(fn () => Oidc::authorizationUrl(array_replace($entryConfig,
            ['workspace_login_url' => $badHome]), $tx, 'workspace-entry'));
    }
    rejects(fn () => Oidc::authorizationUrl(array_replace($entryConfig,
        ['expected_team_id' => '']), $tx, 'workspace-entry'));
    rejects(fn () => Oidc::authorizationUrl($config, $tx, 'arbitrary'));
    // A different request transport must never relax the target restriction.
    rejects(fn () => Oidc::verify($encode(array_replace($claims,
        ['https://slack.com/team_id' => 'TOTHER'])), $jwks, $config, $nonce, $access));
} finally { unset($transactions); unlink($path); }
echo json_encode(['status' => 'passed', 'checks' => $count], JSON_THROW_ON_ERROR) . "\n";
