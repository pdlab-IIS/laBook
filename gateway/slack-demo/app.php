<?php
declare(strict_types=1);

use LaBookSlackDemo\Oidc;
use LaBookSlackDemo\Transactions;

ini_set('display_errors', '0');
umask(0077);
header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: private, no-store, max-age=0');
header('Expires: 0');
header('Referrer-Policy: no-referrer');
header('X-Content-Type-Options: nosniff');
header('X-Robots-Tag: noindex, nofollow');
header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://slack.com; base-uri 'none'; frame-ancestors 'none'");

function h(string $value): string { return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
function sessionOpen(string $stateDir, string $cookiePath): void
{
    ini_set('session.use_strict_mode', '1');
    ini_set('session.use_only_cookies', '1');
    ini_set('session.gc_maxlifetime', '1800');
    session_name('LABOOK_SLACK_DEMO');
    session_save_path($stateDir . '/sessions');
    session_set_cookie_params(['lifetime' => 1800, 'path' => $cookiePath,
        'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
    if (!session_start()) { throw new RuntimeException('session_unavailable'); }
    if (!isset($_SESSION['csrf'])) { $_SESSION['csrf'] = bin2hex(random_bytes(32)); }
}
function scalarInput(array $source, string $key): string
{
    $value = $source[$key] ?? '';
    return is_string($value) ? $value : '';
}

$message = null;
$result = null;
$ready = false;
$config = [];
$stage = 'setup';
$failureCode = null;
$workspaceLoginUrl = '';
$flow = 'select-workspace';
try {
    $config = json_decode(file_get_contents(__DIR__ . '/config.local.json'), true, 16, JSON_THROW_ON_ERROR);
    $publicUrl = $config['public_url'] ?? '';
    $url = parse_url($publicUrl);
    if (!is_array($url) || ($url['scheme'] ?? '') !== 'https' || !isset($url['host'])
        || isset($url['query']) || isset($url['fragment']) || isset($url['user'])
        || !str_ends_with($url['path'] ?? '', '/slack-signin-demo')) {
        throw new RuntimeException('config_invalid');
    }
    if (($_SERVER['HTTPS'] ?? '') !== 'on' || strtolower($_SERVER['HTTP_HOST'] ?? '') !== strtolower($url['host'])) {
        http_response_code(400); exit('このデモは設定されたHTTPS URLから開いてください。');
    }
    $cookiePath = $url['path'] . '/';
    $loginUrl = $config['workspace_login_url'] ?? '';
    // Only a configured Slack home page; never carry OAuth state or a return URL.
    if (is_string($loginUrl) && preg_match('~\Ahttps://[a-z0-9-]+(?:\.enterprise)?\.slack\.com/\z~', $loginUrl)) {
        $workspaceLoginUrl = $loginUrl;
    }
    $stateDir = __DIR__ . '/state';
    if (!is_int($config['expires_at'] ?? null) || time() >= $config['expires_at']) {
        http_response_code(410); exit('この試験用デモの公開期限は終了しました。');
    }
    $ready = is_string($config['client_id'] ?? null) && preg_match('/\A[0-9]+\.[0-9]+\z/', $config['client_id'])
        && is_string($config['client_secret'] ?? null) && $config['client_secret'] !== ''
        && is_string($config['expected_team_id'] ?? null)
        && ($config['expected_team_id'] === '' || preg_match('/\AT[A-Z0-9]+\z/', $config['expected_team_id']));
    require __DIR__ . '/vendor/autoload.php';
    require __DIR__ . '/src/Oidc.php';
    require __DIR__ . '/src/Transactions.php';

    if ($demoAction === 'callback') {
        $stage = 'callback';
        // Some Slack authorization flows return a query redirect even when
        // form_post was requested. Both transports use the same state checks.
        if (!in_array($_SERVER['REQUEST_METHOD'], ['GET', 'POST'], true) || !$ready
            || (int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 16384
            || strlen($_SERVER['QUERY_STRING'] ?? '') > 16384) {
            throw new RuntimeException('callback_invalid');
        }
        $callback = $_SERVER['REQUEST_METHOD'] === 'POST' ? $_POST : $_GET;
        if (scalarInput($callback, 'state') === '') { throw new RuntimeException('state_missing'); }
        if (scalarInput($_COOKIE, 'LABOOK_SLACK_TX') === '') { throw new RuntimeException('cookie_missing'); }
        $nonce = (new Transactions($stateDir . '/transactions.sqlite'))->consume(
            scalarInput($callback, 'state'), scalarInput($_COOKIE, 'LABOOK_SLACK_TX'));
        setcookie('LABOOK_SLACK_TX', '', ['expires' => 1, 'path' => $cookiePath,
            'secure' => true, 'httponly' => true, 'samesite' => 'None']);
        sessionOpen($stateDir, $cookiePath);
        session_regenerate_id(true);
        unset($_SESSION['result']);
        try {
            if (scalarInput($callback, 'error') !== '') { throw new RuntimeException('access_denied'); }
            $code = scalarInput($callback, 'code');
            if ($code === '' || strlen($code) > 4096) { throw new RuntimeException('callback_invalid'); }
            $_SESSION['result'] = Oidc::exchange($config, $code, $nonce);
            unset($_SESSION['error']);
        } catch (Throwable $error) {
            $known = ['access_denied', 'workspace_mismatch', 'slack_unavailable', 'token_exchange_failed'];
            $_SESSION['error'] = in_array($error->getMessage(), $known, true) ? $error->getMessage() : 'verification_failed';
        }
        session_write_close();
        header('Location: ' . $publicUrl . '/index.php', true, 303); exit;
    }

    $stage = 'start';
    $requestedFlow = scalarInput($_GET, 'flow');
    $flow = in_array($requestedFlow, ['current', 'standard', 'select-workspace', 'workspace-entry'], true) ? $requestedFlow : 'select-workspace';
    sessionOpen($stateDir, $cookiePath);
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!hash_equals($_SESSION['csrf'], scalarInput($_POST, 'csrf'))) { throw new RuntimeException('csrf_invalid'); }
        $action = scalarInput($_POST, 'action');
        if ($action === 'clear') {
            $_SESSION = [];
            session_regenerate_id(true);
            session_write_close();
            header('Location: ' . $publicUrl . '/index.php', true, 303); exit;
        }
        if ($action !== 'login' || !$ready) { throw new RuntimeException('not_configured'); }
        if (time() - ($_SESSION['last_start'] ?? 0) < 5) { throw new RuntimeException('try_later'); }
        $_SESSION['last_start'] = time();
        unset($_SESSION['result'], $_SESSION['error']);
        $tx = (new Transactions($stateDir . '/transactions.sqlite'))->create();
        setcookie('LABOOK_SLACK_TX', $tx['browser'], ['expires' => time() + 300, 'path' => $cookiePath,
            'secure' => true, 'httponly' => true, 'samesite' => 'None']);
        session_write_close();
        $authorizationUrl = Oidc::authorizationUrl($config, $tx, $flow);
        if ($flow === 'workspace-entry') {
            // Commit a same-origin response before navigating: form-action can
            // otherwise block the POST's redirect chain through enterprise SSO.
            // The destination comes solely from validated private config.
            echo '<!doctype html><html lang="ja"><meta charset="utf-8">'
                . '<meta name="viewport" content="width=device-width, initial-scale=1">'
                . '<meta http-equiv="refresh" content="0;url=' . h($authorizationUrl) . '">'
                . '<title>Slackへ移動します</title><p>Slackへ移動します。</p>'
                . '<p><a rel="noreferrer" href="' . h($authorizationUrl) . '">移動しない場合はこちら</a></p></html>';
            exit;
        }
        header('Location: ' . $authorizationUrl, true, 303); exit;
    }
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') { http_response_code(405); exit; }
    $result = $_SESSION['result'] ?? null;
    if ($result && time() - $result['verified_at'] > 900) { unset($_SESSION['result']); $result = null; }
    $messages = ['access_denied' => 'Slackで認可がキャンセルまたは拒否されました。',
        'workspace_mismatch' => 'Slackでの本人確認は完了しましたが、対象ワークスペースが一致しません。',
        'slack_unavailable' => 'Slackへの接続を完了できませんでした。時間をおいて再試行してください。',
        'token_exchange_failed' => '認可コードの交換に失敗しました。Slack Appの設定を確認してください。',
        'verification_failed' => 'ログイン結果を安全に検証できなかったため、成功とは判定しませんでした。'];
    $message = $messages[$_SESSION['error'] ?? ''] ?? null;
    $csrf = $_SESSION['csrf'];
    session_write_close();
} catch (Throwable $error) {
    http_response_code(400);
    $failures = [
        'callback_invalid' => 'Slackからの応答の形式を確認できませんでした。デモのトップからやり直してください。',
        'state_missing' => 'ログインの確認情報がありません。デモのトップからログインを開始してください。',
        'cookie_missing' => 'ログインを開始したブラウザのCookieを確認できませんでした。同じブラウザでCookieを許可して、トップからやり直してください。',
        'state_invalid' => 'ログインの有効時間（5分）が過ぎたか、別の試行または使用済みの応答です。トップからログインを1回だけ開始してください。',
        'csrf_invalid' => '画面の有効時間が過ぎたか、Cookieを確認できませんでした。トップを開き直してください。',
        'try_later' => '5秒ほど待ってから、トップでログインを開始してください。',
        'session_unavailable' => 'デモのログイン状態を保存できませんでした。サーバー側の確認が必要です。',
    ];
    $failureCode = array_key_exists($error->getMessage(), $failures) ? $error->getMessage() : 'internal_error';
    $message = $failures[$failureCode] ?? 'この試行を完了できませんでした。デモのトップからやり直してください。';
    // Private, bounded diagnostics: never record URLs, codes, tokens, cookies,
    // identity data, or raw exception messages.
    $diagnostic = ['time' => gmdate('c'), 'stage' => $stage, 'reason' => $failureCode,
        'method' => in_array($_SERVER['REQUEST_METHOD'] ?? '', ['GET', 'POST'], true) ? $_SERVER['REQUEST_METHOD'] : 'other'];
    $log = @fopen(__DIR__ . '/state/failures.jsonl', 'c+');
    if ($log !== false) {
        if (flock($log, LOCK_EX)) {
            if (fstat($log)['size'] > 65536) { ftruncate($log, 0); }
            fseek($log, 0, SEEK_END);
            fwrite($log, json_encode($diagnostic) . "\n");
            flock($log, LOCK_UN);
        }
        fclose($log);
    }
    $ready = false;
    $csrf = '';
}
?>
<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in with Slack 動作確認</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f6f5f8;color:#20202b;font:16px/1.7 system-ui,sans-serif}
main{max-width:760px;margin:64px auto;padding:36px;background:white;border:1px solid #e4e1e9;border-radius:18px}
.eyebrow{color:#674477;font-size:13px;font-weight:700;letter-spacing:.08em}h1{font-size:30px;line-height:1.4;margin:8px 0 18px}
p{margin:12px 0}.muted{color:#656272;font-size:14px}.status{padding:16px 20px;background:#f1edf5;border-radius:10px;margin:24px 0}
.success{background:#e7f5ed;color:#165c37}.error{background:#fff0e8;color:#853b16}button{font:inherit;font-weight:700;cursor:pointer;border:1px solid #d0c8d8;border-radius:8px;padding:12px 22px;background:#4a154b;color:white}
button.secondary{background:white;color:#4a154b}.slack-mark{font-size:22px;margin-right:10px}ol{padding-left:24px}a{color:#5b2872}code{overflow-wrap:anywhere;font-size:13px}dl{display:grid;grid-template-columns:140px 1fr;gap:10px}dt{color:#656272}dd{margin:0;overflow-wrap:anywhere}@media(max-width:640px){main{margin:20px 12px;padding:24px}h1{font-size:25px}dl{grid-template-columns:1fr;gap:4px}dd{margin-bottom:12px}}
</style>
<main><div class="eyebrow">LABOOK / LOGIN DEMO</div><h1>Sign in with Slack<br>動作確認</h1>
<p>利用中のSlackでログインできるかを確認するデモです。</p><p class="muted">laBookのデータやSlackのメッセージにはアクセスしません。</p>
<?php if ($message): ?><div class="status error" role="alert"><?= h($message) ?></div><?php endif; ?>
<?php if ($failureCode): ?><p class="muted">確認用コード：<?= h($failureCode) ?></p><?php endif; ?>
<?php if ($result): ?>
<div class="status success"><strong>Slackログインに成功しました</strong><br>署名・認可先・有効期限・今回のログインとの対応を検証済みです。</div>
<dl><dt>表示名</dt><dd><?= h($result['name']) ?></dd><dt>メール</dt><dd><?= h($result['email']) ?></dd>
<dt>Workspace ID</dt><dd><?= h($result['team_id']) ?></dd><dt>User ID</dt><dd><?= h($result['user_id']) ?></dd>
<dt>対象との一致</dt><dd><?= $result['workspace_checked'] ? '一致しました' : '対象IDは未設定です。このWorkspace IDを設定すると一致も試験できます。' ?></dd></dl>
<p class="muted">この結果は15分で消えます。メンバーの継続在籍確認やlaBookへのアクセス許可は、このデモでは行いません。</p>
<?php elseif (!$ready && !$message): ?>
<div class="status"><strong>Slack Appの設定待ち</strong><br>デモは準備できています。以下の設定後にログインを試せます。</div>
<ol><li><a href="https://api.slack.com/apps" target="_blank" rel="noreferrer">Slack App管理画面</a>で「Create New App」→「From scratch」を選び、利用中のワークスペースに試験用アプリを作成します。</li>
<li>「OAuth &amp; Permissions」のRedirect URLsに次を登録します。<br><code><?= h(($config['public_url'] ?? '') . '/callback.php') ?></code></li>
<li>Client ID・Client Secretをサーバーの非公開設定ファイルへ登録します。対象Workspace IDは任意です。</li></ol>
<p class="muted">要求する権限はログイン用のopenid・profile・emailだけです。Botやメッセージ閲覧の権限は不要です。</p>
<?php endif; ?>
<?php if ($ready && !$result && $flow === 'workspace-entry'): ?>
<div class="status"><strong>ワークスペースの入力を省く試験</strong>
<p>下のボタンから、そのままログインしてください。ワークスペースの入力や事前ログインを省けるか確認します。</p>
<p class="muted">この経路は動作確認中です。成功・失敗と、止まった画面をお知らせください。</p></div>
<?php elseif ($ready && !$result && $flow === 'select-workspace'): ?>
<p>下のボタンから進み、普段利用しているSlackワークスペースを選択または入力してください。</p>
<?php elseif ($ready && !$result && $flow === 'standard'): ?>
<div class="status"><strong>追加手順なしでログインする試験</strong>
<p>Slackにログインしていないブラウザで、下のボタンからそのまま進んでください。先にSlackを開く操作は不要です。</p>
<p class="muted">この経路は動作確認中です。成功・失敗と、止まった画面をお知らせください。</p></div>
<?php elseif ($ready && !$result && $workspaceLoginUrl !== ''): ?>
<div class="status"><strong>このブラウザでSlackにログインしていない場合</strong>
<ol><li><a href="<?= h($workspaceLoginUrl) ?>" target="_blank" rel="noopener noreferrer">先にSlackへログイン（別タブ）</a>し、ブラウザでワークスペースが開くまで進んでください。</li>
<li>このタブに戻り、下の「Sign in with Slack」を押してください。</li></ol>
<p class="muted">Slackで「問題が発生しました」と表示された場合も、この手順をお試しください。Slackにログイン済みなら、そのまま下のボタンで進めます。</p></div>
<?php endif; ?>
<?php if ($ready): ?><form method="post"><input type="hidden" name="csrf" value="<?= h($csrf) ?>"><input type="hidden" name="action" value="login"><button type="submit"><span class="slack-mark" aria-hidden="true">#</span>Sign in with Slack</button></form><?php endif; ?>
<?php if ($result || $message): ?><p><a href="<?= h(($config['public_url'] ?? '') . '/index.php') ?>">デモのトップへ</a></p><?php endif; ?>
<?php if ($result): ?><form method="post"><input type="hidden" name="csrf" value="<?= h($csrf) ?>"><input type="hidden" name="action" value="clear"><button class="secondary">このデモの結果を消す</button></form><?php endif; ?>
<p class="muted">Slack自体からログアウトしたり、既存のWordPress・laBookのログイン状態を変更したりする機能はありません。</p></main></html>
