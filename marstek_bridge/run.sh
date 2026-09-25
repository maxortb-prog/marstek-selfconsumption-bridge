#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

export PYTHONUNBUFFERED=1
export PYTHONPATH=/

cd /
exec python3 -m app.main
