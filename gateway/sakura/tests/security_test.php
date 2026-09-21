<?php
declare(strict_types=1);
require __DIR__ . '/../src/Security.php';
use LaBookGateway\Security;

$valid = ['sub' => 'test-subject', 'hd' => 'workspace.example',
    'email' => 'person@workspace.example', 'email_verified' => true];
$cases = [
    [$valid, true],
    [array_replace($valid, ['hd' => null]), false],
    [array_replace($valid, ['hd' => 'other.example']), false],
    [array_replace($valid, ['hd' => 'child.workspace.example']), false],
    [array_replace($valid, ['email' => 'person@workspace.example.attacker.example']), false],
    [array_replace($valid, ['email' => 'person@other.example']), false],
    [array_replace($valid, ['email_verified' => false]), false],
    [array_replace($valid, ['email_verified' => 'true']), false],
    [array_replace($valid, ['sub' => '']), false],
];
foreach ($cases as [$claims, $expected]) {
    if (Security::allowsVerifiedClaims($claims, 'workspace.example') !== $expected) {
        throw new RuntimeException('Domain policy test failed');
    }
}
$vectors = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
foreach ($vectors as $v) {
    $signature = Security::sign(base64_decode($v['secret'], true), $v['request'], base64_decode($v['body'], true));
    if (!hash_equals($v['expected'], $signature)) {
        throw new RuntimeException('Cross-language signature test failed');
    }
}
echo json_encode(['domain_cases' => count($cases), 'signature_vectors' => count($vectors), 'status' => 'passed']);
