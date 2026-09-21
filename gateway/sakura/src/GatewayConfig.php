<?php
declare(strict_types=1);
namespace LaBookGateway;
use RuntimeException;

final class GatewayConfig
{
    public static function validate(array $c): array
    {
        new SessionPolicy($c);
        $prefix = $c['public_prefix'] ?? '';
        $public = $c['public_url'] ?? '';
        if (!is_string($prefix) || !preg_match('~\A/[A-Za-z0-9_-]+(?:/index\.php)?\z~', $prefix)
            || !is_string($public) || $public !== $c['public_origin'] . preg_replace('~/index\.php\z~', '', $prefix)
            || !is_string($c['client_id'] ?? null) || !preg_match('/\A[0-9]+\.[0-9]+\z/', $c['client_id'])
            || !is_string($c['client_secret'] ?? null) || $c['client_secret'] === ''
            || !in_array($c['login_flow'] ?? null, ['workspace-entry', 'select-workspace'], true)
            || !is_bool($c['relay_enabled'] ?? null)
            || !array_key_exists('expires_at', $c)
            || ($c['expires_at'] !== null && !is_int($c['expires_at']))) {
            throw new RuntimeException('gateway_config_invalid');
        }
        if ($c['login_flow'] === 'workspace-entry'
            && (!is_string($c['workspace_login_url'] ?? null)
                || !preg_match('~\Ahttps://[a-z0-9-]+\.slack\.com/\z~', $c['workspace_login_url']))) {
            throw new RuntimeException('gateway_config_invalid');
        }
        if ($c['relay_enabled']) { new Relay($c); }
        return $c;
    }
}
