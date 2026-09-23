<?php
declare(strict_types=1);

namespace LaBookGateway;

use InvalidArgumentException;

final class Security
{
    /** Input MUST already be verified by the Google ID-token verifier.
     * This policy alone does not authenticate an arbitrary decoded JWT.
     */
    public static function allowsVerifiedClaims(array $claims, string $domain): bool
    {
        if ($domain === '' || $domain !== strtolower($domain)) {
            return false;
        }
        $email = $claims['email'] ?? null;
        if (!is_string($email) || substr_count($email, '@') !== 1) {
            return false;
        }
        [$local, $emailDomain] = explode('@', $email, 2);
        return ($claims['hd'] ?? null) === $domain
            && ($claims['email_verified'] ?? null) === true
            && $local !== '' && strtolower($emailDomain) === $domain
            && is_string($claims['sub'] ?? null) && $claims['sub'] !== '';
    }

    public static function sign(string $secret, array $r, string $body): string
    {
        if (strlen($secret) < 32
            || !preg_match('/\A[A-Za-z0-9_-]{1,64}\z/', $r['key_id'])
            || !in_array($r['method'], ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'], true)
            || !str_starts_with($r['target'], '/') || str_starts_with($r['target'], '//')
            || str_contains($r['target'], '#')
            || !preg_match('/\A[0-9]{1,12}\z/', $r['timestamp'])
            || !preg_match('/\A[a-f0-9]{32}\z/', $r['nonce'])
            || $r['subject'] === '') {
            throw new InvalidArgumentException('Invalid signing input');
        }
        $fields = ['labook-gateway-v1', $r['key_id'], $r['method'], $r['target'],
            $r['content_type'], hash('sha256', $body), $r['timestamp'], $r['nonce'], $r['subject']];
        foreach ($fields as $field) {
            if (preg_match('/[\x00-\x1f\x7f]/', $field)) {
                throw new InvalidArgumentException('Control character in signing input');
            }
        }
        return hash_hmac('sha256', implode("\n", $fields), $secret);
    }
}
