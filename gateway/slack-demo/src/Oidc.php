<?php
declare(strict_types=1);
namespace LaBookSlackDemo;

use Firebase\JWT\JWK;
use Firebase\JWT\JWT;
use RuntimeException;

final class Oidc
{
    public const AUTHORIZE = 'https://slack.com/openid/connect/authorize';
    public const TOKEN = 'https://slack.com/api/openid.connect.token';
    public const KEYS = 'https://slack.com/openid/connect/keys';

    public static function authorizationUrl(array $config, array $transaction, string $flow = 'select-workspace'): string
    {
        if ($flow === 'workspace-entry') { return self::workspaceEntryUrl($config, $transaction); }
        if (!in_array($flow, ['current', 'standard', 'select-workspace'], true)) {
            throw new RuntimeException('flow_invalid');
        }
        $params = ['response_type' => 'code',
            'scope' => 'openid profile email', 'client_id' => $config['client_id'],
            'redirect_uri' => $config['public_url'] . '/callback.php',
            'state' => $transaction['state'], 'nonce' => $transaction['nonce']];
        // The Slack code-flow example omits response_mode. Compare that request
        // through enterprise SSO without changing team or verification policy.
        if ($flow === 'current') { $params['response_mode'] = 'form_post'; }
        // Omit only the UI hint for this comparison. The expected team in
        // config remains intact and is still enforced by verify().
        if ($config['expected_team_id'] !== '' && $flow !== 'select-workspace') {
            $params['team'] = $config['expected_team_id'];
        }
        return self::AUTHORIZE . '?' . http_build_query($params, '', '&', PHP_QUERY_RFC3986);
    }

    private static function workspaceEntryUrl(array $config, array $transaction): string
    {
        $home = $config['workspace_login_url'] ?? '';
        if (!is_string($home) || !preg_match('~\Ahttps://[a-z0-9-]+\.slack\.com/\z~', $home)
            || !is_string($config['expected_team_id'] ?? null)
            || !preg_match('/\AT[A-Z0-9]+\z/', $config['expected_team_id'])) {
            throw new RuntimeException('workspace_entry_invalid');
        }
        // Experimental: reproduce the relative continuation observed after
        // choosing a workspace in Slack's UI. This is not a documented OIDC
        // endpoint. All identities still go through exchange() and verify().
        $params = ['client_id' => $config['client_id'], 'scope' => '',
            'user_scope' => 'openid,profile,email',
            'redirect_uri' => $config['public_url'] . '/callback.php',
            'state' => $transaction['state'], 'granular_bot_scope' => '1',
            'single_channel' => '0', 'install_redirect' => '', 'tracked' => '1',
            'user_default' => '0', 'openid_connect' => '1',
            'nonce' => $transaction['nonce'], 'response_type' => 'code',
            'team' => '', 'original_team' => ''];
        $resume = '/oauth?' . http_build_query($params, '', '&', PHP_QUERY_RFC3986);
        return $home . '?' . http_build_query(['redir' => $resume], '', '&', PHP_QUERY_RFC3986);
    }

    public static function httpJson(string $url, ?array $form = null): array
    {
        if (!in_array($url, [self::TOKEN, self::KEYS], true)) {
            throw new RuntimeException('endpoint_rejected');
        }
        $curl = curl_init($url);
        $body = '';
        curl_setopt_array($curl, [CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_CONNECTTIMEOUT => 5, CURLOPT_TIMEOUT => 12,
            CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
            CURLOPT_PROTOCOLS => CURLPROTO_HTTPS,
            CURLOPT_WRITEFUNCTION => static function ($handle, string $chunk) use (&$body): int {
                if (strlen($body) + strlen($chunk) > 131072) { return 0; }
                $body .= $chunk;
                return strlen($chunk);
            }]);
        if ($form !== null) {
            curl_setopt_array($curl, [CURLOPT_POST => true,
                CURLOPT_POSTFIELDS => http_build_query($form, '', '&', PHP_QUERY_RFC3986),
                CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded']]);
        }
        $success = curl_exec($curl);
        $status = curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
        curl_close($curl);
        if ($success === false || $status !== 200) { throw new RuntimeException('slack_unavailable'); }
        $value = json_decode($body, true, 32, JSON_THROW_ON_ERROR);
        if (!is_array($value)) { throw new RuntimeException('slack_invalid_response'); }
        return $value;
    }

    public static function exchange(array $config, string $code, string $nonce): array
    {
        $tokens = self::httpJson(self::TOKEN, ['grant_type' => 'authorization_code',
            'client_id' => $config['client_id'], 'client_secret' => $config['client_secret'],
            'code' => $code, 'redirect_uri' => $config['public_url'] . '/callback.php']);
        if (($tokens['ok'] ?? false) !== true || !is_string($tokens['id_token'] ?? null)
            || !is_string($tokens['access_token'] ?? null)) {
            throw new RuntimeException('token_exchange_failed');
        }
        // Tokens exist only for this request; they are never stored or displayed.
        return self::verify($tokens['id_token'], self::httpJson(self::KEYS),
            $config, $nonce, $tokens['access_token']);
    }

    public static function verify(string $token, array $jwks, array $config, string $nonce, string $accessToken): array
    {
        $keys = array_values(array_filter($jwks['keys'] ?? [], static fn ($key) =>
            is_array($key) && ($key['kty'] ?? null) === 'RSA'
            && ($key['alg'] ?? 'RS256') === 'RS256' && ($key['use'] ?? 'sig') === 'sig'));
        if (!$keys) { throw new RuntimeException('keys_invalid'); }
        JWT::$leeway = 30;
        $claims = (array) JWT::decode($token, JWK::parseKeySet(['keys' => $keys], 'RS256'));
        $now = time();
        $aud = $claims['aud'] ?? null;
        $audiences = is_string($aud) ? [$aud] : (is_array($aud) ? $aud : []);
        if (($claims['iss'] ?? null) !== 'https://slack.com'
            || !in_array($config['client_id'], $audiences, true)
            || (count($audiences) > 1 && ($claims['azp'] ?? null) !== $config['client_id'])
            || (isset($claims['azp']) && $claims['azp'] !== $config['client_id'])
            || !is_int($claims['exp'] ?? null) || $claims['exp'] < $now - 30
            || !is_int($claims['iat'] ?? null) || $claims['iat'] > $now + 30
            || !is_string($claims['nonce'] ?? null) || !hash_equals($nonce, $claims['nonce'])
            || !is_string($claims['sub'] ?? null) || $claims['sub'] === '') {
            throw new RuntimeException('claims_invalid');
        }
        $team = $claims['https://slack.com/team_id'] ?? null;
        $user = $claims['https://slack.com/user_id'] ?? null;
        if (!is_string($team) || !preg_match('/\AT[A-Z0-9]+\z/', $team)
            || !is_string($user) || $user !== $claims['sub']) {
            throw new RuntimeException('identity_invalid');
        }
        if ($config['expected_team_id'] !== '' && $team !== $config['expected_team_id']) {
            throw new RuntimeException('workspace_mismatch');
        }
        if (isset($claims['at_hash'])) {
            $hash = rtrim(strtr(base64_encode(substr(hash('sha256', $accessToken, true), 0, 16)), '+/', '-_'), '=');
            if (!is_string($claims['at_hash']) || !hash_equals($hash, $claims['at_hash'])) {
                throw new RuntimeException('token_binding_invalid');
            }
        }
        return ['user_id' => $user, 'team_id' => $team,
            'name' => is_string($claims['name'] ?? null) ? $claims['name'] : '',
            'email' => is_string($claims['email'] ?? null) ? $claims['email'] : '',
            'email_verified' => ($claims['email_verified'] ?? false) === true,
            'workspace_checked' => $config['expected_team_id'] !== '', 'verified_at' => $now];
    }
}
