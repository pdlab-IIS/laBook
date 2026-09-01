# Database repair runbook

## Status

2026-09-01時点で、修復ツールはテストと実データsnapshotコピーで検証済みだが、本番DBには適用していない。

実機の本番DBを読み取り専用で監査し、メモリ上のコピーへ修復候補を適用した結果は次のとおり。

| 項目 | 適用前 | dry-run適用後 |
|---|---:|---:|
| Books | 995 | 995 |
| Loans | 23 | 15 |
| `owner_id=0` | 375 | 0 |
| 欠落Userを参照するBooks | 94 | 0 |
| 欠落Bookを参照するLoans | 8 | 0 |
| `foreign_key_check` | 477 | 0 |
| `BookOwnerRepairArchive` | 0 | 469 |
| `LoansOrphanArchive` | 0 | 8 |

同じsnapshotを`/tmp`へコピーして実適用した後も`foreign_key_check=0`になった。適用時に生成された事前backupから別名DBを復元し、元snapshotとSHA-256が一致することも確認した。

## Repair policy requiring approval

本番適用前に、次の方針をデータ管理者が承認する必要がある。

1. `Books.owner_id=0`の375件は、従来の「所有者なし」を表すsentinelとみなし、元のISBNと値を退避して`NULL`へ変更する。
2. 現在の`Users`に存在しないowner IDを持つ94件も、元のISBN、owner ID、理由を退避して`NULL`へ変更する。
3. 対応する`Books`が存在しないLoan 8件は、Loanの全列を退避用テーブルへ保存した後、稼働テーブル`Loans`から削除する。

94件のowner IDが復元すべき過去ユーザーを表す場合、または孤立Loanに対応する書籍を復元できる場合は、本番適用前に再割当・参照復元へ方針を変更する。

## Safety properties

[`scripts/repair_database.py`](../scripts/repair_database.py)には次の安全策がある。

- 引数なしの方針は監査のみで、対象DBを読み取り専用URIで開く
- 修復方針付きdry-runも、操作するのはメモリ上のDBコピーだけ
- `--apply`には両方の修復方針と`--confirm-services-stopped`が必要
- applyの前にSQLite online backupを自動作成し、integrity checkを行う
- 退避、変更、`integrity_check`、`foreign_key_check`を同じtransactionで行う
- 未対応の外部キー違反が1件でも残る場合はtransaction全体をrollbackする
- 出力は集計値だけで、書名、利用者名、tokenを含めない

## Commands

以下はリポジトリroot、Python 3.11のvirtual environment内で実行する。

読み取り専用監査:

```sh
python -m scripts.repair_database /absolute/path/to/library.db
```

修復候補をメモリ上だけで試す:

```sh
python -m scripts.repair_database /absolute/path/to/library.db \
  --owner-policy archive-null \
  --orphan-loan-policy archive-delete
```

本番適用は、方針承認、直前のoff-host backup、メンテナンス時間確保の後に行う。先に`labook`と`labook-subapp`を停止し、DBへ書き込むプロセスがないことを確認する。

```sh
python -m scripts.repair_database /home/pdlab/labook/library.db \
  --owner-policy archive-null \
  --orphan-loan-policy archive-delete \
  --apply \
  --confirm-services-stopped \
  --backup-dir /home/pdlab/labook/backups/migration
```

成功時のJSON出力とbackup pathを作業記録へ保存する。サービス再開前に、少なくとも次を確認する。

- `after.foreign_key_violations`が0
- `book_owners_archived_and_nullified`が事前承認した件数と一致
- `orphan_loans_archived_and_deleted`が事前承認した件数と一致
- backup fileが存在し、mode 0600で`integrity_check=ok`

## Rollback

適用処理内で検証に失敗した場合、DB変更は自動rollbackされる。適用後にアプリケーション検証で問題が見つかった場合は、サービスを停止したまま次の順に戻す。

1. 現在の失敗DBを削除せず、別名で退避する。
2. JSON出力の`backup`が指す適用直前backupを、別名DBとして復元・検証する。
3. `integrity_check=ok`、期待する477件の適用前違反、ファイル所有者とmode 0600を確認する。
4. 検証済み復元ファイルを`library.db`へ切り替える。
5. サービスを起動し、health checkと主要操作を確認する。

パスを取り違えるとデータを失うため、復元時のrename/copyは作業者が絶対パスとhashを確認してから実行する。
