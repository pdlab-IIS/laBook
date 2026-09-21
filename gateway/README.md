# 認証中継の並行準備

このディレクトリの部品は、現行のapp.pyから読み込まれていない。
本番の認証方式・URL・DB・ngrokポリシーを変更せずに試験するための準備段階であり、
完成した認証リバースプロキシとして配備してはいけない。
現在の方針は[Slack移行手順](../docs/sakura-auth-proxy-plan.md)。
Slack単独デモは[slack-demo](slack-demo/README.md)にあり、本番中継とは独立している。

## 実装済みの範囲

- Python/PHP共通の要求署名と、専用SQLiteを使った複数プロセス間の再送防止。
- RPi用の任意起動WSGI入口。固定Host/公開origin/prefix、本文上限、全ルートの署名検証、認証ヘッダーの除去、private/no-storeを適用する。
- PHPのセッション許可判定・保存・ログイン/callback/logout入口。対象team必須、無操作30分/絶対60分、設定世代/主体ごとの失効、更新操作のOrigin/CSRF検証。新入口の実SSOは未試験。
- 固定HTTPS上流への中継・署名ヘッダー生成・Location写像。単一JPEG表紙アップロードの再構成、要求/応答上限を実装。実ngrok中継は未試験。
- 各画面のprefix付きURLとCSRF通信を共通化。従来のルート環境も継続対応する。
- **検証済み**Google IDトークンに適用する旧Workspaceドメイン判定。Slack移行では使用しない。
- Slack単独デモのJWT署名・claims・対象Workspace ID・state/Cookie検証。入力省略経路の実ログイン成功をユーザー確認済み。
- 秘密トークンで保護した期限付きのWeb PHP診断入口。laBookのデータへは接続しない。
- 新設領域だけへ配備する診断用スクリプトと、既存ルート・ルート.htaccessの不変確認。

## 並行試験の入口

既存のRedirectはパスの先頭一致なので、/labook-previewのようなパスは使用しない。
独立した /auth-labook-preview/index.php を使用する。実ファイルへのアクセスなので、
WordPressの存在しないパスを捕捉するrewriteに依存せず、ルート.htaccessを変更しない。
試験中はpretty URLを使わず、actionクエリで処理を選ぶ。

公開側は薄いindex.phpだけ。本体・設定・ログはwww外へ置く。
診断トークンはヘッダーでのみ受け取り、URLやHTMLへ出さない。トークンは7日で期限切れになり、
以降は404を返す。再開時は非公開設定の更新が必要。自動的に期限を延長しない。
この入口は匿名アクセスと誤トークンで404になり、既存サービスへの中継機能を持たない。

## 要求署名の試験用仕様

HMAC-SHA256の入力はUTF-8で以下を改行区切りにし、最後には改行を付けない。

1. labook-gateway-v1
2. key_id
3. HTTP method
4. 正規化・検証済み上流パスと生クエリ
5. 実際に送るContent-Type
6. 実際に送る本文のSHA-256（小文字hex）
7. UNIX秒
8. 128-bit nonce（小文字hex）
9. 検証済み主体ID

共有鍵は32バイト以上。署名も小文字hex。時刻許容差は前後60秒。
nonceは鍵IDとの複合一意制約で一度だけ消費し、最後に受理可能な時刻まで保持する。
失敗した署名ではnonceを消費しない。nonce保存先の障害では拒否する。

RPi入口は固定した公開origin/prefixとHostの検証、パス検証、本文サイズ制限、
ヘッダーの置換を提供する。PHP中継、Slack認証との接続、HTTPセッション管理とCSRFの適用も実装したが、全体の実通信試験は未完了。
署名部品単体で本番ゲートウェイは成立しない。本番と試験で同じ鍵やnonce DBを使わない。

## RPi署名入口（本番未配備）

`gateway.wsgi:application` は `LABOOK_GATEWAY_CONFIG` の非公開JSONを必須とする。
形式は [rpi-config.example.json](rpi-config.example.json)。共有鍵は32バイト以上をbase64化し、
最大2つの鍵IDを登録できる。公開origin/prefixは環境固定値で、Forwardedヘッダーから取得しない。
nonce DBの親は事前に作成した所有者専用ディレクトリとし、鍵ファイルも所有者だけ読めるようにする。
Gunicornから届くRAW_URI/REQUEST_URIとWSGIの復号済みパスの一致を検証する。

この入口で実際のappを起動する際には、業務DBも試験専用に分離する必要がある。
今回のHTTP試験はlaBookをimportしない専用Flaskプローブを使い、業務DBを一切開いていない。
既存 `app:app` と起動スクリプトは変更しておらず、旧入口への迂回防止は本番切替時の別工程。

## 実行

Pythonの部品試験は `python -m pytest tests/test_gateway_signing.py tests/test_gateway_inbound.py tests/test_gateway_http.py -q`。
WindowsではGunicornのHTTP試験4件をスキップする。Linuxでは実際に2ワーカーをループバック上で起動し終了する。
PHP試験はさくらの非公開領域で実行し、Pythonで作ったJSON・バイナリ・multipart・空本文の
期待署名と照合する。fixtureには架空のドメインと試験専用鍵のみを使用する。

診断スクリプトは `scripts/prepare_sakura_preview.py --config <ignored-local-config>`。
初回だけ `--deploy` を指定する。既存ディレクトリがあれば上書きせず停止する。
再確認時は `--deploy` を付けない。実設定・レポートはdeploy/localに限定する。

2026-09-21: `scripts/check_rpi_gateway.py` でRPi実HTTP込み20テスト成功、既存サービスactiveを前後確認。
`scripts/check_sakura_gateway.py` でPHPセッション54チェック、PHP/Python署名4ベクトル成功。
後者はさくらの非公開領域だけで実行し、WordPress代表ルートとルート.htaccessハッシュが前後一致。
両スクリプトは `--config` / `--report` にdeploy/local内のファイルを指定し、未作成の専用test_rootへ試験だけ配置する。
試験設定にはRPi側でssh_target/test_root/python/service、さくら側でssh_target/test_root/site_root/originが必要。

## 最新の追加試験と残作業

2026-09-21後半: PHPのセッション54・中継境界50・保存8の計112チェックが非公開領域で成功。
Python全体120テスト、JSのURL/CSRF/multipart/再送抑止も成功。Windowsでは実HTTP4件はスキップ。
`LABOOK_LOCAL_URL`は従来のローカル接続切替先を非公開環境へ移したもの。gatewayではその切替を無効にする。

途中から作業端末と利用者の通常ブラウザでさくらへの接続がタイムアウトした。
RPiからHTTP 200とSSH接続成功、ルート.htaccess不変を確認。送信元/経路の問題が疑われるが原因未確定。
その後ユーザーが接続元IPをホワイトリストへ登録し、通常経路のHTTPS 200・SSH接続成功と共有ルーティング不変を再確認した。接続問題は解決済み。
詳しくは[引継ぎ要約](../docs/slack-migration-handoff.md)。短いSSH接続の連打を避け、1接続へまとめる。

次の公開試験は `scripts/deploy_gateway_trial.py --config <deploy/local内の設定> --report <同レポート> --deploy`。
このスクリプト自体と公開Web試験はまだ未実行。新callback登録も未実施。
7日で失効し、中継は無効の独立入口を作る。試験用prefixは `/auth-labook-trial/index.php`。
PATH_INFOとWordPressのrewriteが干渉する場合はその時点で止め、共有ルールを無断変更しない。

## 次の工程

1. 復旧済みの通常経路で、公開試験入口の配備条件・期限を確認する。
2. 新しい試験入口で実Slackログイン・対象外拒否・CSRFを確認。本番RPiへの中継はまだ行わない。
3. 接続確認済みRPiに、別ディレクトリ・別port・試験専用DB・別鍵でlaBook検証用プロセスを用意（現在はDBを使わないプローブ試験まで完了）。
4. 契約で可能な独立したngrok endpointを確認してから、既存endpointを変更せず接続試験。
   追加endpointが使えない場合は代替の並行試験方法を決めるまで既存OAuthを維持する。
5. 全体試験後に初めて本番ルーティングの変更候補と短い切替手順をレビューする。
