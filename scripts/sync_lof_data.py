#!/usr/bin/env python3
"""
同步 LOF 基金日线数据到 a_stock.lof_daily 表
数据源: 腾讯财经 fqkline API
覆盖: 501018 (南方原油LOF), 161226 (国投白银LOF)
时间: 2025-01-01 至今

单位约定 (对齐 etf_daily):
  volume: 股 (手数*100)
  amount: 万元 (成交额/10000)
  price: 元
"""

import requests
import json
import mysql.connector
from datetime import datetime, date

DB_CONFIG = {
    'host': '172.28.128.1',
    'user': 'root',
    'password': 'root',
    'database': 'a_stock',
}

LOF_CODES = {
    '501018': {'prefix': 'sh', 'name': '南方原油LOF'},
    '161226': {'prefix': 'sz', 'name': '国投白银LOF'},
}

HEADERS = {'User-Agent': 'Mozilla/5.0'}


def fetch_fqkline(prefix, code):
    """从腾讯 fqkline API 获取复权日线数据"""
    url = 'http://ifzq.gtimg.cn/appstock/app/fqkline/get'
    params = {'param': f'{prefix}{code},day,2025-01-01,,640,qfq'}
    r = requests.get(url, params=params, timeout=15, headers=HEADERS)
    data = r.json()
    key = f'{prefix}{code}'
    if data.get('data') and data['data'].get(key):
        return data['data'][key]['day']
    return []


def main():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    for code, info in LOF_CODES.items():
        prefix = info['prefix']
        name = info['name']
        print(f'\n===== {code} {name} =====')

        rows = fetch_fqkline(prefix, code)
        print(f'  Got {len(rows)} rows from Tencent API')
        if not rows:
            print('  ERROR: no data returned')
            continue

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
            # Tencent fqkline: [date, open, close, high, low, volume(手)]
            trade_date_str = row[0]
            open_p = float(row[1]) if row[1] else None
            close_p = float(row[2]) if row[2] else None
            high_p = float(row[3]) if row[3] else None
            low_p = float(row[4]) if row[4] else None
            volume_hands = float(row[5]) if len(row) > 5 and row[5] else 0

            if not open_p or not close_p:
                prev_close = close_p or prev_close
                continue

            if trade_date_str < '2025-01-01':
                prev_close = close_p
                continue

            # change
            change_amt = None
            change_pct = None
            if prev_close is not None and prev_close != 0:
                change_amt = round(close_p - prev_close, 4)
                change_pct = round((close_p - prev_close) / prev_close * 100, 4)

            # volume: 手→股
            volume_shares = int(volume_hands * 100)

            # amount: 均价*成交量(股)/10000 → 万元
            avg_price = (open_p + high_p + low_p + close_p) / 4
            amount_wan = round(avg_price * volume_shares / 10000, 2)

            pre_close = prev_close if prev_close else 0

            cursor.execute(insert_sql, (
                trade_date_str, code, name,
                open_p, high_p, low_p, close_p,
                pre_close, change_amt, change_pct,
                volume_shares, amount_wan, 1.0
            ))
            inserted += 1
            prev_close = close_p

        conn.commit()
        print(f'  Inserted/Updated: {inserted}')

        # 验证
        cursor.execute("""
            SELECT COUNT(*), MIN(trade_date), MAX(trade_date),
                   ROUND(AVG(close),4), ROUND(AVG(volume),0)
            FROM lof_daily WHERE code = %s
        """, (code,))
        cnt, min_d, max_d, avg_c, avg_v = cursor.fetchone()
        print(f'  Verification: {cnt} rows, {min_d} -> {max_d}')
        print(f'  Avg close: {avg_c}, Avg volume(shares): {int(avg_v)}')

    cursor.close()
    conn.close()
    print('\n===== Done =====')


if __name__ == '__main__':
    main()
