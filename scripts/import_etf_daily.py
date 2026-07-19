#!/usr/bin/env python3
"""
导入 ETF 日线数据 (etf_daily) 从 CSV 文件
过滤已存在数据，每5000行一批commit，完成后删除CSV
"""

import os
import sys
import csv
import mysql.connector
from datetime import datetime

DB_CONFIG = {
    'host': '172.28.128.1',
    'user': 'root',
    'password': 'root',
    'database': 'a_stock',
}

CSV_DIR = '/mnt/e/BaiduNetdiskDownload/基本数据/ETF_按日期'
CSV_FILES = ['20260601.csv', '20260602.csv', '20260603.csv']

COLUMN_MAP = {
    '日期': 'trade_date',
    '代码': 'code',
    '名称': 'name',
    '开盘价': 'open',
    '最高价': 'high',
    '最低价': 'low',
    '收盘价': 'close',
    '上日收盘': 'pre_close',
    '涨跌': 'change_amt',
    '涨幅%': 'change_pct',
    '成交量(手数)': 'volume',
    '成交额(千元)': 'amount',
    '复权因子': 'adj_factor',
}

INSERT_SQL = """
    INSERT INTO etf_daily (trade_date, code, name, open, high, low, close,
                           pre_close, change_amt, change_pct, volume, amount, adj_factor)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        name=VALUES(name), open=VALUES(open), high=VALUES(high),
        low=VALUES(low), close=VALUES(close), pre_close=VALUES(pre_close),
        change_amt=VALUES(change_amt), change_pct=VALUES(change_pct),
        volume=VALUES(volume), amount=VALUES(amount), adj_factor=VALUES(adj_factor)
"""


def parse_value(val, col_type):
    """Parse CSV value based on target column type"""
    if val is None or val.strip() == '':
        return None
    val = val.strip()
    if col_type in ('open', 'high', 'low', 'close', 'pre_close', 'change_amt'):
        return float(val)
    elif col_type == 'change_pct':
        return float(val)
    elif col_type == 'volume':
        return int(float(val))
    elif col_type == 'amount':
        return float(val)
    elif col_type == 'adj_factor':
        return float(val)
    elif col_type == 'trade_date':
        # Format: 20260601 -> 2026-06-01
        return f"{val[:4]}-{val[4:6]}-{val[6:]}"
    else:
        return val


def main():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    for csv_file in CSV_FILES:
        csv_path = os.path.join(CSV_DIR, csv_file)
        if not os.path.exists(csv_path):
            print(f"[SKIP] {csv_file} not found")
            continue

        print(f"\n{'='*60}")
        print(f"Processing: {csv_file}")
        print(f"{'='*60}")

        # Read CSV
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        total = len(rows)
        print(f"  Total rows in CSV: {total}")

        # Get existing trade_dates for this file's date
        file_date = csv_file.replace('.csv', '')
        trade_date_str = f"{file_date[:4]}-{file_date[4:6]}-{file_date[6:]}"
        cursor.execute("SELECT code FROM etf_daily WHERE trade_date = %s", (trade_date_str,))
        existing_codes = {row[0] for row in cursor.fetchall()}
        print(f"  Existing codes for {trade_date_str}: {len(existing_codes)}")

        # Filter out existing rows
        new_rows = []
        for row in rows:
            code = row.get('代码', '').strip()
            if code not in existing_codes:
                new_rows.append(row)

        print(f"  New rows to insert: {len(new_rows)}")

        if not new_rows:
            print(f"  No new data, deleting CSV...")
            os.remove(csv_path)
            print(f"  Deleted: {csv_file}")
            continue

        # Insert in batches of 5000
        batch_size = 5000
        total_inserted = 0
        for i in range(0, len(new_rows), batch_size):
            batch = new_rows[i:i + batch_size]
            values = []
            for row in batch:
                values.append((
                    parse_value(row.get('日期', ''), 'trade_date'),
                    parse_value(row.get('代码', ''), 'code'),
                    parse_value(row.get('名称', ''), 'name'),
                    parse_value(row.get('开盘价', ''), 'open'),
                    parse_value(row.get('最高价', ''), 'high'),
                    parse_value(row.get('最低价', ''), 'low'),
                    parse_value(row.get('收盘价', ''), 'close'),
                    parse_value(row.get('上日收盘', ''), 'pre_close'),
                    parse_value(row.get('涨跌', ''), 'change_amt'),
                    parse_value(row.get('涨幅%', ''), 'change_pct'),
                    parse_value(row.get('成交量(手数)', ''), 'volume'),
                    parse_value(row.get('成交额(千元)', ''), 'amount'),
                    parse_value(row.get('复权因子', ''), 'adj_factor'),
                ))

            cursor.executemany(INSERT_SQL, values)
            conn.commit()
            total_inserted += len(batch)
            print(f"  Batch {i//batch_size + 1}: inserted {len(batch)} rows (total: {total_inserted})")

        # Verify
        cursor.execute("SELECT COUNT(*) FROM etf_daily WHERE trade_date = %s", (trade_date_str,))
        cnt = cursor.fetchone()[0]
        print(f"  Verification: {cnt} rows for {trade_date_str}")

        # Delete CSV
        os.remove(csv_path)
        print(f"  Deleted: {csv_file}")

    cursor.close()
    conn.close()
    print(f"\n{'='*60}")
    print("All done!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
