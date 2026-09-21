# Sign in with Slack 単独デモ

目的は、対象のSlackでSign in with Slackが利用できるかを試すこと。
laBookへのアクセス許可や、Slackメンバー一覧の取得・メッセージ閲覧・投稿は行わない。
既存FlaskアプリやGoogle認証部品から独立している。

## 配置

- 公開: `/slack-signin-demo/index.php` と `/slack-signin-demo/callback.php` の薄い入口だけ。
- 非公開: app.php、src、vendor、config.local.json、state。
- WordPressのルート.htaccess、既存 /labook と /L のRedirectは変更しない。
- 実URL・SSH接続先・Client Secretはdeploy/localまたはサーバーのwww外に保存する。

初回配備は `scripts/deploy_slack_demo.py --config <deploy/localの設定>`。
既存ディレクトリは上書きせず停止する。Composerを公式配布元のチェックサムで確認し、
固定したfirebase/php-jwt 7.1.1とlockfileで署名検証ライブラリを管理する。
通常運用のSlack API権限・Bot tokenは不要。

## Slack Appの設定

1. [Slack App管理画面](https://api.slack.com/apps)でFrom scratchを選び、試したいワークスペースに専用アプリを作る。
2. OAuth & PermissionsのRedirect URLsへ、デモ画面が表示するcallback.phpの正確なHTTPS URLを追加・保存する。
3. Basic InformationのClient IDとClient Secretを非公開のクライアント設定へ入力する。
4. `scripts/configure_slack_demo.py --config <非公開配備設定> --credentials <非公開クライアント設定>` で反映する。
5. デモ画面を再読込し、Sign in with Slackを押す。ワークスペースのアプリ承認方針により、管理者の対応が必要な場合がある。

要求scopeは `openid profile email` だけ。通常のBot scopesと混ぜない。
`expected_team_id` は任意。空ならログイン先のWorkspace IDを表示し、一致確認が未実施であることを明示する。
指定した場合、署名検証済みのteam_idが異なるログインを拒否する。
[Slack公式フロー](https://docs.slack.dev/authentication/sign-in-with-slack/)

## 動作

- 開始はCSRF保護付きPOST。state・nonceとブラウザ用相関値は毎回乱数生成。
- 通常の認可要求はresponse_modeとteamを省略し、callbackはGET/POSTを同じstate・Cookie検証で受け付ける。短寿命の相関CookieだけSameSite=None; Secure; HttpOnly。
- 5分以内のstate・相関CookieをSQLiteトランザクションで一回だけ消費する。
- Slackの固定したトークンURL・公開鍵URLにのみHTTPS接続。任意URLやリダイレクトは受け付けない。
- RS256署名、issuer、audience/azp、有効期限、発行時刻、nonce、subject/user_id、任意の対象team、at_hashがあればその対応を検証。
- アプリはトークン・Client Secret・認可コードを表示・保存しない。サーバー側セッションに最小の検証結果だけを保存。GETで戻る場合はホスティング側のアクセスログにクエリが含まれ得るため、ログの取得・共有時に注意する。
- 戻り処理の失敗はCookie不足・state不一致（期限切れ／再送を含む）などを区別して表示。非公開のstate/failures.jsonlには時刻・処理段階・定義済み理由・GET/POSTの区別だけを記録し、約64KiBで切り詰める。秘密値や生の例外メッセージは記録しない。
- 結果の画面表示は15分。デモセッションのCookie有効期間は30分。結果の消去操作はこのデモの状態だけを変更する。
- 初回配備から14日で入口を期限切れにする。設定更新で自動延長しない。
- これはログイン時点の確認のみ。無効化済みユーザーの継続チェックやゲスト役割判定は本番組込み時の別工程。

## 確認結果（2026-09-17）

- さくら上のPHPで24チェック成功。実際に生成したRSA鍵で、正常署名、改ざん、誤issuer/audience/nonce/team、期限切れ、別アルゴリズム、stateの再送・別ブラウザ・期限切れなどを検証。
- 依存ライブラリのComposer auditが成功。
- HTTPSの設定待ち画面、no-store/CSP、不正callbackの拒否を確認。ブラウザでも表示を確認。
- 配備前後のルート.htaccessハッシュと、既存サイト・/labook・/Lの応答が一致。
- Slack Appの設定後、実アカウントで許可して戻った際に汎用エラーが発生したとの報告あり。修正前のGET callbackが同じ400エラーになることを模擬試験で再現し、GET対応を追加。実際の失敗時のHTTPメソッドは未確認のため、原因の確定と実ログイン成功の確認には再試験が必要。
- 修正後、実サーバー上で認可キャンセルを模擬したGET/POSTの往復、不正Cookie・不正state・Cookie欠落・再送・不正CSRFの拒否など24チェックが成功。`scripts/check_slack_demo.py --config <非公開配備設定>` で再試験可能。Slackへコードを送らず、ログイン成功を偽装しない。実ブラウザのSameSite動作はこの試験の対象外。

- ユーザーから修正後の実Slackログイン成功の報告を受領。確認したWorkspace IDを非公開設定に反映し、実際のログイン開始URLのteam指定とサーバーの一致検証設定を確認済み。対象固定後の画面遷移は次のユーザー試験で確認する。

対象Workspace IDを設定すると、返された署名済みteam_idとの一致を必須にする。通常のログイン開始URLにはteamを付けない。
さくらのWordPress設定やngrok OAuthを変更する必要はない。

## 新規Slackログインを挟む場合（調査中）

ログイン済みのブラウザでは成功する一方、新規Slackログイン後にSlack側のエラー画面へ進むとの報告あり。
未ログイン時に組織のSSO入口へ進むことは確認したが、SSO完了後のエラー原因は未確定。
非公開設定の `workspace_login_url` にSlackのワークスペースまたは組織のHTTPSトップURLを設定すると、
先に別タブでSlackへログインしてからデモ認証を開始する回避手順を表示する。
URLにはクエリや認証状態を付けない。このリンクを開く段階ではデモの5分の認証試行を開始しない。
実ブラウザでの回避手順の完了はユーザー試験で確認する。team_id・state・nonce・署名の検証は変更しない。

ユーザー試験で、先にSlackへログインする回避手順の成功を確認済み。
手動手順をなくすための比較試験として `index.php?flow=standard` を追加。
この入口だけ認可要求から `response_mode=form_post` を省略し、[Slack公式のcodeフロー例](https://docs.slack.dev/authentication/sign-in-with-slack/#request-with-scopes)に合わせる。
差分はresponse_modeの有無だけで、team指定・scope・state・nonce・callback先と全検証は維持する。
通常の入口は従来のまま。これは原因特定の比較試験であり、SSOの問題を解消したとの確認はまだない。
各試験はSlack未ログインの独立したブラウザセッションから1回ずつ開始する。

ユーザー試験で `flow=standard` も失敗との報告あり。
次の比較として `index.php?flow=select-workspace` を追加し、standard要求からteam指定だけを省略する。
利用者がSlack側でワークスペースを選択する。非公開設定のexpected_team_idは変更せず、
認証結果の対象ワークスペース制限は引き続き必須。こちらも実ログインの成否はユーザー試験待ち。

### 最終的に採用した経路

ユーザー試験で、ワークスペースの事前指定を外した経路で新規Slackログインから成功したとの報告を受領。
通常の `index.php` と認可URL生成のデフォルトをselect-workspaceに変更し、通常画面から事前ログイン案内を外した。
Slack側でワークスペースを選択・入力し、認証後にexpected_team_idと一致することを検証する。
比較用の `?flow=current`（元の要求）と `?flow=standard`（team指定あり）は調査用に残す。
比較結果はteam指定を伴うSSO経路の問題を示唆するが、Slack内部の根本原因は未確定。

### ワークスペース入力を省く比較版

`index.php?flow=workspace-entry` は、非公開のworkspace_login_urlを入口に、
手入力経路で観測した相対継続URL `/oauth?...` を `redir` として渡す。
この組合せは公開OIDC仕様で保証された入口ではなく、デモ限定の比較試験。
対象URLはワークスペースのHTTPSトップに限定し、expected_team_idが空なら拒否する。
scopeはログイン用だけ。state・nonceは新規生成し、既存のtoken交換・署名・対象ID検証を共通で使う。
通常入口は変更しない。実ネットワーク設定は引き続き非公開ファイルのみ。

開始POSTからの転送がブラウザで止まったため、試験版だけ同一サイトの200応答を確定し、
即時のmeta refreshで検証済みURLへGET遷移する。CSPの許可範囲は広げていない。
調整後は入力なしで組織のSSO画面に到達し、SSO後の再開先についてstate・nonce以外の
全パラメータが手入力の成功経路と一致することをブラウザで確認した。
大学アカウントの認証後にデモへ戻る最終確認はユーザー試験待ち。
PHPの41チェック、試験版の模擬callback 30チェック、通常版28チェックが成功。

ユーザーからworkspace-entryでのログイン成功の報告を受領。入力省略の試験は成功したが、
この内部転送経路は引き続き比較用入口で、通常入口はselect-workspaceのまま。

### Slack Connect外部参加者への拡張（未実装）

ユーザー指示により、この拡張は保留。以下は参考案であり今回の移行要件に含めない。

Slack Connectの外部参加者は自分のワークスペースに所属するため、現在の固定team_id照合だけでは許可できない。
候補は、外部参加者が自分のワークスペースでOIDC認証した後、ホスト側のBot tokenで
許可した共有チャンネルの参加者を取得し、検証済みのSlack IDと照合する方式。
IDの対応は実アカウントで確認し、名前やメールだけで同一人物とみなさない。
署名・issuer・audience・nonce・state検証と、利用許可の判定を分ける必要がある。
外部ワークスペース全体を許可せず、現在のチャンネル参加とユーザー有効状態を確認する。
ページング完了、共有切断・アーカイブ、API失敗時の拒否、短期キャッシュと再確認も設計する。
必要な追加権限の候補はchannels:readまたはgroups:read、ユーザー状態確認のusers:read。
Botを対象共有チャンネルに参加させ、外部側でSlack Appのログイン利用が許可されることも試験する。
大学ワークスペース固定の入口を外部参加者全員には使えないため、外部向けのログイン経路も必要。
現行の許可範囲とSlack App権限は変更していない。

資料: [Slack Connect](https://docs.slack.dev/apis/slack-connect/)、
[conversations.members](https://docs.slack.dev/reference/methods/conversations.members/)、
[users.info](https://docs.slack.dev/reference/methods/users.info/)。
