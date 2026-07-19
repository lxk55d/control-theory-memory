#!/usr/bin/env python3
"""
批量同步所有 LOF 基金日线数据到 a_stock.lof_daily 表
数据源: 腾讯财经 fqkline API
覆盖: 所有 501xxx(SH) + 16xxxx(SZ) 交易所上市基金
"""

import requests
import json
import mysql.connector
import time
import sys

DB_CONFIG = {
    'host': '172.28.128.1',
    'user': 'root',
    'password': 'root',
    'database': 'a_stock',
}

HEADERS = {'User-Agent': 'Mozilla/5.0'}
BATCH_SIZE = 5  # 并发数
SLEEP_BETWEEN = 0.5  # 每个请求间隔

# 代码前缀映射
PREFIX_MAP = {
    '50': 'sh',
    '16': 'sz',
}

def fetch_fqkline(code, market):
    """从腾讯 fqkline API 获取复权日线数据"""
    url = 'http://ifzq.gtimg.cn/appstock/app/fqkline/get'
    params = {'param': f'{market}{code},day,2025-01-01,,640,qfq'}
    try:
        r = requests.get(url, params=params, timeout=15, headers=HEADERS)
        data = r.json()
        key = f'{market}{code}'
        if data.get('data') and data['data'].get(key):
            kd = data['data'][key]
            # Some return 'day', some return 'qfqday'
            if 'day' in kd:
                return kd['day']
            elif 'qfqday' in kd:
                return kd['qfqday']
        return []
    except Exception as e:
        return []


def process_code(code, market, name, cursor):
    """拉取并写入单支 LOF 数据"""
    rows = fetch_fqkline(code, market)
    if not rows:
        return 0, 0

    # Filter for 2025+ only
    rows = [r for r in rows if r[0] >= '2025-01-01']
    if not rows:
        return 0, 0

    insert_sql = """
        INSERT INTO lof_daily (trade_date, code, name, open, high, low, close,
                               pre_close, change_amt, change_pct, volume, amount, adj_factor)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name=VALUES(name), open=VALUES(open), high=VALUES(high),
            low=VALUES(low), close=VALUES(close), pre_close=VALUES(pre_close),
            change_amt=VALUES(change_amt), change_pct=VALUES(change_pct),
            volume=VALUES(volume), amount=VALUES(amount), adj_factor=VALUES(adj_factor)
    """

    inserted = 0
    prev_close = None

    for row in rows:
        trade_date_str = row[0]
        open_p = float(row[1]) if row[1] else None
        close_p = float(row[2]) if row[2] else None
        high_p = float(row[3]) if row[3] else None
        low_p = float(row[4]) if row[4] else None
        volume_hands = float(row[5]) if len(row) > 5 and row[5] else 0

        if not open_p or not close_p:
            prev_close = close_p or prev_close
            continue

        change_amt = None
        change_pct = None
        if prev_close is not None and prev_close != 0:
            change_amt = round(close_p - prev_close, 4)
            change_pct = round((close_p - prev_close) / prev_close * 100, 4)

        volume_shares = int(volume_hands * 100)
        avg_price = (open_p + high_p + low_p + close_p) / 4
        amount_wan = round(avg_price * volume_shares / 10000, 2)

        cursor.execute(insert_sql, (
            trade_date_str, code, name,
            open_p, high_p, low_p, close_p,
            prev_close or 0, change_amt, change_pct,
            volume_shares, amount_wan, 1.0
        ))
        inserted += 1
        prev_close = close_p

    return inserted, len(rows)


def main():
    # Load code list
    with open('/tmp/lof_codes.json', 'r') as f:
        code_map = json.load(f)

    print(f"Total codes to process: {len(code_map)}")

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    total_inserted = 0
    total_codes = 0
    total_skipped = 0
    batch = []
    i = 0

    codes_sorted = sorted(code_map.keys())

    for code in codes_sorted:
        info = code_map[code]
        market = info['market'].lower()
        name = info['name']

        i += 1
        if i % 50 == 0:
            print(f"Progress: {i}/{len(code_map)}, inserted so far: {total_inserted}")

        inserted, total_rows = process_code(code, market, name, cursor)
        if inserted > 0:
            total_inserted += inserted
            total_codes += 1
        else:
            total_skipped += 1

        # 每 10 支提交一次
        if i % 10 == 0:
            conn.commit()

        time.sleep(SLEEP_BETWEEN)

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n===== Done =====")
    print(f"Codes with data: {total_codes}")
    print(f"Codes skipped (no data): {total_skipped}")
    print(f"Total rows inserted: {total_inserted}")


if __name__ == '__main__':
    main()
