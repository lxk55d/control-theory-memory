#!/usr/bin/env bash
# 七星ETF轮动策略 - 收盘日报 Cron 包装脚本
# 每天 15:30 运行（A股收盘后）

set -e

# 代理
export http_proxy=http://172.30.176.1:7897
export https_proxy=http://172.30.176.1:7897

REPORT_DIR="/mnt/e/Obsidian/七星ETF日报"
mkdir -p "$REPORT_DIR"

# 运行日报生成器
/root/.venv/bin/python3 /root/scripts/qixing_etf_daily_report.py 2>&1

# 获取最新报告路径
LATEST_REPORT="$REPORT_DIR/qixing_report_latest.md"
if [ -f "$LATEST_REPORT" ]; then
    echo ""
    echo "========== 日报文件路径 =========="
    echo "报告: $LATEST_REPORT"
fi
