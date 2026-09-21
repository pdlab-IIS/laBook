# Slack / Notionを利用したlaBook認証の再検討

2026-09-17更新: 本書は過去の方式比較として保存する。ユーザーはSlack単独を採用し、
Notion認証とSlack Connect対応は保留。実装・移行の正本は[Slack移行手順](sakura-auth-proxy-plan.md)。
以下のBot所属確認・追加権限などを現在の必須要件と解釈しない。

調査日: 2026-09-17。Google WorkspaceでのOAuth利用が不可、OAuth方式全般は禁止ではない、というユーザー確認に基づく。
本書は方式検討。現行サービス・試験入口・外部アプリ設定を変更していない。実ワークスペースID、ユーザーID、鍵、接続先は記載しない。

## 結論

第一候補はさくら側でのSign in with Slack。Google固有の認証処理をSlackへ置き換え、既存のPHPセッション・認証中継・RPi署名検証の設計を引き継ぐ。

Notionゲストも条件付きで資格確認に利用できるが、ゲスト一覧の自動同期やログイン本人確認を通常APIだけで完結させる案は採用しない。
Slackに入っていない人も対象にする場合は、「管理者が登録したNotion利用者＋メールのワンタイムコード」を第二経路として検討する。

## 比較

| 案 | 本人確認 | 利用資格 | 評価 |
| --- | --- | --- | --- |
| Sign in with Slack | Slack OIDC | 指定ワークスペースの有効なメンバー | 第一候補 |
| Slack所属＋メールコード | 登録メールへのコード | Slack APIで有効なメンバーを照合 | Slack OIDCを使えないときの代替。メール送信基盤が必要 |
| Notion既知ユーザー＋メールコード | API取得メールへのコード | 管理者登録済みIDが指定ワークスペースに属することを再確認 | ゲスト向け第二経路の候補。役割・ページ権限は別途扱う |
| Notionゲスト全員の自動ログイン | 通常APIではログイン機構にならない | ゲスト全員の一覧を取得できない | 現状の第一候補にしない |

利用資格を取得できても、ブラウザの利用者がその人物だと確認できるわけではない。ID・メールの自己申告だけではセッションを発行しない。

## Slackの実装案

Sign in with SlackはOAuth 2.0上のOpenID Connect。IDトークンにワークスペースと利用者の識別子が含まれる。
ログイン用scopeと通常のWeb API用scopeは別の認可フローで取得する必要がある。[公式Sign in with Slack](https://docs.slack.dev/authentication/sign-in-with-slack/)

1. 対象ワークスペースにlaBook専用Slack Appを準備。アプリ導入承認・契約のアプリ枠・管理者方針を確認する。
2. 保守されているOIDCライブラリで署名・iss・aud・exp・state・nonceを検証する。
3. 検証済みの `https://slack.com/team_id` が非公開設定の対象IDと一致することを必須にする。認可要求のteam指定だけでは制限しない。
4. 安定した主体キーはSlackのworkspace IDとuser ID。メールアドレスや表示名を識別キーにしない。
5. 対象ワークスペースに導入したアプリの読取トークンで所属・有効状態を確認。通常メンバーを初期対象とし、無効化済み・bot・アプリユーザー・招待未完了を除く。Slackゲストの扱いは別途明示する。
6. 成功後はさくら独自のセッションを発行し、以降の中継は従来計画と同じ。RPiにはGoogle/Slackトークンを渡さない。

所属確認には `users.info` / `users.list` とユーザー情報を使う。Slack Connectの外部利用者もAPIから見える場合があり、取得できたことや `is_stranger=false` だけで所属を認定しない。通常ワークスペースは対象team IDとの一致を確認し、Enterprise構成では対象ワークスペースへの所属情報を別途検証する。[users.info](https://docs.slack.dev/reference/methods/users.info/)、[User object](https://docs.slack.dev/reference/objects/user-object/)

所属判定用の最小権限は `users:read` を基本とする。メール照合方式を選ぶ場合に限り `users:read.email` も必要。既存のIncoming Webhookは投稿用なので、この所属確認用トークンの代用にはならない。[users.list](https://docs.slack.dev/reference/methods/users.list/)

SlackのFreeプランにはカスタムアプリを含め10個の導入枠がある。Google側の制約がなくなるだけで、Slack側の導入承認・残り枠の確認は必要。[Freeプランの制限](https://slack.com/help/articles/115002422943-Usage-limits-for-free-workspaces)

### セッションと失効

- 各要求でローカルセッションを確認し、所属情報は短いTTL（初期案5分）で再確認する。無効化を検出したらセッションを失効させる。
- 所属APIの障害や429で、期限切れの所属情報を無制限に信頼しない。再確認できなければ保護対象の要求を一時拒否する。
- ログインscopeとBotの読取権限を混ぜず、ログイン利用者にワークスペース全体の読取許可を毎回求めない。
- SlackのOIDCメタデータにはform_post応答が記載されている。Google用に予定していたSameSite=Laxだけでは、クロスサイトPOSTのcallbackに相関Cookieが付かない場合がある。使用ライブラリの応答モードを確認し、必要なら短寿命の専用相関CookieだけSameSite=None; Secure; HttpOnlyとする。本体セッションはLaxを維持し、stateとブラウザの関連付け・一回限りの消費を検証する。[OIDC仕様とフロー](https://docs.slack.dev/authentication/sign-in-with-slack/)

## Notionの実装可能範囲

公式仕様では、一覧APIの返却対象にゲストは含まれない。一方、IDが分かっていれば、連携先ワークスペースに所属するゲストを個別取得できる。[List all users](https://developers.notion.com/reference/get-users)

個別取得はメンバー・ゲスト・botが対象で、連携先ワークスペースへの所属が条件となる。[Retrieve a user](https://developers.notion.com/reference/get-user)

ただしUserのtypeはperson/botであり、通常のUser情報にゲスト役割や特定ページの共有権限は含まれない。メールの取得にはユーザー情報のcapabilityも必要。[User object](https://developers.notion.com/reference/user)

したがって次のような限定した方式を検討する。

1. 管理者がNotionゲストであることを確認したユーザーIDを、laBook用の非公開名簿へ登録する。利用者が自分で許可名簿を書き換えられる場所には置かない。
2. サーバー専用のNotion連携でそのIDを取得し、personであることとAPIが返すメールを確認する。
3. そのメールへ短寿命・一回限りのコードを送り、ブラウザでの入力を確認する。コードのハッシュ保存、試行回数・送信頻度制限、ブラウザとの関連付けを行う。メール送信は実装後の機能であり、今回送信はしていない。
4. セッション作成前と短いTTLで資格を再確認する。Notionから取得不可・権限不足・退会時の挙動を実アカウントで試験する。

この方式が保証するのは「承認済みのNotion利用者が現在も接続先ワークスペースに属し、その登録メールを操作できること」。
「今もゲスト役割である」「特定の研究室ページを今も閲覧できる」を同義にしない。後者が必須なら共有解除や役割変更を扱う資格情報の別管理が必要となる。

Notion OAuthは連携へのコンテンツアクセス許可を中心とする。許可画面で選べるページにもFull access条件があり、単純なゲスト向けログインボタンへの置換としては適さない。[Notion Authorization](https://developers.notion.com/guides/get-started/authorization)

Enterprise向けAdmin APIは組織オーナー・Enterprise契約が前提なので、追加ライセンスなしで使える代替と想定しない。[Notion Admin API](https://www.notion.com/help/admin-apis-for-enterprise-organizations)

## 「SlackメンバーまたはNotionゲスト」を採用する場合

- Slackログインを標準経路とし、Slack外の承認済み利用者だけNotion＋メールコードを使う。
- 各経路で本人確認と資格確認を完結させる。二つのサービスのメールが同じというだけでアカウントや資格を自動結合しない。
- 認証元と元サービスのIDをセッションに記録し、その根拠の失効を追跡できるようにする。
- Notion側を追加する必要がなければSlack一本に絞り、名簿登録・メール配信・二系統の失効管理を省く。

## 現行作業への反映

- Googleクライアントの準備とGoogleドメイン固有の実装を保留する。
- PHP中継、/labook配下対応、CSRF、サーバー間HMAC、nonce保存、秘密設定のGit除外は継続利用する。
- Workspace判定関数をSlack用認証プロバイダーへ置き換える。テスト済みのGoogle claim判定はSlackの認証として流用しない。
- WordPressと既存ngrok OAuthは維持し、独立した試験入口でSlackログインを先行試験する。
- 試験トークンは自動延長されない。9月12日作成の試験環境を再利用するときは有効期限を確認する。
- 次の実環境確認はSlack Appを作成・導入できるか、対象ワークスペース、通常メンバーだけで対象者を網羅するか。
  Notionを併用する場合のみ既知IDの取得・削除後の失効・メール到達を検証する。

今回の変更は本書と計画への参照追加のみ。Slack/Notionへのアプリ導入、メンバー取得、通知送信、サーバー変更、コミットは行わない。
