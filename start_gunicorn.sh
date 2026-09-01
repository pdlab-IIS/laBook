#!/usr/bin/env bash
set -Eeuo pipefail

readonly app_dir="${LABOOK_APP_DIR:-/home/pdlab/labook}"
readonly venv_dir="${LABOOK_VENV_DIR:-${app_dir}/venv}"

source "${venv_dir}/bin/activate"
cd "${app_dir}"

exec gunicorn \
  --workers 9 \
  --bind 127.0.0.1:5000 \
  --access-logfile - \
  --access-logformat '%({x-forwarded-for}i)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(L)s' \
  --error-logfile - \
  --capture-output \
  app:app
