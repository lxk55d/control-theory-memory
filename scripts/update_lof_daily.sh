#!/bin/bash
# LOF基金日线增量更新 - 每日盘后运行
# 数据源：腾讯财经 fqkline API
# 写入：a_stock.lof_daily

cd /root
/root/.venv/bin/python3 /root/scripts/update_lof_daily.py 2>&1
