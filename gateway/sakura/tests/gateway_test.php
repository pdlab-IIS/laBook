<?php
declare(strict_types=1);
foreach (['RequestTarget', 'LoginTransactions', 'SessionPolicy', 'Security', 'Relay', 'GatewayConfig'] as $name) {
    require __DIR__ . '/../src/' . $name . '.php';
}
use LaBookGateway\RequestTarget;
use LaBookGateway\LoginTransactions;
use LaBookGateway\Relay;
use LaBookGateway\Security;
use LaBookGateway\GatewayConfig;
$checks = 0;
function check(bool $ok): void { global $checks; ++$checks; if (!$ok) { throw new RuntimeException('Gateway test failed: ' . $checks); } }
function rejected(callable $fn): void {
    try { $fn(); } catch (RuntimeException $e) { check(true); return; }
    check(false);
}
foreach (['/books?q=%E6%9C%AC&a=1&a=2', '/%E6%9C%AC', '/'] as $target) {
    check(RequestTarget::validate($target) === $target);
    check(RequestTarget::stripPrefix('/trial/index.php' . $target, '/trial/index.php') === $target);
}
foreach (['//outside.invalid', '/a/../b', '/a/%2e/b', '/a%2fb', '/a%5cb', '/a%252fb',
    '/a//b', '/a\\b', '/a%00b', '/a%zz', '/a%ff', '/a#b', "/a\nb"] as $target) {
    rejected(fn() => RequestTarget::validate($target));
}
foreach (['/trial-other/x', '/outside/x'] as $target) { rejected(fn() => RequestTarget::stripPrefix($target, '/trial')); }
foreach (['https://outside.invalid/', '//outside.invalid/', '/trial/../x', '/trial/_auth/logout', '/trial/%5fauth/session'] as $target) {
    check(RequestTarget::returnPath($target, '/trial') === '/trial/');
}
check(RequestTarget::returnPath('/trial/L/A?location=A%20B', '/trial') === '/trial/L/A?location=A%20B');
$directory = sys_get_temp_dir() . '/labook-tx-' . bin2hex(random_bytes(8));
mkdir($directory, 0700);
try {
    $transactions = new LoginTransactions($directory . '/tx.sqlite');
    $tx = $transactions->create('/trial/L/A?x=1');
    rejected(fn() => $transactions->consume($tx['state'], str_repeat('0', 64)));
    $result = $transactions->consume($tx['state'], $tx['browser']);
    check($result === ['nonce' => $tx['nonce'], 'return_path' => '/trial/L/A?x=1']);
    rejected(fn() => $transactions->consume($tx['state'], $tx['browser']));
    $expired = $transactions->create('/trial/');
    $db = new PDO('sqlite:' . $directory . '/tx.sqlite');
    $db->exec('UPDATE gateway_transactions SET expires=1');
    rejected(fn() => $transactions->consume($expired['state'], $expired['browser']));
} finally {
    unset($transactions, $db);
    foreach (glob($directory . '/*') as $file) { unlink($file); }
    rmdir($directory);
}
$config = ['public_origin' => 'https://public.example', 'public_prefix' => '/trial/index.php',
    'public_url' => 'https://public.example/trial', 'expected_team_id' => 'TTEST',
    'session_generation' => 'test', 'revoked_subjects' => [], 'client_id' => '123.456', 'client_secret' => 'test-only',
    'login_flow' => 'workspace-entry', 'workspace_login_url' => 'https://example.slack.com/',
    'expires_at' => time()+60, 'relay_enabled' => true, 'upstream_origin' => 'https://upstream.example',
    'signing_key_id' => 'test', 'signing_key' => base64_encode(str_repeat('k', 32))];
check(GatewayConfig::validate($config) === $config);
foreach ([['public_url' => 'https://outside.example/trial'], ['expected_team_id' => ''], ['login_flow' => 'current'],
    ['upstream_origin' => 'http://upstream.example'], ['upstream_origin' => 'https://upstream.example/path'],
    ['signing_key' => 'invalid'], ['workspace_login_url' => 'https://outside.example/']] as $change) {
    rejected(fn() => GatewayConfig::validate(array_replace($config, $change)));
}
$relay = new Relay($config);
foreach (['/books?x=1', 'https://upstream.example/books?x=1', '/trial/index.php/books?x=1',
    'https://public.example/trial/index.php/books?x=1'] as $location) {
    check($relay->location($location) === 'https://public.example/trial/index.php/books?x=1');
}
foreach (['https://outside.example/', '//outside.example/', '/a/../b', "foo\r\nSet-Cookie:x"] as $location) {
    rejected(fn() => $relay->location($location));
}
$headers = $relay->signedHeaders('POST', '/books?x=1', 'slack:TTEST:UTEST', 'application/json', '{"test":1}');
$map=[];
foreach ($headers as $header) { [$name,$value]=explode(':', $header,2); $map[strtolower($name)]=trim($value); }
$expected = Security::sign(str_repeat('k',32), ['key_id'=>'test','method'=>'POST','target'=>'/books?x=1',
    'content_type'=>'application/json','timestamp'=>$map['x-labook-timestamp'],'nonce'=>$map['x-labook-nonce'],
    'subject'=>'slack:TTEST:UTEST'], '{"test":1}');
check(hash_equals($expected, $map['x-labook-signature']));
check(!isset($map['cookie']) && !isset($map['authorization']));
rejected(fn() => $relay->signedHeaders('POST', '/books', 'slack:TOTHER:U1', '', ''));
echo json_encode(['checks'=>$checks,'status'=>'passed']) . "\n";
