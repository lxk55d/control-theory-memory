#!/usr/bin/env python3
"""
增量更新 LOF 日线数据 (lof_daily)
仅拉取缺失日期（最新交易日至今），避免全量拉取
可配合 cron 每日盘后运行

数据源: 腾讯财经 fqkline API
"""

import requests
import mysql.connector
from datetime import datetime, timedelta
import sys

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


def get_latest_date(cursor, code):
    cursor.execute("SELECT MAX(trade_date) FROM lof_daily WHERE code=%s", (code,))
    r = cursor.fetchone()
    return r[0]


def fetch_fqkline(prefix, code, start_date):
    url = 'http://ifzq.gtimg.cn/appstock/app/fqkline/get'
    params = {'param': f'{prefix}{code},day,{start_date},,640,qfq'}
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
        latest = get_latest_date(cursor, code)
        if latest:
            start = latest.strftime('%Y-%m-%d')
        else:
            start = '2025-01-01'

        rows = fetch_fqkline(prefix, code, start)
        if not rows:
            print(f'{code}: no data')
            continue

        # 过滤出需要新增的日期
        new_rows = [r for r in rows if r[0] >= start]
        if not new_rows:
            print(f'{code}: up to date (latest={latest})')
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

        # 如果是增量更新，需要获取前一天的收盘价作为 prev_close
        if latest:
            cursor.execute("SELECT close FROM lof_daily WHERE code=%s AND trade_date=%s", (code, latest))
            r = cursor.fetchone()
            if r:
                prev_close = float(r[0])

        for row in new_rows:
            trade_date_str = row[0]
            open_p = float(row[1]) if row[1] else None
            close_p = float(row[2]) if row[2] else None
            high_p = float(row[3]) if row[3] else None
            low_p = float(row[4]) if row[4] else None
            volume_hands = float(row[5]) if len(row) > 5 and row[5] else 0

            if not open_p or not close_p:
                prev_close = close_p or prev_close
                continue

            # 第一行（latest_date本身）跳过不处理
            if trade_date_str == start and latest:
                prev_close = close_p
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

        conn.commit()
        print(f'{code}: inserted {inserted} new rows (latest was {latest}, now up to {new_rows[-1][0]})')

    cursor.close()
    conn.close()
    print('Done')


if __name__ == '__main__':
    main()
