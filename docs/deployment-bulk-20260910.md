# 一括編集リリース（2026-09-10 18:20 JST）

- 機能コミット: `e7a00e3`、実機検証・配備対象: `4d97d44b801484828064a6748a30df590c5d9785`
- 旧本番: `0bf20488a27dfe05e282d7b135b02c41c763d552`
- 実機: `100.110.113.62`、`/home/pdlab/labook`、branch `deploy`
- 起動確認: 2026-09-10 18:20:23 JST
- DB構造・秘密設定・systemd/nginx/ngrok設定の変更なし。

## 変更内容

一括編集モード中だけ一覧のチェックボックスを表示。
全選択は表示中のページが対象で、ページ移動・検索・一覧更新で選択を解除する。
背景をぼかさない非モーダルパネルでLocationとOwnerを指定・解除できる。
実行前に対象冊数と変更内容を確認し、成功時またはパネルを閉じた時にモードを終了する。
一括更新はトランザクションで実行し、失敗時は新規Locationを含めて取り消す。
画面上のユーザーID表記を非表示にし、処理用のID値は保持する。

## 検証

- 開発機: 102 tests、56 subtests成功。JavaScript構文確認成功。
- 実機の隔離環境: 一括編集テスト8件、既存HTTP操作試験30項目成功。
- 一覧・Book manage・Users管理・health/readinessのHTTP 200を確認。
- nginx配信のJS/CSSと配備ファイルのハッシュ一致、Tailscaleから新版ページを確認。
- 本体・subapp・backup timer・nginx・ngrokがactive。本体/subappの起動後ERROR・例外0件、NRestarts=0。
- 本番DBへの試験用更新は実施していない。実ブラウザ目視・公開Google認証後の確認は未実施。

## バックアップ

実機: `/home/pdlab/labook/backups/predeploy/bulk-4d97d44-20260910/library.db_20260910-182021-609661.db`

開発機: `C:\workspace\laBook\backups\bulk-4d97d44-20260910\library.db_20260910-182021-609661.db`

SHA-256: `07c2a7ce66b25a5ed3a60257da031b36394802a521d87d6d2c7ad39154aee7b8`

SQLite Backup APIで作成。開発機は現在ユーザーとSYSTEMのみアクセス可能。
SCP転送後のハッシュ一致、メモリDBへの復元、整合性・外部キー違反なしを確認した。
DB・秘密値はGitに含めていない。

今回の変更に限るコード復旧先は`0bf2048`。DB構造は同じなのでコードだけを戻せる。
ただし実際に行われた一括編集はコードの復旧では元に戻らない。
本番DBを過去のバックアップで無条件に上書きしないこと。

## SP表示修正の追加リリース（18:29 JST）

- 機能コミット: `0d91589`、実機配備: `7ec69a31c6c52ca5ea8ef367bc09794ab037210d`。
- SPではBulk Editを非表示・無効化し、PCからSPへの切替時にモードを終了。
  列幅指定を列の意味に基づくクラスへ変更し、SPのCover・Status幅を維持、Titleを可変幅にした。
- メニュー名は`Bulk Edit`、メニュー内の件数カウンターを削除。
- 開発機103 tests・56 subtests、実機隔離テスト9件・HTTP操作試験30項目が成功。
- 18:29:59 JSTに本体起動。主要ページ・配信ファイル・Tailscale経由の新版HTMLを確認。
  本体/subappの起動後ERROR・例外0件、NRestarts=0。実ブラウザ目視確認は未実施。
- DB構造・秘密値・公開経路に変更なし。復旧先は直前の`0a9cc81`。
- バックアップ: `/home/pdlab/labook/backups/predeploy/sp-7ec69a3-20260910/library.db_20260910-182953-350684.db`
- 開発機退避先: `C:\workspace\laBook\backups\sp-7ec69a3-20260910\library.db_20260910-182953-350684.db`
- ACLを制限して転送。SHA-256は上記18:20リリース時のバックアップと同一で、転送後の一致を確認。
