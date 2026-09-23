# Slack認証ゲートウェイ

本番運用の正本は[運用手順](../docs/sakura-auth-proxy-plan.md)。

- `sakura/`: Slack OAuth、30日DBセッション、CSRF、固定HTTPS中継。
- `slack-demo/src/Oidc.php`: 本番でも再利用するOIDC検証部品。デモの実配置は削除済みだが、このソースは削除しない。
- `wsgi.py`: `LABOOK_GATEWAY_CONFIG`を必須とする署名付きWSGI入口。
- `inbound.py` / `signing.py`: 固定Host/prefix、HMAC、時刻・nonce・本文検証。
- `rpi-config.example.json`: 架空値のみの設定見本。

従来の`app:app`は切り戻し用として維持する。本番入口は`gateway.wsgi:application`。
鍵は32バイト以上、最大2つのkey IDに対応。nonce DBは所有者専用ディレクトリへ配置する。
本番と試験でDB・鍵・nonceを共有しない。個別設定・秘密はGit外へ保存する。

Python試験は`python -m pytest tests/test_gateway_signing.py tests/test_gateway_inbound.py tests/test_gateway_http.py -q`。
隔離実アプリ試験は`scripts/check_rpi_gateway_app.py`と`tests/run_isolated_gateway_app.py`を使用する。
