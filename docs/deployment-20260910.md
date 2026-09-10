# 実機リリース記録（2026-09-10）

- アプリ反映コミット: `18230c198ccc301aabba83ae5ea54ed0c066db10`
- 旧版: `900eb8ba7e92d6e10ec855cb7d31fad1439c61ce`
- 実機: `100.110.113.62`、`/home/pdlab/labook`、branch `deploy`
- 本体起動確認: 2026-09-10 17:54:14 JST
- 表記は利用者の指示に従い`SCANNER`と`Refresh Book List`へ統一。

## 検証・反映

1. 開発機の自動テスト94件・42 subtests成功。
2. 実機の隔離DBコピーでUsers移行、HTTP操作試験30項目、管理ページ表示を確認。
3. 移行前後で既存データの一致を確認し、隔離DBへのバックアップ復元も成功。
4. 本番のアプリ・subapp・バックアップtimerを停止し、DBをバックアップ。
5. コードをfast-forwardし、`scripts.migrate_user_entities --apply`で本番DBを移行。
6. 本・棚・貸出および既存Users列が移行前と一致することを確認してサービスを再起動。
7. 本体・subapp・timer・nginx・ngrokがactive、再起動後のERROR/例外0件、NRestarts=0。
8. 一覧・Book manage・人物組織管理・全貸出履歴・health/readinessがHTTP 200。
   JS/CSSはnginx経由の内容と配備ファイルのハッシュが一致。
9. 開発機からTailscale経由で`/users/manage`のHTTP 200を確認。

秘密設定、nginx、ngrokの認証設定、既存systemd unitは変更していない。
公開Google認証後の画面と実ブラウザの目視描画は今回未確認。

## 退避

実機の未コミットHTML変更は、利用者の承認に基づき以下に退避した。
案内文は最新コミット側の配置を採用し、SCANNER表記はコードへ取り込んだ。

```text
git stash: On deploy: pre-release-18230c1
/home/pdlab/labook-deploy-backups/20260910-18230c1/index-before.patch
/home/pdlab/labook-deploy-backups/20260910-18230c1/index.html.before
/home/pdlab/labook-deploy-backups/20260910-18230c1/labook.service.before
/home/pdlab/labook-deploy-backups/20260910-18230c1/labook-subapp.service.before
```

本番DBの停止中バックアップ:

```text
/home/pdlab/labook/backups/predeploy/release-18230c1-20260910/library.db_20260910-175412-973143.db
SHA-256: 6b6b1ae02133bddc4521708d87f28a6f799f67d6d650138a0f15195d6d845a1e
```

移行スクリプト自身も同じディレクトリに
`library.db_20260910-175413-161317.db`を追加保存した。

包括許可済みの開発機退避先:

```text
C:\workspace\laBook\backups\predeploy-18230c1-20260910\library.db_20260910-175412-973143.db
```

現在ユーザーとSYSTEMのみにアクセスを制限してSCP転送し、SHA-256一致を確認。
DB本体・秘密値はGitへ含めていない。

## 復旧時の注意

今回のDBには新しい制約トリガーがあるため、コードだけを旧版へ戻す手順は使用しない。
必要な場合はサービスを停止し、現在のDBも退避して移行後の利用者更新を確認する。
更新を失わない復旧計画を決めてから、旧コードと移行前DBを組み合わせて復元する。
退避した実機HTML差分は別途保持しており、無条件には再適用しない。
