#!/usr/bin/env bash
set -e

source /home/pdlab/labook/venv/bin/activate
cd /home/pdlab/labook

exec gunicorn \
  --workers 9 \
  --bind 127.0.0.1:5000 \
  --access-logfile /home/pdlab/labook/logs/access.log \
  --error-logfile /home/pdlab/labook/logs/error.log \
  app:app
