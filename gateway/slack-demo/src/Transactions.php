<?php
declare(strict_types=1);
namespace LaBookSlackDemo;
use PDO;
use RuntimeException;

final class Transactions
{
    private PDO $db;
    public function __construct(string $path)
    {
        $this->db = new PDO('sqlite:' . $path, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
        $this->db->exec('PRAGMA busy_timeout=5000');
        $this->db->exec('CREATE TABLE IF NOT EXISTS transactions (state_hash TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, nonce TEXT NOT NULL, expires INTEGER NOT NULL)');
    }
    public function create(): array
    {
        $this->db->prepare('DELETE FROM transactions WHERE expires < ?')->execute([time()]);
        $tx = ['state' => bin2hex(random_bytes(32)), 'browser' => bin2hex(random_bytes(32)),
            'nonce' => bin2hex(random_bytes(32))];
        $this->db->prepare('INSERT INTO transactions VALUES (?, ?, ?, ?)')->execute([
            hash('sha256', $tx['state']), hash('sha256', $tx['browser']), $tx['nonce'], time() + 300]);
        return $tx;
    }
    public function consume(string $state, string $browser): string
    {
        if (!preg_match('/\A[a-f0-9]{64}\z/', $state) || !preg_match('/\A[a-f0-9]{64}\z/', $browser)) {
            throw new RuntimeException('state_invalid');
        }
        $this->db->exec('BEGIN IMMEDIATE');
        try {
            $hash = hash('sha256', $state);
            $query = $this->db->prepare('SELECT * FROM transactions WHERE state_hash=?');
            $query->execute([$hash]);
            $row = $query->fetch(PDO::FETCH_ASSOC);
            if (!$row || (int)$row['expires'] < time() || !hash_equals($row['browser_hash'], hash('sha256', $browser))) {
                throw new RuntimeException('state_invalid');
            }
            $this->db->prepare('DELETE FROM transactions WHERE state_hash=?')->execute([$hash]);
            $this->db->exec('COMMIT');
            return $row['nonce'];
        } catch (\Throwable $error) {
            $this->db->exec('ROLLBACK');
            throw $error;
        }
    }
}
