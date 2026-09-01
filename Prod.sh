#!/usr/bin/env bash
set -Eeuo pipefail

readonly services=(labook labook-subapp)
readonly probe_base_url="http://127.0.0.1:5000"
readonly probe_attempts=10

wait_for_probe() {
  local endpoint="$1"
  local attempt

  for ((attempt = 1; attempt <= probe_attempts; attempt++)); do
    if curl \
      --fail \
      --silent \
      --max-time 5 \
      "${probe_base_url}/${endpoint}" >/dev/null; then
      return 0
    fi
    sleep 1
  done

  printf 'Probe failed after %d attempts: %s/%s\n' \
    "$probe_attempts" "$probe_base_url" "$endpoint" >&2
  return 1
}

sudo systemctl daemon-reload
sudo systemctl restart "${services[@]}"

for service in "${services[@]}"; do
  if ! sudo systemctl is-active --quiet "$service"; then
    sudo systemctl --no-pager --full status "$service" >&2 || true
    exit 1
  fi
done

for endpoint in healthz readyz; do
  wait_for_probe "$endpoint"
done

printf 'laBook deployment checks passed.\n'
