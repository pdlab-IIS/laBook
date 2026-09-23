<?php
declare(strict_types=1);

namespace LaBookGateway;

use RuntimeException;

/** Policy for private server-side sessions; never accepts browser identity data. */
final class SessionPolicy
{
    public const TTL = 90 * 86400;

    public function __construct(private array $config)
    {
        $origin = $config['public_origin'] ?? null;
        $parts = is_string($origin) ? parse_url($origin) : false;
        if (!is_array($parts) || ($parts['scheme'] ?? '') !== 'https'
            || !isset($parts['host']) || isset($parts['user']) || isset($parts['pass'])
            || isset($parts['path']) || isset($parts['query']) || isset($parts['fragment'])
            || !preg_match('~\Ahttps://[A-Za-z0-9.-]+(?::[0-9]+)?\z~', $origin)
            || (isset($parts['port']) && $parts['port'] < 1)
            || !is_string($config['expected_team_id'] ?? null)
            || !preg_match('/\AT[A-Z0-9]+\z/', $config['expected_team_id'])
            || !is_string($config['session_generation'] ?? null)
            || !preg_match('/\A[A-Za-z0-9_-]{1,64}\z/', $config['session_generation'])
            || !is_array($config['revoked_subjects'] ?? null)) {
            throw new RuntimeException('session_config_invalid');
        }
        foreach ($config['revoked_subjects'] as $subject) {
            if (!is_string($subject) || !preg_match('/\Aslack:T[A-Z0-9]+:[A-Z][A-Z0-9]+\z/', $subject)) {
                throw new RuntimeException('session_config_invalid');
            }
        }
    }

    /** Call only with verified OIDC claims after state, nonce and signature checks. */
    public function establish(array $verified, int $now): array
    {
        if (($verified['workspace_checked'] ?? null) !== true
            || ($verified['team_id'] ?? null) !== $this->config['expected_team_id']
            || !is_string($verified['user_id'] ?? null)
            || !preg_match('/\A[A-Z][A-Z0-9]+\z/', $verified['user_id'])
            || !is_int($verified['verified_at'] ?? null)
            || $verified['verified_at'] > $now || $now - $verified['verified_at'] > 60) {
            throw new RuntimeException('identity_rejected');
        }
        $session = ['subject' => 'slack:' . $verified['team_id'] . ':' . $verified['user_id'],
            'team_id' => $verified['team_id'], 'issued_at' => $now, 'last_seen' => $now,
            'generation' => $this->config['session_generation'], 'csrf' => bin2hex(random_bytes(32))];
        $this->authorize($session, $now);
        return $session;
    }

    /** Must run for every request, using freshly loaded private configuration. */
    public function authorize(array &$session, int $now): string
    {
        $subject = $session['subject'] ?? null;
        if (!is_string($subject)
            || !preg_match('/\Aslack:' . preg_quote($this->config['expected_team_id'], '/') . ':[A-Z][A-Z0-9]+\z/', $subject)
            || ($session['team_id'] ?? null) !== $this->config['expected_team_id']
            || ($session['generation'] ?? null) !== $this->config['session_generation']
            || in_array($subject, $this->config['revoked_subjects'], true)
            || !is_int($session['issued_at'] ?? null) || !is_int($session['last_seen'] ?? null)
            || $session['issued_at'] > $session['last_seen'] || $session['last_seen'] > $now
            || $now - $session['issued_at'] >= self::TTL
            || !is_string($session['csrf'] ?? null) || !preg_match('/\A[a-f0-9]{64}\z/', $session['csrf'])) {
            $session = [];
            throw new RuntimeException('login_required');
        }
        $session['last_seen'] = $now;
        return $subject;
    }

    /** Apply after authorize() and before any mutation, including logout. */
    public function checkCsrf(array $session, string $method, ?string $origin, ?string $token): void
    {
        if (in_array($method, ['GET', 'HEAD', 'OPTIONS'], true)) { return; }
        if (!in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'], true)
            || $origin !== $this->config['public_origin']
            || !is_string($token) || !preg_match('/\A[a-f0-9]{64}\z/', $token)
            || !is_string($session['csrf'] ?? null) || !hash_equals($session['csrf'], $token)) {
            throw new RuntimeException('csrf_rejected');
        }
    }
}
