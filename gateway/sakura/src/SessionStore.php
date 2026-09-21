<?php
declare(strict_types=1);
namespace LaBookGateway;
use RuntimeException;

final class SessionStore
{
    public function __construct(string $directory, private string $cookiePath)
    {
        if (!is_dir($directory) || !is_writable($directory)) { throw new RuntimeException('session_unavailable'); }
        ini_set('session.use_strict_mode', '1');
        ini_set('session.use_only_cookies', '1');
        ini_set('session.use_trans_sid', '0');
        ini_set('session.gc_maxlifetime', '3600');
        session_name('LABOOK_GATE_SESSION');
        session_save_path($directory);
        session_set_cookie_params(['lifetime' => 3600, 'path' => $cookiePath,
            'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
        if (!session_start()) { throw new RuntimeException('session_unavailable'); }
        if (!isset($_SESSION['login_csrf'])) { $_SESSION['login_csrf'] = bin2hex(random_bytes(32)); }
    }
    public function establish(array $identity): void
    {
        if (!session_regenerate_id(true)) { throw new RuntimeException('session_unavailable'); }
        $_SESSION = ['identity' => $identity, 'login_csrf' => bin2hex(random_bytes(32))];
    }
    public function close(): void
    {
        if (session_status() === PHP_SESSION_ACTIVE && !session_write_close()) {
            throw new RuntimeException('session_unavailable');
        }
    }
    public function logout(): void
    {
        $_SESSION = [];
        if (!session_destroy()) { throw new RuntimeException('session_unavailable'); }
        setcookie('LABOOK_GATE_SESSION', '', ['expires' => 1, 'path' => $this->cookiePath,
            'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
    }
}
