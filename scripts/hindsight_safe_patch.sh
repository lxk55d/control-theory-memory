#!/usr/bin/env bash
# Hindsight 安全 PATCH 三步法 (config 端点版)
# 用法: hindsight_safe_patch.sh <patch.json>
# PATCH 端点: /v1/default/banks/{bank_id}/config  (不是 /v1/default/banks/{bank_id})

set -euo pipefail

BANK="${HINDSIGHT_BANK:-hermes}"
HOST="${HINDSIGHT_HOST:-http://localhost:8888}"
PATCH_FILE="${1:?usage: $0 <patch.json>}"

# Step 1: 基线
BEFORE=$(curl -s "$HOST/v1/default/banks/$BANK/stats" | \
  python3 -c "import json,sys; print(json.load(sys.stdin)['total_nodes'])")
echo "[$(date +%H:%M:%S)] BEFORE: $BEFORE nodes"

# Step 2: 备份
BACKUP_DIR=~/.hermes/backups/hindsight
mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${BANK}_pre_patch_${TS}.json"
curl -s "$HOST/v1/default/banks/$BANK/export" > "$BACKUP_FILE"
echo "[$(date +%H:%M:%S)] BACKUP: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# Step 3: PATCH (用 /config 端点,不是根 bank 端点)
echo "[$(date +%H:%M:%S)] PATCHING $PATCH_FILE -> $HOST/v1/default/banks/$BANK/config ..."
RESP=$(curl -s -w "\n%{http_code}" -X PATCH "$HOST/v1/default/banks/$BANK/config" \
  -H "Content-Type: application/json" \
  --data @"$PATCH_FILE")
HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
echo "HTTP $HTTP_CODE"
echo "Response (head 500):"
echo "$BODY" | head -c 500
echo

# Step 4: 立即验证
sleep 3
AFTER=$(curl -s "$HOST/v1/default/banks/$BANK/stats" | \
  python3 -c "import json,sys; print(json.load(sys.stdin)['total_nodes'])")
DELTA=$((AFTER - BEFORE))
echo "[$(date +%H:%M:%S)] AFTER: $AFTER nodes (delta=$DELTA)"

# Step 5: 决策
if [ "$DELTA" -lt 0 ]; then
  echo "❌ ALERT: nodes decreased by $((-DELTA))!"
  echo "❌ Auto-rollback from backup..."
  curl -s -X PATCH "$HOST/v1/default/banks/$BANK/config" \
    -H "Content-Type: application/json" \
    --data @"$BACKUP_FILE" > /dev/null
  echo "❌ DO NOT continue without manual investigation."
  exit 2
elif [ "$DELTA" -eq 0 ]; then
  echo "✅ Safe: no node loss"
else
  echo "✅ Safe: nodes increased by $DELTA (acceptable)"
fi
