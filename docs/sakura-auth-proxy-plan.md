# Slack認証ゲートウェイの運用

2026-09-22に本番切替を完了。利用者によるSlack認証と既存書籍一覧の表示を確認済み。
個別の接続先・IP・ID・秘密・サーバーパスはGitに保存せず、`deploy/local/`とサーバーの非公開領域で管理する。

## 構成と利用者の動作

ブラウザ → さくらPHP（Slack認証・セッション・CSRF）→ HTTPS ngrok（さくら送信元IPv4のみ許可）→ RPi（HMAC検証）→ laBook。

- `/labook/`が本番入口。旧`/L/...`は`/labook/L/...`へ転送する。
- 未ログイン時はサービスの配色に合わせた案内画面を表示。「続行する」を押して標準Slack認証を開始する。ログイン先の表示とワークスペース文字列のコピーボタンを備え、自動開始しない。
- 指定Slackワークスペースのteam IDを検証する。Google/Notion認証、Slack Connectへの許可拡張、コマンド入力は採用しない。
- ルート画面のハンバーガーメニューに`Logout`を配置。他画面のメニューは`display: none`。
- ログアウト後は完了画面で止まり、再ログインリンクから認証を開始する。

## 認証と中継

- OIDCの署名、issuer、audience/azp、exp/iat、nonce、subject、at_hash、teamを検証。stateはブラウザ相関Cookieと照合し、5分以内に一度だけ消費する。
- ログイン開始は「続行する」からCSRFフォームをPOSTする。CSP nonce付きスクリプトはワークスペース文字列のコピーにのみ使用する。Origin検証のためログインHTMLは`Referrer-Policy: strict-origin`。
- 2026-09-23、Android ChromeでSlackアプリへ移動して戻れない問題の比較検証のため、非公開設定の`login_flow`だけを`workspace-entry`から標準の`select-workspace`へ切り替えた。旧設定は非公開領域にバックアップ済み。クエリから方式を変更させない。
- 切替後、公開入口から標準認証URLへの遷移、callback先、state・nonce、相関Cookie、認可キャンセル時の拒否を確認済み。その後、利用者からAndroid Chromeでサービスを開けたとの報告を受領。標準経路を継続する。
- 認証セッションは発行から固定90日。DBにはopaque IDのハッシュだけを保存し、ログアウトで失効する。業務Usersと自動結合しない。
- 90日への変更は変更後のログインから適用する。既存セッションのDB・Cookieの期限は延長せず、次回ログイン時に90日で発行する。
- 90日内にSlack所属を再照会しない。毎要求で許可team、設定世代、失効対象を確認する。全失効は`session_generation`、個別拒否は`revoked_subjects`で管理。
- CookieはSecure/HttpOnly、専用Path、Domainなし。preauthは1時間、OAuth相関は5分、認証済みは90日で分離する。
- 更新操作はOriginとCSRFを必須とし、自動再送しない。ブラウザCookieやAuthorizationをRPiへ転送しない。
- PHPは固定HTTPS上流だけに接続し、TLS検証・IPv4固定・転送追跡禁止を適用。HMACはmethod、raw target、本文ハッシュ、時刻、nonce、主体を署名する。
- RPiは全ルートで署名・固定Host・時刻±60秒・SQLite nonce再送防止を検証。本番用の鍵とnonce DBは試験から分離する。
- 認可コード・OAuthトークンをDB保存しない。ホスティングのアクセスログを共有する場合は認証クエリを除く。

## 本番配置と切り戻し

- WordPressのコード・DB・全体設定は変更していない。共有`.htaccess`のWordPressブロックはバイト単位で維持し、laBook専用ルールを外側に配置した。
- RPiの新リリースは既存の業務DB・表紙を共用する。試験DBは持ち込まず、schema変更も行っていない。切替前にSQLite backup APIでバックアップし、整合性を確認した。
- `labook-gateway.service`と`labook-gateway-ngrok.service`を自動起動する。本番は試験の24時間停止・公開期限を持たない。
- 旧laBook・旧ngrokは切り戻し用に維持する。これらは今回の不要リソース削除の対象外。
- 実配置は`deploy/local/production-cutover.local.json`、運用手順は`production-operations.local.md`、検証・清掃結果は`production-*-result.local.json`などを参照。
- `deploy/local/rollback_production.local.py --execute`で元のルーティングを復元できる。共有`.htaccess`が切替直後のハッシュから変わっていれば停止し、後日の変更を上書きしない。
- 切り戻し時に業務DBを古いバックアップへ戻さない。切替後の登録・貸出・返却を保持するため、現行DBを継続使用する。

## 検証済み事項と制約

- PHP認証・境界・DBセッション136チェック、OAuth HTTP50チェック、runtime JS試験を実施。
- RPi別DBの実アプリ34チェックで署名、nonce競合、業務操作、prefix、multipart転送を確認。
- 試験環境の実ブラウザで更新・貸出/返却・正常JPEGのWeb PHPアップロード/保存/表示を確認。利用者も手動操作に問題なしと回答。
- 試験アプリの一時停止でPHP Relayの約20秒タイムアウトと復旧後200を確認。ブラウザ障害画面自体の検証とは区別する。
- 本番読み取り7チェック、新ngrok4チェック、公開認証境界と棚転送、WordPress代表応答、DB整合性、本番サービス不変を確認。実Slack認証後の一覧も利用者確認済み。
- 中継の接続5秒/全体20秒、要求8MiB/応答16MiB/ヘッダー32KiB上限。PHP実測はupload 5M/post 8M/memory 128M/30秒。大容量時にPHPの413が外部403へ変換される既知の挙動がある。
- 旧公開デモ・試験入口、非公開試験配置、停止済みRPi試験配置を削除済み。再試験には新しい隔離ディレクトリ・DB・鍵を用意する。

## 開発時の確認

- Python: `python -m pytest tests/test_gateway_signing.py tests/test_gateway_inbound.py tests/test_gateway_http.py -q`（WindowsではGunicorn実通信試験をスキップ）。
- JavaScript: `node tests/test_runtime.cjs`。
- PHP: `scripts/check_sakura_gateway.py`で新しい非公開試験領域へ配備して実行する。
- 再現用デモ・隔離試験のソースは維持する。削除済みの実配置を参照する古い設定で配備スクリプトを再実行しない。
