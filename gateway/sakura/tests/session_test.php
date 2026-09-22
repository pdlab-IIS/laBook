<?php
declare(strict_types=1);
require __DIR__ . '/../src/SessionPolicy.php';
use LaBookGateway\SessionPolicy;

$checks = 0;
function check(bool $ok): void {
    global $checks;
    ++$checks;
    if (!$ok) { throw new RuntimeException('Session test failed: ' . $checks); }
}
function rejected(callable $fn, string $reason): void {
    try { $fn(); } catch (RuntimeException $e) { check($e->getMessage() === $reason); return; }
    check(false);
}
$config = ['public_origin' => 'https://public.example', 'expected_team_id' => 'TTEST',
    'session_generation' => 'test-1', 'revoked_subjects' => []];
$policy = new SessionPolicy($config);
$identity = ['user_id' => 'UTEST', 'team_id' => 'TTEST', 'workspace_checked' => true,
    'verified_at' => 2000000000, 'email' => 'do-not-store@example.invalid', 'access_token' => 'do-not-store'];
$session = $policy->establish($identity, 2000000000);
check(!isset($session['email']) && !isset($session['access_token']));
check($policy->authorize($session, 2000000010) === 'slack:TTEST:UTEST');
check($session['last_seen'] === 2000000010);
$another = $policy->establish($identity, 2000000000);
check($another['csrf'] !== $session['csrf']);

foreach ([['expected_team_id' => ''], ['expected_team_id' => 'EORG'], ['session_generation' => ''],
    ['revoked_subjects' => null], ['revoked_subjects' => ['invalid']], ['public_origin' => 'http://public.example'],
    ['public_origin' => 'https://public.example/'], ['public_origin' => 'https://public.example:99999']] as $change) {
    rejected(fn() => new SessionPolicy(array_replace($config, $change)), 'session_config_invalid');
}
foreach ([['team_id' => 'TOTHER'], ['workspace_checked' => false], ['user_id' => "U1\n"],
    ['verified_at' => 1999999939], ['verified_at' => 2000000001]] as $change) {
    rejected(fn() => $policy->establish(array_replace($identity, $change), 2000000000), 'identity_rejected');
}

foreach ([30 * 86400, 31 * 86400] as $elapsed) {
    $expired = $another;
    $expired['last_seen'] = 2000000000 + $elapsed - 1;
    rejected(function () use ($policy, &$expired, $elapsed) {
        $policy->authorize($expired, 2000000000 + $elapsed);
    }, 'login_required');
    check($expired === []);
}
$border = $another;
check($policy->authorize($border, 2000000000 + 30 * 86400 - 1) === 'slack:TTEST:UTEST');
foreach ([['session_generation' => 'test-2'], ['expected_team_id' => 'TOTHER'],
    ['revoked_subjects' => ['slack:TTEST:UTEST']]] as $change) {
    $copy = $another;
    $updated = new SessionPolicy(array_replace($config, $change));
    rejected(function () use ($updated, &$copy) { $updated->authorize($copy, 2000000010); }, 'login_required');
    check($copy === []);
}
foreach ([['issued_at' => 2000000001], ['last_seen' => 2000001000], ['csrf' => ''],
    ['subject' => 'slack:TOTHER:UTEST']] as $change) {
    $copy = array_replace($another, $change);
    rejected(function () use ($policy, &$copy) { $policy->authorize($copy, 2000000010); }, 'login_required');
}
foreach (['POST', 'PUT', 'PATCH', 'DELETE'] as $method) {
    $policy->checkCsrf($session, $method, 'https://public.example', $session['csrf']);
    check(true);
    foreach ([[null, $session['csrf']], ['https://outside.example', $session['csrf']],
        ['https://public.example', null], ['https://public.example', str_repeat('0', 64)]] as [$origin, $token]) {
        rejected(fn() => $policy->checkCsrf($session, $method, $origin, $token), 'csrf_rejected');
    }
}
$policy->checkCsrf($session, 'GET', null, null);
check(true);
rejected(fn() => $policy->checkCsrf($session, 'TRACE', 'https://public.example', $session['csrf']), 'csrf_rejected');
echo json_encode(['checks' => $checks, 'status' => 'passed']) . "\n";
