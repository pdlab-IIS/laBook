# laBook 調査結果・デバッグ計画

- 調査日: 2026-09-01 (JST)
- 対象リポジトリ: `laBook`
- 本番相当ホスト: Raspberry Pi 4 (`pdlab@labook`)
- 調査方針: 本番checkout・本番DB・本番serviceは変更せず、書き込み検証は`/tmp`のDBコピーと別portだけで実施

## 1. 要約

laBookは現在稼働しており、直ちに停止につながるCPU、メモリ、温度、ディスクの問題は確認されなかった。HTTPもGunicorn直結、nginx経由のどちらも正常応答している。

一方で、最優先で対処すべき問題はSQLiteの論理的不整合である。DBファイル自体は破損していないが、外部キー違反が477件ある。現状のアプリはSQLiteの外部キー制約を有効にしていないため、不整合を残したまま稼働できている。先にデータを分類・退避・修復してから制約を有効化する必要がある。

次の優先課題は、開発環境の再現性、外部API障害への耐性、デプロイスクリプトとsystemdの競合、バックアップとログの無制限な増加、秘密値の配布方法である。

秘密値については、現在の`keys.py`を開発ホスト間でコピーする運用をやめ、次を暫定推奨とする。

1. SOPS + ageで暗号化した設定をGit上の正本にする
2. 開発ホストごとに別のage秘密鍵を生成し、秘密鍵自体は受け渡さない
3. 開発用と本番用の秘密値・復号可能な端末を分離する
4. 本番RPiでは、最終的にsystemd credentialsを使って実行プロセスへ渡す

研究室ですでに監査・権限管理付きの共有パスワード管理サービスを標準利用している場合は、そのサービスをSOPS + ageより優先してよい。

### 1.1 着手状況

2026-09-01にPhase 0からPhase 6へ着手し、commit `16e6515`を本番へ反映した。未完了事項は各行に明記する。

| 項目 | 状態 |
|---|---|
| SQLite online backup | 実施済み |
| backup path | `/home/pdlab/labook/backups/manual/library-20260901-154418-733033.db` |
| backup SHA-256 | `91791d5d2b519413a9fd0900335b3626a2c2182d6efcfd7f3be1bc96aa3bfde4` |
| backup検証 | `integrity_check=ok`, 163,840 bytes, mode 0600 |
| 外部キー違反 | backupにも477件。現状を保存する復元用snapshotであり、修復済みbackupではない |
| Python依存採取 | 実施済み。`requirements.txt`へRPiのversionを固定 |
| 設定loader | 環境変数優先、`keys.py` fallbackの移行用`config.py`を追加 |
| 秘密値template | 値を含まない`.env.example`を追加 |
| 自動テスト | 設定、外部API、Notion、Slack、Books、Loans、online backup、保持処理、logging、管理route非公開、DOM安全性、DB修復、health/readiness、smoke target安全策の54件を追加 |
| 隔離検証 | RPiの`/tmp`上で54 testsが成功。Bash、Gunicorn、systemd unit/timer、journald drop-inも検証済み |
| 外部API耐性 | connect/read timeout、書誌providerの部分障害継続、Notionの502/504変換を実装 |
| 出版日 | `YYYY`、`YYYY-MM`、`YYYY-MM-DD`の正規化を実装 |
| 棚作成 | localhostへの自己HTTPを廃止し、同一SQLite transaction内の処理へ変更 |
| owner_id封じ込め | 既存469件を退避してNULL化済み。新規入力でも値0と空文字をNULLへ正規化 |
| app/scheduled backup | `shutil.copy`を共通のSQLite online backup＋integrity checkへ置換 |
| DB修復dry-run | 本番DBのread-only→memory copyで469 ownerと8 Loanを退避・修復し、477→0を確認 |
| DB修復apply/rollback試験 | 検証済みsnapshotの`/tmp`コピーで成功。事前backupからの復元hashも元snapshotと一致 |
| 本番DB修復 | 2026-09-01実施。owner 469件と孤立Loan 8件を退避し、`foreign_key_check`を477→0、Loansを23→15、未返却Loanを2→0へ変更 |
| 過去backup復元調査 | 359/359個を読取成功。孤立ISBN 6件（active 2件を含む）の過去Bookは0件 |
| 貸出整合性 | foreign keys、5秒busy timeout、貸出・返却transaction、未返却Loanの重複防止を実装 |
| ヘルス診断 | `/healthz`と`/readyz`を本番配備し、どちらも200を確認 |
| 再起動手順 | 安全化した`Prod.sh`を本番配備。systemd状態とhealth/readinessによる切替確認に成功 |
| 運用設定 | app/subapp/backupのsystemd unitを本番配備。nginxは現行設定を維持 |
| 日次backup | systemd oneshot＋timerを本番配備。手動実行成功、次回03:19 JST予定。90件・120日保持 |
| ログ | アプリ・Gunicorn・subappをjournalへ集約済み。ホスト全体の永続journal設定は未配備 |
| Web管理操作 | `/backup`と`/initdb`を本番から削除し、404を確認。既存DBを上書きしない初期化CLIへ置換 |
| DOM安全性 | 安全なDOM操作を本番配備 |
| Phase 6 smoke | commit `95cbe74`をRPiの`/tmp`へ展開し、online snapshot（SHA-256 `76b690940339a5a2bd44f4ab6c7f5f088fc398bb98ba46c56815a7b573c3c4f3`）を使う127.0.0.1:5100で30項目が成功。一時serviceを停止し、一時DB・展開先も削除済み |
| 本番反映 | commit `16e6515`を配備。本番checkout clean、app/subappは`NRestarts=0`、公開ページ200 |
| off-host backup | 修復直前snapshotを承認済みの権限制限付きローカル領域へSSHコピーし、SHA-256一致を確認。恒久的な暗号化recipientは未確立 |
| SOPS + age | SOPS 3.13.3はSHA-256検証済み。age 1.3.2は取得物を検証できず破棄したため、端末鍵とrecipientは未作成 |

本番切替では`labook`と`labook-subapp`だけを再起動した。nginx、ngrok、ホスト全体のjournald設定は変更していない。

DB修復の承認事項と実行手順は[`docs/database-repair.md`](database-repair.md)に分離した。
日次backupの保持方針と本番導入手順は[`docs/backup-operations.md`](backup-operations.md)に分離した。
ログの記録項目と移行確認手順は[`docs/logging-operations.md`](logging-operations.md)に分離した。

## 1.2 変更

tailscale経由の実機のipが`100.110.113.62`に変更になった

## 2. システム全体像

```text
スマートフォン / PC
  ├─ 書籍一覧・管理画面
  └─ ブラウザのカメラ + QuaggaJSによるISBNスキャン
              │
              ▼
      nginx :80 on Raspberry Pi
              │
              ▼
 Gunicorn :5000 on 127.0.0.1
      9 sync workers
              │
              ▼
          Flask app
      ├─ SQLite: library.db
      ├─ covers/
      ├─ Google Books API
      ├─ 楽天Books API
      ├─ 国立国会図書館API
      └─ Notion API

別プロセス: subapp.py
      └─ Notionの新着レビューをSlackへ通知

systemd timer: labook-backup.timer
      └─ SQLite online backup + integrity check + local retention

外部公開経路:
      ngrok + traffic policy → nginx :80
```

RPi固有のGPIOや周辺機器制御はない。バーコード読取に使うカメラはクライアント端末側のブラウザ機能であり、RPiはWeb、DB、トンネル、定期処理の実行ホストである。

## 3. ローカルリポジトリの状態

### 3.1 Git

- 開発ブランチ: `dev-miya`
- 開発HEAD: `16e6515`
- 調査開始時の実機HEAD: `834a63a`
- 2026-09-01切替後の実機HEAD: `16e6515`、branch `deploy`、worktree clean
- 調査開始時の`834a63a..c301ea7`はツリー差分0件だった。その後の改善commitを含む`16e6515`を本番配備した

### 3.2 構成

- Flaskアプリ: [`app.py`](../app.py)
- DB接続・初期スキーマ: [`db.py`](../db.py)
- API Blueprint: [`routes/`](../routes)
- ブラウザ側処理: [`static/`](../static)
- バックアップ・Slack通知: [`subapp.py`](../subapp.py), [`slack_notify.py`](../slack_notify.py)
- Gunicorn起動: [`start_gunicorn.sh`](../start_gunicorn.sh)
- 手動デプロイ: [`Prod.sh`](../Prod.sh)

### 3.3 再現性に関する不足

- `requirements.txt`、`pyproject.toml`、lockファイルがない
- 調査開始時点では自動テストがなかった
- systemd unit、nginx設定、ngrok設定がリポジトリ管理されていない
- DB schema migrationの仕組みがない
- `keys.py`は`.gitignore`対象だが、作成・更新・失効の運用が定義されていない
- 調査に使用した開発ホストではPythonとNode.jsがPATHに存在せず、そのままではローカルテストを実行できない

## 4. RPi4実機の観測結果

### 4.1 OS・リソース

| 項目 | 観測値 |
|---|---|
| OS | Debian GNU/Linux 12 (bookworm), aarch64 |
| Kernel | `6.12.25+rpt-rpi-v8` |
| Uptime | 約365日20時間 |
| Load average | `0.13, 0.29, 0.23` |
| メモリ | 3.7 GiB中、available約2.0 GiB |
| Swap | なし |
| ルートFS | 58 GiB中7.9 GiB使用、使用率15% |
| CPU温度 | 55.0 ℃ |
| Throttle | `0x0`、スロットリング履歴なし |
| failed systemd units | 0 |

現在のリソース枯渇は確認されなかった。Swapがないこと自体は現在の負荷では問題化していないが、外部API応答停止やworker増加時の挙動は負荷試験で確認する。

### 4.2 サービス

| サービス | 状態 | 起動方法 | 備考 |
|---|---|---|---|
| `labook.service` | active/running | `start_gunicorn.sh` | 切替後`NRestarts=0` |
| `labook-subapp.service` | active/running | `venv/bin/python subapp.py` | Slack scheduler、切替後`NRestarts=0` |
| `nginx.service` | active/running | nginx | port 80 |
| `ngrok-labook.service` | active/running | ngrok → port 80 | traffic policyあり |

Gunicornは127.0.0.1:5000で9 workerを起動している。9 workerが必ず過剰とは断定できないが、SQLiteの並行書き込み、各workerからの外部HTTP、同一ログへの複数プロセス書き込みを含めて検証が必要である。

### 4.3 HTTPヘルスチェック

| 経路 | Status | 応答時間 |
|---|---:|---:|
| `http://127.0.0.1:5000/` | 200 | 約3 ms |
| `http://127.0.0.1/` | 200 | 約3 ms |
| `http://127.0.0.1:5000/books` | 200 | 約13 ms |
| `http://100.65.97.87/`（開発ホストから） | 200 | 約45 ms |

`/healthz`と`/readyz`は本番へ配備済みで、2026-09-01の切替後はいずれも200である。HTTPSの待受けは確認されず、Tailscale IPによる本番ページは`http://100.65.97.87/`である。

access logの集計では500が17件あり、すべて`/books`系だった。

- `/books/manage`: 15件
- `/books/api/fetch_book_info/<isbn>`: 2件
- 最後の500: 2026-02-25 15:12 JST

調査時点で継続中の500エラーは確認されなかった。

### 4.4 過去ログ

Gunicorn error logには次の履歴がある。

| シグネチャ | 件数 |
|---|---:|
| `Address already in use` | 15,713 |
| `Can't connect` | 3,137 |
| `Traceback` | 126 |
| `Worker exiting` | 137 |
| `Booting worker` | 681 |
| `WORKER TIMEOUT` | 0 |

例外の集計は`ModuleNotFoundError` 117件、`IndentationError` 9件だった。最後のerror log更新は2026-02-25のサービス起動時であり、主として過去の環境・デプロイ問題と考えられる。

`labook.service`の`NRestarts=220`とport 5000競合は相関が疑われるが、systemd journalに当時の記録が残っておらず、直接の因果関係までは確定できなかった。

## 5. SQLite調査結果

### 5.1 DB概要

| 項目 | 値 |
|---|---:|
| DBサイズ | 163,840 bytes |
| 最終更新 | 2026-07-08 21:31 JST |
| `PRAGMA integrity_check` | `ok` |
| journal mode | `delete` |
| Books | 995 |
| Users | 2 |
| Shelves | 71 |
| Loans | 23 |
| 貸出中 | 2 |

最新の日次バックアップについても`integrity_check=ok`だった。

### 5.2 外部キー違反

`PRAGMA foreign_key_check`の結果は477件だった。

| 子テーブル | 親テーブル | 件数 |
|---|---|---:|
| Books | Users | 469 |
| Loans | Books | 8 |

Booksの`owner_id`分布:

| 状態 | 件数 |
|---|---:|
| NULL | 526 |
| 0 | 375 |
| 現在のUsersに存在するID | 0 |
| 空文字 | 94 |
| 0・空文字以外でUsersに存在しないID | 0 |

Shelvesへの不正参照、Loansのborrower/returnerへの不正参照は0件だった。

原因は、SQLite接続時に`PRAGMA foreign_keys=ON`を設定していないことと、Booksの`owner_id`既定値が0であることが中心と考えられる。追加調査により残り94件は欠落IDではなく空文字と判明した。孤立Loan 8件のうち2件は未返却であり、どう扱うかはデータの意味を確認して決める必要がある。

制約を直ちに有効化すると、既存データや現行書き込みが失敗する可能性がある。必ずバックアップ、分類、修復、dry-runの後に有効化する。

### 5.3 バックアップ

- リポジトリ配下で確認できたバックアップ: 195個
- 合計: 31,461,376 bytes
- 最古: 2026-02-25
- 最新: 2026-08-31
- 保存数、保存期間、容量の上限なし
- 調査開始時点の[`subapp.py`](../subapp.py)は稼働中のSQLiteファイルを`shutil.copy`でコピーしていた
- 同一RPi、同一ファイルシステム上のバックアップであり、SDカード故障への耐性は確認できない

現在確認したDBコピーは整合していたが、今後はSQLite Backup APIを使い、復元確認とオフホスト保管を組み合わせる。

## 6. コード上の主要リスク

### 6.1 P0: データ整合性

- [`db.py`](../db.py)の各接続で外部キー制約が有効化されていない
- `owner_id DEFAULT 0`と実在Usersの間に意味上の不一致がある
- 書籍削除後もLoansが残り得る
- 調査開始時点では、同一ISBNに複数の未返却Loanを作ることをDB/APIが防いでいなかった
- 書籍更新、返却、新規貸出が一連のUI操作に依存し、サーバー側では原子的でない

### 6.2 P1: 外部API障害

[`fetch_book_info.py`](../fetch_book_info.py)、[`routes/notion.py`](../routes/notion.py)、[`slack_notify.py`](../slack_notify.py)の`requests`呼び出しには明示的なtimeoutがない。外部サービスやDNSが停止するとGunicorn workerやsubappが長時間待つ可能性がある。

書誌情報取得は3サービスを並列に呼ぶため、サービスごとのtimeout、全体deadline、部分成功、再試行方針を分ける。

### 6.3 P1: デプロイと再起動

調査時点の[`Prod.sh`](../Prod.sh)はport 5000のPIDを`kill -9`した後で、`Restart=always`のsystemd serviceを再起動していた。systemd管理外のプロセス混在や自動再起動との競合を起こしやすいため、開発branchではsystemdだけを使う手順へ修正済みである。

デプロイは次の順に単純化する。

1. 配備内容と設定の検証
2. DBバックアップ
3. `systemctl restart labook`
4. `systemctl is-active`と`/healthz`確認
5. 失敗時に旧commitへ戻して再起動

portに対する直接の`kill -9`は通常手順から除外する。

### 6.4 P1: SQLite並行性

- journal modeは`delete`
- Gunicornは9 worker
- busy timeoutはsqlite3既定値に依存
- 棚の検索・作成で、Flask workerからlocalhost:5000のFlask APIを再度呼んでいる: [`routes/books.py`](../routes/books.py)

同時書き込み時の`database is locked`、棚作成競合、全workerが自己HTTP待ちになる状態を負荷試験する。結果に基づき、DB helperへの直接置換、transaction境界、`busy_timeout`、WAL、worker/thread数を決める。

### 6.5 P2: 正しさとエラー処理

- `normalize_publication_date()`は`YYYY-MM-DD`入力時に値をreturnせず、`None`になる
- ISBNを`int()`へ変換する前のサーバー側検証が不足
- 書籍追加時の広い`except Exception`が原因をすべて409へ変換する
- `abort()`より後のエラーログは実行されない
- 外部APIのJSON形式不正や非200応答の扱いが統一されていない
- HTTP自己呼び出しで例外を握りつぶしている

### 6.6 P2: ログ

- 書籍追加・更新時にリクエストデータ全体を記録している
- 調査開始時点ではFlask loggerのRotatingFileHandlerを複数Gunicorn workerから使用する構成だった
- 調査開始時点ではGunicorn access/error logにrotation設定がなかった
- access logは調査時点で約21 MB

アプリ、Gunicorn、subappは本番でsystemd journalへ集約し、queryを除外したaccess log形式とunitごとのrate limitを適用済みである。本番のjournalは引き続き`Storage=volatile`であり、host全体へ影響する256 MB・30日上限の永続化設定は未配備である。

コメント、利用者情報、外部API応答、tokenをログへ出さない。request ID、処理時間、結果、例外型などの診断情報だけを構造化して残す。

### 6.7 P1: 公開境界とWebセキュリティ

- Flask API自体に認証・認可がない
- nginxはLANのport 80で待受けており、ngrok側のtraffic policyを経由しないアクセス経路がある
- nginx CORS設定は`Access-Control-Allow-Origin: *`とcredentialsを同時指定している
- CORS許可メソッドにUIが使うPUT/DELETEが含まれていない
- 調査開始時点ではNotion由来reviewやDB由来書籍情報をJavaScriptの`innerHTML`へ挿入していた（安全なDOM操作を本番配備済み）
- 調査開始時点では`/backup`がHTTPから実行可能だった（本番route削除済み）
- 調査開始時点では`/initdb`が公開ルートに残っていた（本番route削除済み。上書き拒否のローカルCLIへ置換）

実際の利用者・ネットワーク境界を確認し、nginxまたはアプリ側で認証・認可を統一する。外部文字列は`textContent`でDOMへ追加する。

## 7. デバッグ・改善計画

### Phase 0: データ保全とベースライン固定

1. SQLite Backup APIでタイムスタンプ付きバックアップを作成
2. SHA-256、`integrity_check`、`foreign_key_check`結果を記録
3. 別ホストへ暗号化してコピー
4. バックアップから別名DBへの復元を試験
5. 現行service、nginx、Python package、Git commitのスナップショットを保存
6. 不整合477件を値を公開しない集計レポートにする

このPhaseでは本番DBの内容を変更しない。

### Phase 1: 開発環境の再現

1. 実機venvから直接依存と間接依存を採取
2. Pythonの対応versionを定義し、requirementsをlock
3. `config.py`を追加し、起動時に必須設定名だけを検証
4. 匿名化DB fixtureと空DB fixtureを作成
5. pytestを導入
6. 外部APIをmockする
7. Windows/Linux双方のセットアップ手順を文書化

最低限のテスト対象:

- DB初期化とschema
- 書籍CRUD
- 棚の作成・移動・重複
- 貸出・返却・二重貸出
- ISBN-10/ISBN-13と不正入力
- 出版日正規化
- cover upload
- 外部APIの成功、404、429、500、invalid JSON、timeout
- Notion/Slack停止時に本体が継続稼働すること

### Phase 2: データ修復と制約有効化

1. `owner_id`の業務上の意味を確認
2. 469件をNULL化、再割当、履歴テーブル退避のいずれかに分類
3. 孤立Loan 8件を退避または参照修復
4. dry-runと変更件数確認ができるmigrationを作成
5. DBコピー上でmigrationとrollbackを試験
6. `foreign_key_check=0`を確認
7. 各connectionで`PRAGMA foreign_keys=ON`
8. 削除時の`RESTRICT`、`SET NULL`、履歴保持方針をschemaへ明記

### Phase 3: 障害耐性と整合性

1. 外部HTTPへconnect/read timeoutと全体deadlineを設定
2. 期待可能なエラーと内部エラーのレスポンスを分離
3. localhostへの自己HTTPをDB/service関数へ置換
4. 貸出・返却をtransaction化
5. 同一ISBNの未返却Loanを1件に制限
6. SQLiteのWAL、busy timeout、Gunicorn worker/thread数を負荷試験
7. `/healthz`と、必須のSQLite接続を確認する`/readyz`を追加（実装済み。外部APIは書籍操作時の部分障害継続を優先し、probeからは呼び出さない）

### Phase 4: 運用整備

1. `kill -9`依存を廃止（本番配備済み）
2. subappも同じvenvと設定loaderを利用（本番配備済み）
3. 日次backupをsystemd timerへ移行（本番配備・手動実行済み）
4. backupの保存数、保存期間、オフホスト転送を設定（90件・120日保持は本番配備。恒久的な暗号化off-host転送は未実施）
5. access/error/application logを上限付きjournalへ統合（service単位は本番配備。host全体の永続化は未配備）
6. unit、nginx、Gunicorn設定をリポジトリ管理（systemd/Gunicornを本番配備。nginxは現行設定を維持）
7. rollback手順を自動化

### Phase 5: セキュリティ境界

1. LAN、学内proxy、ngrokそれぞれの利用者と認証境界を図示
2. APIの認証・認可方式を決定
3. CORSを必要なorigin/methodだけに限定
4. HTML挿入を安全なDOM操作へ変更（本番配備済み）
5. `/backup`、`/initdb`などの管理操作をWeb公開から外す（本番配備済み、404確認）
6. file uploadの容量、実体MIME、保存名を検証
7. secretsをログやエラー応答へ出さないテストを追加

### Phase 6: 段階的リリース

1. 開発ホストで全自動テスト
2. DBコピーを使い、RPiの別portでsmoke test（2026-09-01実施済み。commit `95cbe74`、127.0.0.1:5100、30/30項目成功）
3. 保守時間前にbackupとrollback確認（2026-09-01実施済み）
4. migration適用（2026-09-01実施済み、477→0）
5. service切替（2026-09-01実施済み、commit `16e6515`）
6. 登録、編集、検索、棚移動、貸出、返却、レビューを確認
7. error rate、latency、service restart数を監視

Step 2ではSQLite Backup APIで作成・検証した本番DB snapshotだけを`/tmp/labook-smoke-95cbe74`で使用し、登録、編集、棚移動、貸出、二重貸出拒否、返却、二重返却拒否、削除までを確認した。`/backup`と`/initdb`が404であること、health/readiness、主要画面とAPIも含めて30/30項目が成功し、500応答・例外はなかった。テストデータを削除後、一時serviceを停止して5100番が閉じたことを確認し、本番DB snapshotを含む一時展開先も削除した。本番checkoutは`834a63a`のままcleanで、本番アプリ、subapp、nginx、ngrok tunnelは稼働し、`http://100.65.97.87/`は200を返した。

Step 3から5では修復直前backup `/home/pdlab/labook/backups/predeploy/library.db_20260901-234317-943414.db`を作成し、SHA-256 `76b690940339a5a2bd44f4ab6c7f5f088fc398bb98ba46c56815a7b573c3c4f3`を本番内と権限制限付きローカルコピーで照合した。サービス停止後に469 ownerを退避・NULL化し、孤立Loan 8件（未返却2件を含む）を退避・削除して、外部キー違反を0にした。commit `16e6515`とsystemd unitを反映し、app/subapp、日次backup timerを起動した。主要read endpointと公開ページは200、`/backup`と`/initdb`は404、起動後の500・例外・service restartは0である。

## 8. 秘密値管理の検討

### 8.1 現状

コードが参照する秘密値・外部設定は次のとおり。

| 設定名 | 利用箇所 | 備考 |
|---|---|---|
| `RAKUTEN_APP_ID` | `fetch_book_info.py` | 楽天Books書誌検索のApp ID |
| `RAKUTEN_ACCESS_KEY` | `fetch_book_info.py` | 楽天Books書誌検索のAccess Key。HTTPヘッダーで送信 |
| `GOOGLE_API_KEY` | `fetch_book_info.py` | 書誌検索 |
| `NOTION_TOKEN` | `routes/notion.py`, `slack_notify.py` | Notion read/write |
| `NOTION_DATABASE_ID` | 同上 | tokenほど強い秘密ではないが設定として一緒に管理 |
| `SLACK_WEBHOOK_URL` | `slack_notify.py` | URL自体が投稿権限を持つ秘密 |
| `SLACK_APP_TOKEN` | `slack_notify.py` | 現行コードでは代入のみ。必要性を確認して未使用なら削除 |

すべて`keys.py`からimportしている。`keys.py`はGit対象外だが、複数ホストへ安全に配布、更新、失効する方法がない。

### 8.2 要件

- 平文の秘密をGit、チャット、メール、issue、ログへ置かない
- ホストごとに復号identityを分ける
- 秘密鍵をホスト間でコピーしない
- 開発用と本番用の秘密値を分離する
- 開発者全員へ本番秘密を配らない
- 端末追加、端末紛失、メンバー離脱、token漏えい時の手順を定義する
- rotation後に古い秘密を上流サービス側で無効化できる
- 誰・どの端末がどの環境を復号できるか一覧化する
- 平文を長期間ディスクへ残さない

これらは、最小権限、環境ごとの分離、rotation/revocation、ログへの平文出力禁止を基本とする[OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)に沿う。

### 8.3 候補比較

| 方式 | 長所 | 短所 | 適合性 |
|---|---|---|---|
| SOPS + age | provider非依存、Windows/Linux対応、端末別公開鍵、暗号化ファイルをGitでversion管理可能 | 復号操作の集中監査がない、失効時は実secretのrotationも必要 | 現規模の暫定推奨 |
| 共有パスワード管理サービス | ユーザー単位の権限、MFA、監査、失効が容易。CLI連携できる製品もある | サービス契約、アカウント管理、製品依存 | 研究室に既存標準があれば第一候補 |
| Vault / cloud Secrets Manager | 細粒度権限、監査、動的secret、rotation自動化 | 構築・運用負荷が大きい。RPiの可用性が外部サービスへ依存 | 利用者・サービスが増えた段階 |
| 暗号化zip、DM、メール、手動SCP | 導入が容易 | 版管理、失効、監査が弱く、秘密やpasswordが複製され続ける | 通常運用には採用しない |

SOPSはage recipientを複数登録でき、`.sops.yaml`と`updatekeys`で追加・削除できる。Windowsでは既定で`%AppData%\sops\age\keys.txt`を参照する。詳細は[SOPS公式ドキュメント](https://github.com/getsops/sops)を参照する。age自体は公開鍵暗号によるファイル暗号化ツールであり、公式情報は[age](https://age-encryption.org/)を参照する。

### 8.4 推奨構成

将来追加する構成例:

```text
.sops.yaml                    # 公開recipientのみ。Git管理
.env.example                  # 設定名と説明のみ。値なし
secrets/
  dev.enc.env                 # 開発用。許可された開発ホストだけ復号可能
  prod.enc.env                # 本番用。RPi/デプロイ担当だけ復号可能
config.py                     # envまたはsystemd credentialから設定を読む
docs/
  secret-operations.md        # 追加、失効、rotation、事故対応
```

重要な分離:

- `dev.enc.env`と`prod.enc.env`で実際のtokenを別にする
- Notionは可能なら開発用database/integrationを作る
- Slackは開発専用channel/webhookを作る
- Google/Rakutenも開発用keyまたはquota制限付きkeyを使う
- RPiのrecipientを開発用ファイルへ含める必要はない
- 通常の開発ホストを本番用ファイルのrecipientにしない

SOPSに保存する値の例:

```dotenv
RAKUTEN_APP_ID=...
RAKUTEN_ACCESS_KEY=...
GOOGLE_API_KEY=...
NOTION_TOKEN=...
NOTION_DATABASE_ID=...
SLACK_WEBHOOK_URL=...
```

`.env.example`には値を置かず、次のようにする。

```dotenv
RAKUTEN_APP_ID=
RAKUTEN_ACCESS_KEY=
GOOGLE_API_KEY=
NOTION_TOKEN=
NOTION_DATABASE_ID=
SLACK_WEBHOOK_URL=
```

### 8.5 開発ホスト追加手順

1. 各ホストへversionを固定した`age`と`sops`を導入する
2. そのホスト上で専用age keyを生成する
3. 秘密鍵ファイルを現在ユーザーだけが読めるようにする
4. `age-keygen -y`でpublic recipientを出力する
5. public recipientを、本人確認できる既存経路で管理者へ渡す
6. 管理者が`.sops.yaml`の`dev`対象recipientへ追加する
7. `sops updatekeys secrets/dev.enc.env`で暗号化対象を更新する
8. 当該ホストで復号テストする
9. access rosterにホスト名、所有者、public recipient、許可環境、追加日を記録する

public recipientは秘密ではないが、第三者の鍵へ差し替えられないよう、追加時に所有者とfingerprintを確認する。

WindowsのSOPS既定鍵配置:

```powershell
$keyDirectory = Join-Path $env:APPDATA "sops\age"
New-Item -ItemType Directory -Force $keyDirectory
age-keygen -o (Join-Path $keyDirectory "keys.txt")
age-keygen -y (Join-Path $keyDirectory "keys.txt")
```

鍵ファイルのACLは継承状態を含めて確認し、現在ユーザー以外が読めないようにする。Linuxでは通常`~/.config/sops/age/keys.txt`を使用し、directoryを0700、fileを0600にする。

同一人物が複数PCを使う場合でも、PCごとに別の鍵を生成する。これにより、1台の紛失時に他のPCを巻き込まず失効できる。

### 8.6 日常の開発

アプリを先に環境変数対応へ変更する。可能ならSOPSの`exec-env`等で平文ファイルを作らずプロセスを起動する。Windows上のtoolingやdebuggerが対応しない場合だけ、次のようにローカル`.env`へ一時復号する。

```text
sops decrypt --output .env secrets/dev.enc.env
```

運用規則:

- `.env`、`.env.*`、復号途中ファイルを`.gitignore`へ追加する
- `.env.example`だけをGit管理する
- `.env`をチャットやファイル共有へアップロードしない
- shell historyへ値を直接書かない
- screenshot、IDE設定、crash dump、debug logへの混入に注意する
- 作業終了時に不要な平文ファイルを削除する
- 外部API呼び出し時のURLにkeyを含める場合、そのURLをログへ出さない

### 8.7 本番RPiへの渡し方

短期案:

1. 本番復号権限を持つデプロイ担当ホストで`prod.enc.env`を復号
2. SSHの暗号化通信内でRPiのroot管理領域へ配置
3. owner/modeを制限
4. systemdから読み込む
5. 配備元・一時ファイルを削除

目標案:

- systemdの`LoadCredentialEncrypted=`で暗号化credentialをunitへ渡す
- Flask側は`$CREDENTIALS_DIRECTORY`内の個別ファイルから読み込む
- credentialは対象serviceの実行時だけ`/run/credentials/<unit>`に公開する
- RPiのsystemd versionと暗号化方式を検証してから採用する

systemd credentialsは通常のenvironment variableより秘密値の受け渡しに適した仕組みとして説明されている。実装時は[systemd Credentials公式ドキュメント](https://github.com/systemd/systemd/blob/main/docs/CREDENTIALS.md)を基準にする。

本番用秘密値を開発ホスト全台へ渡す設計にはしない。RPiが自動復号する場合はRPi専用identityを使い、その秘密鍵を開発端末へコピーしない。

### 8.8 端末失効・メンバー離脱

1. access rosterで対象recipientと復号可能だった環境を特定
2. `.sops.yaml`からrecipientを削除
3. `sops updatekeys`または必要に応じてdata key rotationを実施
4. 対象者・対象端末が読めた実際のAPI token/webhookを上流で再発行
5. 新しい値を暗号化ファイルへ反映
6. 旧tokenを無効化
7. 本番と開発の動作確認
8. incident/rotation記録を残す

recipientを暗号化ファイルから削除するだけでは不十分である。対象端末が過去のGit revisionや平文を保持している可能性があるため、アクセスを確実に失効するには上流サービスの実tokenをrotationする。

紛失端末が本番秘密を読めなかった場合、本番tokenまで一律にrotationする必要はない。環境を分けることで影響範囲を限定する。

### 8.9 `keys.py`からの移行

1. 現在必要な設定名と利用箇所を確定
2. 未使用の`SLACK_APP_TOKEN`を削除できるか確認
3. 開発用Notion/Slack/API keyを新規発行
4. `config.py`を実装し、必須値がない場合は値を表示せず起動エラーにする
5. `keys.py` importを段階的に置換
6. test用のdummy設定で自動テスト
7. 開発ホストをSOPS + ageへ移行
8. 本番RPiを新方式へ移行
9. 現在の全tokenをrotation
10. 各ホストに残る旧`keys.py`を削除

旧tokenのrotationを最後に行う理由は、過去に`keys.py`がどのホストやbackupへコピーされたかを完全には確認できないためである。

## 9. 完了条件

### データ

- main DBとbackupの`integrity_check=ok`
- `foreign_key_check=0`
- 同一ISBNのactive loanが最大1件
- backupから復元できる
- off-host backupの成功を確認できる

### アプリ

- 書籍登録、編集、削除、検索、棚移動、貸出、返却、reviewのテスト成功
- 不正ISBNや不正JSONが4xxになり、500にならない
- 外部API停止時も設定したdeadline内で応答する
- 外部APIの部分障害で利用可能なデータを返せる
- secretや個人情報をlogへ出さない

### 運用

- `requirements`とPython versionから新規ホストを再構築できる
- systemd/nginx/Gunicorn設定がversion管理される
- port競合なくrestartできる
- `NRestarts`が通常運用中に増加しない
- logとbackupに保存上限がある
- rollback手順が検証済み

### 秘密値

- `keys.py`の手動コピーが不要
- 開発用と本番用tokenが別
- 各ホストが別identityを持つ
- 通常の開発ホストは本番secretを復号できない
- 追加・失効・rotation手順を第三者が再現できる
- token漏えい時に影響対象とrotation対象を特定できる

## 10. 推奨着手順

1. Phase 0の安全なDBスナップショットとオフホスト退避
2. Python開発環境、requirements、pytestの整備
3. `config.py`と環境変数対応
4. SOPS + ageの小規模PoCを2台の開発ホストで実施
5. DB不整合修復migrationの設計とdry-run
6. 外部HTTP timeout、日付正規化、自己HTTPの修正
7. 実機の別portで統合試験
8. DB migrationと段階的本番反映
9. `keys.py`廃止と既存tokenのrotation

最初の本番変更はDB修復ではなく、復元確認済みバックアップの確立とする。
