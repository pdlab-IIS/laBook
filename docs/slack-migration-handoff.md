# Slack認証移行・再開用要約

更新: 2026-09-21。最新の作業指示は「一旦状況をまとめ、コミットしてプッシュ」。本書はその区切りの引継ぎ記録。
正本は [移行手順](sakura-auth-proxy-plan.md)。この要約と正本から作業を再開する。

## 目的・制約

- 現在のngrok OAuthの3MAU制限への依存を外し、所有ドメインのさくらPHPでSlack認証・セッション・中継を行う。
- 中継先は固定ngrok→RPi laBook。さくら送信元IP制限とHMACを併用。秘密鍵はブラウザへ渡さない。
- Google Workspace OAuthは利用不可。Notion認証、Slack Connect・ゲストへの拡張は保留。Botの追加権限は未取得で、今回の必須条件にしない。
- 指定Workspace IDに一致するSlack OIDC利用者が対象。メール/表示名による許可や既存laBook Usersへの自動結合はしない。
- WordPressのコード・DB・プラグイン・テーマ・全体PHP/WAF設定は触らない。共有.htaccessは将来の切替時にlaBookルールだけ最小変更する。
- 現行laBookとngrok OAuthを準備中維持する。個別ネットワーク情報・設定・秘密・実機レポートはGit外。コミット対象は準備実装・テンプレート・試験・文書のみ。

## 到達点

Slack実ログインは9月17日までの記録。9月21日は以下の署名入口とセッション部品試験を追加。公開デモの期限は変更していない。

- 本番切替は未実施。RPi本番には新しい認証部品を組み込んでいない。PHP認証入口/中継とprefix対応は実装済みだが、新しい公開入口の配備・実SSO・ngrokとの結合試験は未実施。
- さくらSSHとWeb PHP 8.2.32を確認済み。upload 5M/post 8M/memory 128M/30秒。IPv4外向きIPは実測し非公開記録へ保存済みだが再測定する。
- multipartは生本文が取得できないため再構成して最終本文へ署名する。PHPの413が外部403になる件は未解決。
- RPi新接続先をユーザーから取得し接続成功。現行サービスactive、作業ツリーclean。新しい専用ディレクトリだけに試験を配備した。
- gateway/inbound.py と gateway/wsgi.py を追加。非公開設定必須、固定Host/origin/prefix、全ルート署名検証、本文上限、認証ヘッダー除去、private/no-store。従来の起動入口は維持し、ローカルapp.pyの変更は画面へ公開可能な実行設定を渡す部分のみ。本番コードは未変更。
- ローカル16テスト＋53サブテスト成功。WindowsではHTTP4テストをスキップ。RPiでは2ワーカーのGunicorn実HTTP込み20テスト成功。試験プロセスは終了済み。専用プローブのみで業務DBを開いていない。
- gateway/sakura/app.phpにログイン・GET/POST callback・セッションAPI・ログアウト・中継を接続。SessionStoreは専用Cookie/保存先/ログイン時ID再発行、LoginTransactionsは一回限りstate/ブラウザ照合/安全な復帰先を保存。公開ID確認モードやflowクエリによる切替を持たない。
- PHPの対象team/30分・60分期限/設定世代/個別失効/Origin・CSRFは54チェック成功。パス・設定・復帰先・署名ヘッダー等50チェック、実PHPセッション保存/ID再発行/破棄8チェックも成功（合計112）。実HTTPと実SSOは未試験。
- Relayは固定HTTPS、TLS検証、IPv4固定、リダイレクト追跡なし、認証ヘッダー非転送、要求署名、応答上限/タイムアウト、Location写像を実装。実ngrok転送は未試験。multipartは現行の単一JPEG cover操作に限定して再構成する。PHPで潰れる重複フィールドの扱いと上限時の外部応答は引き続き確認が必要。
- static/runtime.js と各画面を共通URL/CSRF通信へ変更。/、/labook、試験用index.php prefixの4画面を試験DBで確認。JSでmultipart保持、CSRF取得共用、外部URL拒否、失敗更新を自動再送しないことを確認。
- ローカル全体120テスト・121サブテスト成功、WindowsのGunicorn実HTTP4件はスキップ。その後prefix境界の追加試験は10テスト・38サブテスト成功。前段のRPi実HTTP20テスト結果と区別する。
- ローカル接続切替先の直書きを外し、LABOOK_LOCAL_URLを非公開環境設定へ移した。空なら切替不可、gateway経由では常に切替不可。移行時に必要な実値をGit外で設定する。
- PHP/Python署名4ベクトルを再確認。さくら代表ルートとルート.htaccessハッシュが前後一致。
- PHP/PythonのHMAC v1とSQLite nonce再送防止を部品試験済み。v1は公開origin/prefixを署名に含めないため、固定設定の検証を別途実装する。
- 独立Slackデモはさくらで稼働し、実ログイン成功をユーザー確認済み。指定Workspace IDは非公開設定に反映済み。

## 接続問題（解決済み）

- 多数の短いSSH接続でPHP構文確認を行った途中から、作業端末→さくらのSSH/HTTPSがタイムアウト。ユーザーの通常ブラウザでも開けないと回答あり。原因は未確定。
- RPiからの公開トップ取得はHTTP 200。RPi経由のSSHも成功し、さくらは12日以上連続稼働、ルート.htaccessのSHA-256は以前の記録と一致。外部Web取得でもトップを確認した。
- サーバー全体停止の証拠はなく、送信元/経路による制限が疑われる。試験との時間的な関連はあるが、IP遮断と断定しない。システム認証ログは共用サーバーの権限で読めなかった。
- これ以降は短いSSH連打をやめ、非公開試験を1接続にまとめた。秘密鍵は転送せず、ProxyJump経由でPHP112チェックを完了。接続制限やWAF設定を解除・変更していない。
- 新しい公開試験入口は追加していない。通常経路の復旧確認を優先する。必要ならさくら管理画面/サポートで接続元制限を確認する（外部への問い合わせはまだ送っていない）。
- その後、ユーザーが接続元IPをホワイトリストへ登録し解決と連絡。通常経路からHTTPS 200・SSH接続成功・ルート.htaccess不変を再確認した。次工程を妨げる接続問題は解消済み。短いSSH接続をまとめる運用は継続する。

## Slack経路の比較結果（再試験を最初から繰り返さない）

| flow | 結果 |
| --- | --- |
| current | team指定＋form_post指定。Slack既ログインなら成功。未ログインから大学SSO後にSlack内部転送で失敗 |
| standard | form_post指定だけ省略。新規ログインは失敗 |
| select-workspace | teamも省略し、利用者がワークスペースを入力。新規ログイン成功。現在の通常デモのデフォルト |
| workspace-entry | 専用ワークスペーストップ＋相対/oauth再開先。入力・事前ログインなしで大学SSO後も成功とユーザー確認済み |

- 初期のcallbackはPOST限定で汎用エラー。GETも同じstate/Cookie検証で受け付ける修正後、ログイン成功。
- workspace-entryは公開OIDC仕様で保証された入口ではなく、Slack UIで観測した内部転送の再現。まだ比較用入口であり、通常デモのデフォルトへは昇格していない。
- この試験版のみPOSTの200応答を確定後、meta refreshで固定先へGET遷移する。POSTからの直接転送はブラウザで止まった。CSP許可範囲は拡大していない。
- 成功した手入力経路とworkspace-entryのSSO再開先はstate/nonce以外の全パラメータが一致。teamとoriginal_teamは空。秘密のclient_secretは認可URLに含まれない。
- 本番案は入力省略経路を候補にし、公開OIDCの選択方式を代替として残す。採用は非公開設定で決め、比較用flowクエリを本番へ出さない。
- 直近試験: PHP 41チェック、workspace-entryの模擬往復30チェック、通常版28チェック。実SSO成功はユーザー報告で、模擬試験を実ログイン成功と扱っていない。

## 再利用する実装

- gateway/slack-demo/app.php: デモ画面、CSRF、セッション、callback、GET/POST対応、秘密を含まない限定診断。
- gateway/slack-demo/src/Oidc.php: ログインURL各方式、固定Slack API通信、JWT署名・claims・対象team検証。
- gateway/slack-demo/src/Transactions.php: 5分・一回限りstateとブラウザ相関値をSQLiteで照合。
- gateway/slack-demo/tests/run.php: 署名・claims・nonce・入口生成のPHP試験。依存はcomposer.lockで固定したfirebase/php-jwt 7.1.1。
- gateway/signing.py、gateway/sakura/src/Security.php: HMACと再送防止。Google claim判定は旧試験部品でありSlack認証には使わない。
- scripts/configure_slack_demo.py: 非公開のSlack設定だけ更新。公開URL・公開期限を維持する。
- scripts/check_slack_demo.py --config <非公開設定> [--flow workspace-entry]: Slackを呼ばずに模擬キャンセル・不正state/Cookie・再送・CSRFを確認。
- scripts/deploy_slack_demo.py: 初回配備用。既存領域への上書きを拒否する。check-onlyは当初の設定待ち状態を想定しており、設定済み検証には上のcheckスクリプトを使う。
- scripts/prepare_sakura_preview.py: ssh、archive、snapshot等の再利用ヘルパー。snapshotはWordPress等の応答とルート.htaccessハッシュを確認する。
- scripts/check_rpi_gateway.py、check_sakura_gateway.py: 専用ディレクトリで部品試験を行う。実設定/レポートはdeploy/local限定。既存ディレクトリへの上書きを拒否する。
- tests/test_gateway_inbound.py、test_gateway_http.py、fixtures/gateway_probe.py: WSGI境界と実HTTP試験。業務アプリをimportしない。
- scripts/deploy_gateway_trial.py: 独立・7日期限・relay無効の公開試験入口を用意するスクリプト。公開前にCLI試験を要求し、既存ディレクトリを上書きしない。**まだ実行していない**。PATH_INFOがWordPressルールを通過するかを含め、Web試験は未完了。
- gateway/sakura/config.example.json: 空値の設定ひな型。実設定はwww外、鍵はbase64。trial終了後の本番設定は通過条件を満たしてから決める。

## 非公開情報の所在（値を出力しない）

- deploy/local/slack-demo.local.json: SSH接続先、サイト/非公開領域のパス、origin。
- deploy/local/slack-client.local.json: Client ID/Secret、expected_team_id、workspace_login_url。reference_enterprise_idは以前のEから始まる組織IDの控えで、許可teamには使わない。
- deploy/local/slack-demo-report.local.json、slack-demo-callback-fix.local.json: 応答・ハッシュ等の記録。
- deploy/local/sakura-preview.local.json、sakura-preview-state.local.json: 旧診断の配備先、秘密トークン、送信元IP等の記録。
- deploy/local/rpi-gateway.local.json、rpi-gateway-report.local.json: 更新されたSSH接続先・専用試験領域・Pythonとサービス名、20テストの結果。
- deploy/local/sakura-gateway.local.json、sakura-gateway-report.local.json: さくら専用試験領域と部品試験結果・不変確認。
- deploy/local/sakura-gateway-report-03.local.json: 最新112チェックと署名4ベクトル、共有ルーティング不変の結果。02は接続切れで中断、03が最新。sakura-gateway.local.jsonは03とProxyJump経路を指す。
- deploy/local/sakura-connectivity.local.json: 接続問題の読取診断。ログ参照の権限拒否により全体exit=1だが、SSH自体とuptime/ハッシュ取得は成功している。
- deploy/local/sakura-connectivity-resolved.local.json: ホワイトリスト登録後の通常経路復旧（HTTPS 200、SSH成功、共有ルーティング不変）の記録。
- deploy/local/gateway-trial.local.json: 次の公開試験配備用設定。**未配備**。実ID等は別の非公開clientファイル参照。
- .gitignoreは/deploy/local/、/secrets/、*.local.*を除外済み。既存追跡ファイルの実ホスト直書きは移行実装時の整理対象。
- サーバーのデモはpublicにindex.php/callback.phpの薄い入口のみ、app/src/vendor/config/stateはwww外。設定は所有者のみ読取可能。
- 診断7日・デモ14日の公開期限は自動延長しない。再開時に実設定を確認する。

## 再開時の順序

1. 正本と非公開設定の存在・期限を確認する。過去の認証失敗URLやstate/nonceは再使用しない。
2. さくらへの通常経路はホワイトリスト登録で復旧確認済み。SSHはバッチ化し、ProxyJumpは必要な場合のみ非公開設定で使用する。
3. 独立した認証試験入口を配備しPATH_INFO/拒否動作/Cookieを検証。新しいcallbackをSlack Appに追加登録して実SSOとログアウトを確認する。従来デモcallbackを消さない。
4. 現行ngrokと独立するendpointの利用可否を確認。別DB/別プロセス/別鍵でPHP→ngrok→RPiの結合試験、業務操作・表紙・障害/失効・WordPress不変・復旧を確認する。
5. 計画の通過条件を満たしてから短いlaBook保守時間に切替。旧ngrok OAuthを先に外さない。

今回のユーザー依頼で準備実装・並行試験を進めた。本番ルーティング切替・ngrok変更・Slack権限追加は未実施。
会話自体の強制圧縮を呼ぶツールはこの環境で見つからず、このファイルは引継ぎ用要約である。
