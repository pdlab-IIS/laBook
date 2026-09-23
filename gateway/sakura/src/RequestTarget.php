<?php
declare(strict_types=1);
namespace LaBookGateway;
use RuntimeException;

final class RequestTarget
{
    public static function validate(string $target): string
    {
        if (!str_starts_with($target, '/') || str_starts_with($target, '//')
            || preg_match('/[^\x21-\x7e]|#/', $target)) {
            throw new RuntimeException('target_invalid');
        }
        $path = explode('?', $target, 2)[0];
        if (str_contains($path, '\\') || str_contains($path, '//')
            || preg_match('/%(?![a-f0-9]{2})|%(?:2f|5c|25)/i', $path)) {
            throw new RuntimeException('target_invalid');
        }
        $decoded = rawurldecode($path);
        if (!preg_match('//u', $decoded) || preg_match('/[\x00-\x1f\x7f]/', $decoded)
            || in_array('.', explode('/', $decoded), true) || in_array('..', explode('/', $decoded), true)) {
            throw new RuntimeException('target_invalid');
        }
        return $target;
    }

    public static function stripPrefix(string $target, string $prefix): string
    {
        self::validate($target);
        if (!str_starts_with($target, $prefix . '/')) { throw new RuntimeException('target_invalid'); }
        return self::validate(substr($target, strlen($prefix)));
    }

    public static function returnPath(string $candidate, string $prefix): string
    {
        try {
            $target = self::stripPrefix($candidate, $prefix);
            $path = rawurldecode(explode('?', $target, 2)[0]);
            if ($path === '/_auth' || str_starts_with($path, '/_auth/')) {
                throw new RuntimeException('target_invalid');
            }
            return $candidate;
        } catch (RuntimeException $e) { return $prefix . '/'; }
    }
}
