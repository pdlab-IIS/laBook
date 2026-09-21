<?php
declare(strict_types=1);
require __DIR__ . '/../src/SessionStore.php';
use LaBookGateway\SessionStore;
$checks=0;
function check(bool $ok): void { global $checks; ++$checks; if (!$ok) { throw new RuntimeException('Session store test failed'); } }
$directory = sys_get_temp_dir() . '/labook-session-' . bin2hex(random_bytes(8));
mkdir($directory, 0700);
try {
    $store = new SessionStore($directory, '/trial/');
    $before = session_id();
    $params = session_get_cookie_params();
    check($params['secure'] && $params['httponly'] && $params['samesite'] === 'Lax' && $params['path'] === '/trial/');
    check(session_name() === 'LABOOK_GATE_SESSION' && ini_get('session.use_strict_mode') === '1');
    $store->establish(['subject'=>'slack:TTEST:UTEST']);
    $after = session_id();
    check($before !== $after);
    $store->close();
    check(session_status() === PHP_SESSION_NONE);
    check(!file_exists($directory . '/sess_' . $before));
    session_id($after);
    $store = new SessionStore($directory, '/trial/');
    check($_SESSION['identity']['subject'] === 'slack:TTEST:UTEST');
    $store->logout();
    check(!file_exists($directory . '/sess_' . $after));
    $fake = bin2hex(random_bytes(16));
    session_id($fake);
    $store = new SessionStore($directory, '/trial/');
    check(session_id() !== $fake && !isset($_SESSION['identity']));
    $store->close();
} finally {
    if (session_status() === PHP_SESSION_ACTIVE) { session_write_close(); }
    foreach (glob($directory . '/*') as $file) { unlink($file); }
    rmdir($directory);
}
echo json_encode(['checks'=>$checks,'status'=>'passed']) . "\n";
