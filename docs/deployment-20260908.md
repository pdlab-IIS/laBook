# 実機デプロイ記録（2026-09-08）

## 反映結果

- 実機: `pdlab@100.110.113.62`、checkout: `/home/pdlab/labook`、branch: `deploy`
- 旧版: `61c0041f8515c1d23750d88dbf5274715984eddd`
- 配備版: `900eb8ba7e92d6e10ec855cb7d31fad1439c61ce`
- 取得元: `upstream/feat/frontend-borrowed-filter`。旧版からfast-forwardで反映。
- `Prod.sh`で再起動し、13:52:46 JSTに本体の起動を確認。
- 本番checkoutに未コミット変更なし。既存の追跡先`upstream/dev-miya`は変更していない。

`debugging-plan.md`のPhase 6、`backup-operations.md`、
`logging-operations.md`に従い、隔離試験、バックアップ、切替、稼働確認を実施した。
DBの修復・初期化・schema変更は実施していない。

## 検証

- 開発機の自動テスト: 73 passed、24 subtests passed。
- 実機上の本番DBコピーと一時port 5100による操作試験: 30項目成功。
  登録・編集・棚移動・貸出・返却・削除を含み、本番DBには試験データを追加していない。
- 楽天・Google・NDL: ISBN `9784862463609`の書誌情報取得成功。
- 楽天・Google: 書影の取得成功。画像の保存先も隔離環境内のみ。
- 切替後: `/healthz`、`/readyz`、一覧・管理・スキャナー画面がHTTP 200。
- JS/CSSは実機アプリとnginxの双方で配備ファイルとハッシュ一致。
- Location検索は対象41件とDB集計が一致。貸出中フィルタ、全体件数もDB集計と一致。
- DB: Books 1005、Users 2、Shelves 73、Loans 15。
  `integrity_check=ok`、`foreign_key_check=0`。
- 本体・subapp・日次バックアップtimer・nginx・ngrokがactive。
  本体・subappの今回の起動以降のログでERROR/例外・HTTP 500は0件、`NRestarts=0`。
- 開発機から`http://100.110.113.62/`へ到達し、新しい画面のHTMLを確認。
  本番では開発用オーバーレイが非表示。
- 公開ngrok URLは既存のGoogleログインへ転送される。
  認証を迂回・解除しておらず、ログイン後の公開画面とブラウザ上の目視描画は未確認。

## バックアップ

本番DBはSQLite Backup APIで実機内に保存し、メモリ上への復元と整合性検査を実施した。

```text
/home/pdlab/labook/backups/predeploy/release-900eb8b-20260908/library.db_20260908-135037-208265.db
SHA-256: 6b6b1ae02133bddc4521708d87f28a6f799f67d6d650138a0f15195d6d845a1e
```

サービス設定の控え:

```text
/home/pdlab/labook-deploy-backups/20260908-900eb8b/labook.service.before
/home/pdlab/labook-deploy-backups/20260908-900eb8b/labook-subapp.service.before
```

開発機へのDB退避は当初、安全確認で停止したが、2026-09-08に利用者から
今回および今後のコピーについて明示的な許可を得て実施した。

```text
C:\workspace\laBook\backups\predeploy-900eb8b-20260908\library.db_20260908-135037-208265.db
```

SSH/SCPで転送し、SHA-256が上記の実機バックアップと一致することを確認した。
開発機でもメモリ上への復元、`integrity_check=ok`、`foreign_key_check=0`を確認。
保存先とファイルのアクセス権は開発機の現在ユーザーとSYSTEMのみ。
DB本体はGitの除外対象であり、開発用の稼働DBも上書きしていない。
実機内バックアップは引き続き保持している。
今後の退避範囲と注意事項は`backup-operations.md`に記録した。

## 維持した本番設定

- `/etc/labook/metadata.env`（root:root、0600）と既存の本番`keys.py`を維持。
  秘密値の表示・Git登録は行っていない。
- nginx、ngrok、既存systemd unitを変更していない。
- リポジトリの`labook.service`には書誌API・画像ホストだけを許可する設定があるが、
  本番の既存Notion連携を遮断しないよう、このunitの再インストールは行っていない。
  本番の既存`EnvironmentFile`による楽天設定の読込みは維持。
- 依存パッケージに変更がないことと、実機の`pip check`成功を確認。再インストールなし。

## 復旧手順

今回DB構造を変更していないため、まずコードだけを旧版へ戻す。
実機checkoutの未コミット変更がないことを確認してから実行する。

```bash
cd /home/pdlab/labook
git status --short
git switch --detach 61c0041f8515c1d23750d88dbf5274715984eddd
bash Prod.sh
```

本番DBをバックアップで無条件に上書きしない。切替後の利用者の更新を失うため、
DBの復元が必要な場合は別途停止・退避・復元確認の手順をとる。

隔離環境`/tmp/labook-smoke-900eb8b-Kzq8aB`は一時サービスの停止を確認して削除済み。
削除したのは今回作成した検証用コード・DBコピー・取得画像のみ。
本番データと上記の復旧用バックアップは保持している。
