#!/usr/bin/env bash
# Sync backend CODE from CRM_BACKEND (private, source of truth) to
# CRM-TEST-BACKEND (public, deployed on Railway).
#
# Each repo keeps its OWN config — settings.py, google_credentials, .env and .git
# are never touched. --delete makes TEST mirror CRM_BACKEND's code exactly
# (so moved/deleted files, like the fleet restructure, propagate correctly).
#
# Usage:
#   bash scripts/sync-to-test.sh
#   cd ../CRM-TEST-BACKEND && git add -A && git commit -m "sync" && git push
set -euo pipefail

SRC="/Users/apple/Documents/GitHub/CRM_BACKEND"
DST="/Users/apple/Documents/GitHub/CRM-TEST-BACKEND"

rsync -a --delete \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='libdata/settings.py' \
  --exclude='appflow/services/google_credentials/' \
  "$SRC/src/" "$DST/src/"

rsync -a "$SRC/requirements.txt" "$DST/requirements.txt"

# Alembic migration files live OUTSIDE src/ — sync them too (no --delete: only
# add new revisions, never remove TEST's). env.py / alembic.ini are left alone.
rsync -a "$SRC/migrations/versions/" "$DST/migrations/versions/"

echo "✅ Synced src/ + requirements.txt + migrations/versions"
echo "   Preserved in TEST: libdata/settings.py, google_credentials/, .env, .git"
echo "   Next: cd $DST && git add -A && git commit -m 'sync from CRM_BACKEND' && git push"
