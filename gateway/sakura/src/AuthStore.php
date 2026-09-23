<?php
declare(strict_types=1);
namespace LaBookGateway;
use PDO;
use RuntimeException;

/** Dedicated private SQLite database; no business Users, names, or Slack tokens. */
final class AuthStore
{
    public const TTL = SessionPolicy::TTL;
    private PDO $db;
    public function __construct(string $path)
    {
        $this->db = new PDO('sqlite:' . $path, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
        // Keep DB transactions short; Slack API calls happen before this store.
        $this->db->exec('PRAGMA busy_timeout=1000; PRAGMA foreign_keys=ON');
        $this->db->exec('CREATE TABLE IF NOT EXISTS auth_users (
            id INTEGER PRIMARY KEY, slack_team_id TEXT NOT NULL, slack_user_id TEXT NOT NULL,
            created_at INTEGER NOT NULL, UNIQUE(slack_team_id, slack_user_id));
            CREATE TABLE IF NOT EXISTS auth_sessions (
            session_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES auth_users(id),
            csrf TEXT NOT NULL, generation TEXT NOT NULL, created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL, last_used_at INTEGER NOT NULL, revoked_at INTEGER);
            CREATE INDEX IF NOT EXISTS session_expiry ON auth_sessions(expires_at);');
    }
    private function query(string $sql, array $args = []): \PDOStatement
    {
        $stmt = $this->db->prepare($sql); $stmt->execute($args); return $stmt;
    }
    private function atomic(callable $action): mixed
    {
        $this->db->exec('BEGIN IMMEDIATE');
        try { $result = $action(); $this->db->exec('COMMIT'); return $result; }
        catch (\Throwable $e) { $this->db->exec('ROLLBACK'); throw $e; }
    }
    private static function validToken(string $token): bool { return preg_match('/\A[a-f0-9]{64}\z/', $token) === 1; }
    /** OIDC claims must already be verified; never pass browser identity fields. */
    public function establish(array $verified, string $oldSession, SessionPolicy $policy, int $now): array
    {
        $identity = $policy->establish($verified, $now);
        return $this->atomic(function () use ($verified, $oldSession, $identity, $now) {
            $this->query('DELETE FROM auth_sessions WHERE expires_at<=? OR revoked_at IS NOT NULL', [$now]);
            $this->query('INSERT OR IGNORE INTO auth_users(slack_team_id, slack_user_id, created_at) VALUES (?, ?, ?)',
                [$verified['team_id'], $verified['user_id'], $now]);
            $id = (int)$this->query('SELECT id FROM auth_users WHERE slack_team_id=? AND slack_user_id=?',
                [$verified['team_id'], $verified['user_id']])->fetchColumn();
            $newToken = bin2hex(random_bytes(32));
            $this->query('INSERT INTO auth_sessions VALUES (?, ?, ?, ?, ?, ?, ?, NULL)',
                [hash('sha256', $newToken), $id, $identity['csrf'], $identity['generation'], $now, $now + self::TTL, $now]);
            $this->revoke($oldSession, $now);
            return ['token' => $newToken, 'expires_at' => $now + self::TTL];
        });
    }
    public function session(string $token, SessionPolicy $policy, int $now): array
    {
        if (!self::validToken($token)) { throw new RuntimeException('login_required'); }
        $row = $this->query('SELECT s.*, u.slack_team_id, u.slack_user_id FROM auth_sessions s
            JOIN auth_users u ON u.id=s.user_id WHERE session_hash=? AND revoked_at IS NULL AND expires_at>?',
            [hash('sha256', $token), $now])->fetch(PDO::FETCH_ASSOC);
        if (!$row) { throw new RuntimeException('login_required'); }
        $identity = ['subject' => 'slack:' . $row['slack_team_id'] . ':' . $row['slack_user_id'],
            'team_id' => $row['slack_team_id'], 'issued_at' => (int)$row['created_at'],
            'last_seen' => (int)$row['last_used_at'], 'generation' => $row['generation'], 'csrf' => $row['csrf']];
        $policy->authorize($identity, $now);
        $this->query('UPDATE auth_sessions SET last_used_at=MAX(last_used_at, ?) WHERE session_hash=?', [$now, $row['session_hash']]);
        return $identity;
    }
    public function revoke(string $token, int $now): void
    {
        if (self::validToken($token)) {
            $this->query('UPDATE auth_sessions SET revoked_at=? WHERE session_hash=?', [$now, hash('sha256', $token)]);
        }
    }
}
