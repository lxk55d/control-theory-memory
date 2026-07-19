#!/root/.venv/bin/python3
"""
七星ETF轮动策略 - 收盘日报生成器
每日收盘后运行，输出策略运行日报

数据源: akshare 新浪财经 (fund_etf_hist_sina)
参考策略: 七星ETF轮动策略 (PTrade版本)
"""

import os
import sys
import math
import json
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
import traceback

# ==================== 代理配置 ====================
# 动态检测 WSL 网关 IP（WSL 重启后虚拟网卡 IP 会变）
import subprocess
_gw = subprocess.run(
    ["ip", "route", "show", "default"],
    capture_output=True, text=True, timeout=5
)
_gateway_ip = _gw.stdout.strip().split()[2] if _gw.returncode == 0 else "172.28.128.1"
PROXY = f"http://{_gateway_ip}:7897"
os.environ['http_proxy'] = PROXY
os.environ['https_proxy'] = PROXY

# ==================== 常量 ====================
REPORT_DIR = "/mnt/e/Obsidian/七星ETF日报"
os.makedirs(REPORT_DIR, exist_ok=True)

# ==================== ETF池 ====================
# 格式: code_6digits -> (sina_symbol, ptrade_code, name)
# sina_symbol: shXXXXXX 或 szXXXXXX
ETF_POOL = {
    # 大宗商品ETF
    "518880": ("sh518880", "518880.SS", "黄金ETF华安"),
    "159980": ("sz159980", "159980.SZ", "有色ETF"),
    "159985": ("sz159985", "159985.SZ", "豆粕ETF华夏"),
    "501018": ("sh501018", "501018.SS", "南方原油"),
    "161226": ("sz161226", "161226.SZ", "白银LOF"),
    "159981": ("sz159981", "159981.SZ", "能源化工ETF建信"),
    # 国际ETF
    "513100": ("sh513100", "513100.SS", "纳指ETF国泰"),
    "159509": ("sz159509", "159509.SZ", "纳指科技ETF景顺"),
    "513290": ("sh513290", "513290.SS", "纳指生物科技ETF汇添富"),
    "513500": ("sh513500", "513500.SS", "标普500ETF博时"),
    "159529": ("sz159529", "159529.SZ", "标普消费ETF景顺"),
    "513400": ("sh513400", "513400.SS", "道琼斯ETF鹏华"),
    "513520": ("sh513520", "513520.SS", "日经ETF华夏"),
    "513030": ("sh513030", "513030.SS", "德国ETF华安"),
    "513080": ("sh513080", "513080.SS", "法国ETF华安"),
    "513310": ("sh513310", "513310.SS", "中韩半导体ETF华泰柏瑞"),
    "513730": ("sh513730", "513730.SS", "东南亚科技ETF华泰柏瑞"),
    # 香港ETF
    "159792": ("sz159792", "159792.SZ", "港股通互联网ETF富国"),
    "513130": ("sh513130", "513130.SS", "恒生科技ETF华泰柏瑞"),
    "513050": ("sh513050", "513050.SS", "中概互联网ETF易方达"),
    "159920": ("sz159920", "159920.SZ", "恒生ETF华夏"),
    # 指数ETF
    "510300": ("sh510300", "510300.SS", "沪深300ETF华泰柏瑞"),
    "510500": ("sh510500", "510500.SS", "中证500ETF南方"),
    "510050": ("sh510050", "510050.SS", "上证50ETF华夏"),
    "510210": ("sh510210", "510210.SS", "上证指数ETF富国"),
    "159915": ("sz159915", "159915.SZ", "创业板ETF易方达"),
    "588080": ("sh588080", "588080.SS", "科创50ETF易方达"),
    "512100": ("sh512100", "512100.SS", "中证1000ETF南方"),
    "563360": ("sh563360", "563360.SS", "A500ETF"),
    "563300": ("sh563300", "563300.SS", "中证2000ETF"),
    # 风格ETF
    "512890": ("sh512890", "512890.SS", "红利低波ETF华泰柏瑞"),
    "159967": ("sz159967", "159967.SZ", "创业板成长ETF华夏"),
    "512040": ("sh512040", "512040.SS", "价值100ETF富国"),
    "159201": ("sz159201", "159201.SZ", "自由现金流ETF华夏"),
    # 债券ETF + 防御
    "511380": ("sh511380", "511380.SS", "可转债ETF"),
    "511010": ("sh511010", "511010.SS", "国债ETF"),
    "511220": ("sh511220", "511220.SS", "城投债ETF"),
    "511880": ("sh511880", "511880.SS", "银华日利ETF"),
}

# 排序用ETF池（不含防御）
ETF_POOL_MAIN = {k: v for k, v in ETF_POOL.items() if k != "511880"}

# 核心参数 (与策略一致)
LOOKBACK_DAYS = 25
SHORT_LOOKBACK_DAYS = 10
HOLDINGS_NUM = 1
MIN_SCORE_THRESHOLD = 0
PROFIT_PROTECTION_LOOKBACK = 1
PROFIT_PROTECTION_THRESHOLD = 0.05
LOSS_THRESHOLD = 0.97
USE_SHORT_MOMENTUM_FILTER = True
SHORT_MOMENTUM_THRESHOLD = 0.0
ENABLE_VOLUME_CHECK = True
VOLUME_LOOKBACK = 5
VOLUME_THRESHOLD = 2
VOLUME_RETURN_LIMIT = 1

# 震荡期参数
ENABLE_RANGE_BOUND_MODE = True
LAPLACE_S_PARAM = 0.05
LAPLACE_MIN_SLOPE = 0.001
GAUSSIAN_SIGMA = 1.2
GAUSSIAN_MIN_SLOPE = 0.002
BIAS_THRESHOLD = 0.10
MA_PERIOD = 20
RSI_OVERBOUGHT = 75
RSI_PULLBACK = 60
LOW_POINT_RISE_THRESHOLD = 0.03
DRAWDOWN_RECOVERY = 0.03
LOOKBACK_HIGH_LOW_DAYS = 20

# ETF名称缓存（从实时行情获取）
ETF_NAMES_CACHE = {}


# ==================== 数据获取 ====================
def fetch_etf_data(sina_symbol, days=60):
    """获取ETF日线数据 - 直接调用东方财富API"""
    import requests as req
    try:
        code_6digit = sina_symbol[2:] if len(sina_symbol) >= 8 else sina_symbol
        # 直接调用东方财富K线API，避免akshare的fund_etf_hist_em重复拉取code_id_map
        market = 1 if code_6digit.startswith(("51", "50", "56", "58")) else 0
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": f"{market}.{code_6digit}",
            "fields1": "f1,f2,f3,f4,f5",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "klt": "101",
            "fqt": "0",
            "beg": "20240101",
            "end": "20261231",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
        }
        r = req.get(url, params=params, timeout=15, proxies={"http": PROXY, "https": PROXY})
        data_json = r.json()
        if not data_json.get("data") or not data_json["data"].get("klines"):
            return None
        items = [item.split(",") for item in data_json["data"]["klines"]]
        df = pd.DataFrame(items, columns=["date","open","close","high","low","volume","amount","_"])
        df = df[["date","open","close","high","low","volume","amount"]]
        for c in ["open","close","high","low","volume","amount"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        cutoff = date.today() - timedelta(days=days + 10)
        df = df[df["date"] >= pd.Timestamp(cutoff)].reset_index(drop=True)
        return df
    except Exception as e:
        return None


def fetch_index_data(index_code, days=60):
    """获取指数日线数据 - 使用东方财富数据源"""
    import akshare as ak
    try:
        # 东方财富需要带市场前缀: sh000001, sh000300, sh000688
        prefix_map = {"000001": "sh000001", "000300": "sh000300", "000688": "sh000688"}
        symbol = prefix_map.get(index_code, f"sh{index_code}")
        df = ak.stock_zh_index_daily_em(symbol=symbol, start_date="20240101", end_date="20261231")
        if df is None or df.empty:
            return None
        # 东方财富接口列名已是英文: date, open, close, high, low, volume, amount
        for c in ["date", "close"]:
            if c not in df.columns:
                return None
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        cutoff = date.today() - timedelta(days=days + 10)
        df = df[df["date"] >= pd.Timestamp(cutoff)].reset_index(drop=True)
        return df
    except Exception:
        return None


def fetch_index_realtime(etf_spot=None):
    """获取指数最新收盘及涨跌（使用日线数据计算）

    新浪指数数据可能延迟1-2个交易日，ETF spot数据今涨跌可用于补充。
    """
    result = {}
    indices = {
        "000001": ("sh000001", "上证指数"),
        "000300": ("sh000300", "沪深300"),
        "000688": ("sh000688", "科创50"),
    }
    today = date.today()
    for idx_code, (sym, name) in indices.items():
        df = fetch_index_data(idx_code, days=10)
        if df is not None and len(df) >= 2:
            latest = df.iloc[-1]
            latest_date = latest["date"]
            if hasattr(latest_date, "date"):
                latest_date = latest_date.date()
            elif hasattr(latest_date, "strftime"):
                latest_date = datetime.strptime(str(latest_date)[:10], "%Y-%m-%d").date()

            # 找最新交易日和前一交易日
            close = float(latest["close"])
            if len(df) >= 2:
                prev = df.iloc[-2]
                prev_close = float(prev["close"])
            else:
                prev_close = close

            if prev_close > 0:
                pct_chg = (close / prev_close - 1) * 100
            else:
                pct_chg = 0

            is_today = (latest_date == today)
            date_label = "今日" if is_today else latest_date.strftime("%m/%d")
            result[idx_code] = {
                "name": name,
                "close": close,
                "pct_chg": pct_chg,
                "date": str(latest_date),
                "date_label": date_label,
            }

    # 尝试用ETF行情补充今日沪深300 pct（510300 沪深300ETF）
    if result.get("000300"):
        r = result["000300"]
        if r.get("date") != str(today):
            if etf_spot and "510300" in etf_spot:
                hs300_etf_pct = etf_spot["510300"].get("pct_chg", 0)
                if "note" not in r:
                    r["note"] = "沪深300ETF估算"
                r["pct_chg_index"] = r["pct_chg"]
                r["pct_chg"] = hs300_etf_pct
                r["date"] = str(today)
                r["date_label"] = "今日"

    return result if result else None


def fetch_etf_spot_data():
    """获取全市场ETF实时行情（更新名称、最新价、涨跌幅）"""
    import akshare as ak
    try:
        df = ak.fund_etf_spot_em()
        result = {}
        for _, row in df.iterrows():
            code = str(row.get("代码", ""))
            result[code] = {
                "name": row.get("名称", ""),
                "close": float(row.get("最新价", 0) or 0),
                "pct_chg": float(row.get("涨跌幅", 0) or 0),
                "high": float(row.get("最高价", 0) or 0),
                "low": float(row.get("最低价", 0) or 0),
            }
        return result
    except Exception:
        return None


# ==================== 核心计算 ====================
def calculate_rsi(close, period=14):
    if len(close) < period + 1:
        return None
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def laplace_filter(price, s=0.05):
    alpha = 1 - np.exp(-s)
    L = np.zeros(len(price))
    L[0] = price[0]
    for t in range(1, len(price)):
        L[t] = alpha * price[t] + (1 - alpha) * L[t - 1]
    return L


def gaussian_filter_last_two(price, sigma=1.2):
    n = len(price)
    if n < 2:
        return 0, 0
    idx_1 = np.arange(n)
    weights_1 = np.exp(-((idx_1 + 1) ** 2) / (2 * sigma ** 2))[::-1]
    weights_1 /= np.sum(weights_1)
    g1 = np.sum(price * weights_1)
    price_2 = price[:-1]
    idx_2 = np.arange(n - 1)
    weights_2 = np.exp(-((idx_2 + 1) ** 2) / (2 * sigma ** 2))[::-1]
    weights_2 /= np.sum(weights_2)
    g2 = np.sum(price_2 * weights_2)
    return g1, g2


def check_profit_protection(close_series, lookback=None, threshold=None):
    lookback = lookback or PROFIT_PROTECTION_LOOKBACK
    threshold = threshold or PROFIT_PROTECTION_THRESHOLD
    if len(close_series) < lookback + 1:
        return False
    recent = close_series[-(lookback + 1):]
    max_high = np.max(recent)
    current_price = recent[-1]
    if current_price <= 0 or max_high <= 0:
        return False
    return current_price <= max_high * (1 - threshold)


def get_current_filter(risk_state):
    """根据风险状态判断当前滤波器类型"""
    if risk_state is None:
        return "正常期"
    if risk_state["should_enter_range"]:
        return "震荡期"
    return "正常期"


def calculate_momentum(code_6digit, daily_data, etf_name=""):
    if daily_data is None or len(daily_data) < LOOKBACK_DAYS:
        return None

    close_arr = daily_data["close"].values.astype(float)
    current_price = float(close_arr[-1])
    if current_price <= 0:
        return None

    # 1. 盈利保护
    if check_profit_protection(close_arr):
        return None

    # 2. 成交量过滤
    if ENABLE_VOLUME_CHECK and len(daily_data) >= VOLUME_LOOKBACK + 1:
        vol_series = daily_data["volume"].values.astype(float)
        recent_vol = vol_series[-1]
        avg_vol = np.mean(vol_series[-(VOLUME_LOOKBACK + 1):-1])
        if avg_vol > 0:
            vol_ratio = recent_vol / avg_vol
            if vol_ratio > VOLUME_THRESHOLD:
                recent_prices = close_arr[-(LOOKBACK_DAYS + 1):]
                y = np.log(recent_prices)
                x = np.arange(len(y))
                weights = np.linspace(1, 2, len(y))
                slope, _ = np.polyfit(x, y, 1, w=weights)
                annualized = math.exp(slope * 250) - 1
                if annualized > VOLUME_RETURN_LIMIT:
                    return None

    # 3. 短期动量过滤
    if len(close_arr) >= SHORT_LOOKBACK_DAYS + 1:
        short_return = close_arr[-1] / close_arr[-(SHORT_LOOKBACK_DAYS + 1)] - 1
        short_annualized = (1 + short_return) ** (250.0 / SHORT_LOOKBACK_DAYS) - 1
    else:
        short_annualized = 0

    if USE_SHORT_MOMENTUM_FILTER and short_annualized < SHORT_MOMENTUM_THRESHOLD:
        return None

    # 4. 长期动量得分
    recent = close_arr[-(LOOKBACK_DAYS + 1):]
    y = np.log(recent)
    x = np.arange(len(y))
    weights = np.linspace(1, 2, len(y))
    slope, intercept = np.polyfit(x, y, 1, w=weights)
    annualized_returns = math.exp(slope * 250) - 1

    ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
    ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else 0
    score = annualized_returns * r_squared

    # 5. 近3日单日跌幅过滤
    if len(close_arr) >= 4:
        day1 = close_arr[-1] / close_arr[-2]
        day2 = close_arr[-2] / close_arr[-3]
        day3 = close_arr[-3] / close_arr[-4]
        if min(day1, day2, day3) < LOSS_THRESHOLD:
            return None

    # 6. 今日涨跌幅
    if len(close_arr) >= 2:
        today_pct = (close_arr[-1] / close_arr[-2] - 1) * 100
    else:
        today_pct = 0

    return {
        "code": code_6digit,
        "name": etf_name,
        "score": score,
        "annualized_returns": annualized_returns,
        "r_squared": r_squared,
        "current_price": current_price,
        "short_annualized": short_annualized,
        "today_pct": today_pct,
    }


def get_risk_benchmark_state(idx_data):
    """分析沪深300风险状态"""
    if idx_data is None or len(idx_data) < max(MA_PERIOD, LOOKBACK_HIGH_LOW_DAYS):
        return None

    close = idx_data["close"].values.astype(float)
    high = idx_data["high"].values.astype(float)
    low = idx_data["low"].values.astype(float)

    current_price = float(close[-1])
    recent_high = np.max(high[-LOOKBACK_HIGH_LOW_DAYS:])
    recent_low = np.min(low[-LOOKBACK_HIGH_LOW_DAYS:])
    ma = np.mean(close[-MA_PERIOD:])
    current_rsi = calculate_rsi(close, period=14)
    bias = (current_price - ma) / ma if ma > 0 else 0
    drawdown = (recent_high - current_price) / recent_high if recent_high > 0 else 0
    rise_from_low = (current_price - recent_low) / recent_low if recent_low > 0 else 0

    should_enter_range = False
    reasons = []

    if bias > BIAS_THRESHOLD:
        should_enter_range = True
        reasons.append(f"乖离率{bias*100:.2f}%>{BIAS_THRESHOLD*100:.0f}%")

    if current_rsi is not None and len(close) >= 15:
        prev_rsi = calculate_rsi(close[:-1], period=14)
        if prev_rsi is not None and prev_rsi > RSI_OVERBOUGHT and current_rsi < RSI_PULLBACK:
            should_enter_range = True
            reasons.append(f"RSI超买回落{prev_rsi:.1f}->{current_rsi:.1f}")

    return {
        "current_price": current_price,
        "recent_high": recent_high,
        "recent_low": recent_low,
        "ma": ma,
        "current_rsi": current_rsi,
        "bias": bias,
        "drawdown": drawdown,
        "rise_from_low": rise_from_low,
        "should_enter_range": should_enter_range,
        "range_enter_reasons": reasons,
    }


# ==================== 报告生成 ====================
def generate_report(results, rank_top5, idx_realtime, risk_state, today_str):
    sep = "=" * 72
    today_display = today_str.replace("-", "/")

    lines = []
    lines.append(f"七星ETF轮动策略 - 收盘日报 — {today_display} 已生成")
    lines.append("")
    lines.append(sep)

    # ===== 核心速览 =====
    lines.append("📊 核心速览")
    lines.append("")
    lines.append(f"{'项目':<20} {'内容'}")
    lines.append("-" * 70)

    if rank_top5:
        top = rank_top5[0]
        pct_str = f"{top['today_pct']:+.2f}%"
        lines.append(f"{'🏆 排名第一':<20} {top['name']}({top['code']}) 得分{top['score']:.2f} 价格¥{top['current_price']:.3f} 日涨{pct_str}")
    else:
        lines.append(f"{'🏆 排名第一':<20} 无符合条件的ETF")

    candidates = " / ".join([f"{r['code']}" for r in rank_top5[:3]]) if rank_top5 else "无"
    cand_names = " / ".join([f"{r['name']}" for r in rank_top5[:3]]) if rank_top5 else ""
    lines.append(f"{'📋 明日备选':<20} {candidates}")
    if cand_names:
        lines.append(f"{'':<20} {cand_names}")
    lines.append("")

    # ===== ETF动量排名 TOP5 =====
    lines.append(sep)
    lines.append("📈 ETF动量排名 TOP5")
    lines.append("")
    header = f"{'排名':<6} {'代码':<8} {'名称':<22} {'动量得分':<10} {'年化收益':<10} {'R²':<8} {'收盘价':<10} {'今日涨跌':<10}"
    lines.append(header)
    lines.append("-" * 84)

    if rank_top5:
        for i, r in enumerate(rank_top5, 1):
            code = r["code"]
            name = r["name"]
            score = f"{r['score']:.2f}"
            ann_ret = f"{r['annualized_returns']*100:+.2f}%"
            rsq = f"{r['r_squared']:.4f}"
            price = f"¥{r['current_price']:.3f}"
            pct = f"{r['today_pct']:+.2f}%"
            lines.append(f"{i:<6} {code:<8} {name:<22} {score:<10} {ann_ret:<10} {rsq:<8} {price:<10} {pct:<10}")
    else:
        lines.append(f"{'无符合条件的ETF':<50}")
    lines.append("")

    # ===== 大盘环境 =====
    lines.append(sep)
    lines.append("🏛️ 大盘环境")
    lines.append("")

    if idx_realtime:
        for idx_code in ["000001", "000300", "000688"]:
            info = idx_realtime.get(idx_code)
            if info:
                name = info.get("name", "")
                close = info.get("close", 0)
                pct = info.get("pct_chg", 0)
                date_label = info.get("date_label", "")
                note = info.get("note", "")
                note_str = f" ({note})" if note else ""
                lines.append(f"  {name:<12} {close:>10.2f}  {pct:+.2f}%  {date_label}{note_str}")

    # 市场简评
    if idx_realtime and "000300" in idx_realtime:
        hs300_pct = idx_realtime["000300"].get("pct_chg", 0)
        if hs300_pct > 1.5:
            lines.append(f"\n  ✅ 沪深300涨幅{hs300_pct:.2f}%，市场整体强势，科技主线延续。")
        elif hs300_pct > 0.5:
            lines.append(f"\n  📈 沪深300涨幅{hs300_pct:.2f}%，市场震荡偏强。")
        elif hs300_pct < -1.5:
            lines.append(f"\n  ⚠️ 沪深300跌幅{hs300_pct:.2f}%，市场整体偏弱，注意控制风险。")
        elif hs300_pct < -0.5:
            lines.append(f"\n  📉 沪深300跌幅{hs300_pct:.2f}%，市场震荡偏弱。")
        else:
            lines.append(f"\n  ↔️  沪深300微幅波动{hs300_pct:.2f}%，市场窄幅震荡。")

    # 震荡期状态
    if risk_state:
        lines.append("")
        filter_name = get_current_filter(risk_state)
        filter_desc = "拉普拉斯滤波器（正常期）" if filter_name == "正常期" else "高斯滤波器（震荡期）"
        lines.append(f"  📊 策略模式: {filter_desc}")

        if risk_state["should_enter_range"]:
            reasons = "; ".join(risk_state["range_enter_reasons"])
            lines.append(f"  ⚠️ 震荡期信号触发: {reasons}")

        if risk_state["current_rsi"] is not None:
            lines.append(f"  📊 沪深300 RSI(14): {risk_state['current_rsi']:.1f}")
        lines.append(f"  📊 乖离率(MA{MA_PERIOD}): {risk_state['bias']*100:.2f}%")
        lines.append(f"  📊 近{LOOKBACK_HIGH_LOW_DAYS}日回撤: {risk_state['drawdown']*100:.2f}%")
    lines.append("")

    # ===== 策略信号 =====
    lines.append(sep)
    lines.append("🔍 策略信号")
    lines.append("")

    if rank_top5:
        top = rank_top5[0]
        if len(rank_top5) >= 2:
            second = rank_top5[1]
            ratio = top["score"] / second["score"] if second["score"] > 0 else float('inf')
            lines.append(f"  🏆 {top['name']}({top['code']}) 得分{top['score']:.2f}，为第二名({second['name']})的{ratio:.1f}倍。")
            if ratio > 3:
                lines.append(f"  ⚡ 动量信号极为强烈，领先优势显著，建议重点关注。")
            elif ratio > 2:
                lines.append(f"  🔥 动量信号较强，领先优势明显。")
        else:
            lines.append(f"  🏆 {top['name']}({top['code']}) 得分{top['score']:.2f}，动量排名第一。")
        ann_str = f"{top['annualized_returns']*100:+.2f}%"
        lines.append(f"  📈 年化动量收益: {ann_str}，R²={top['r_squared']:.4f}")
        lines.append(f"  💡 建议持仓: {top['name']}({top['code']})")
    else:
        lines.append(f"  💤 无符合条件ETF，建议进入防御模式(511880 银华日利)")

    # 全列表得分明细
    if results:
        lines.append("")
        lines.append(sep)
        lines.append("📋 全ETF动量得分明细")
        lines.append("")
        lines.append(f"{'代码':<8} {'名称':<22} {'得分':<10} {'年化收益':<10} {'R²':<8} {'今日涨跌':<8}")
        lines.append("-" * 66)
        for r in results:
            lines.append(f"{r['code']:<8} {r['name']:<22} {r['score']:<10.2f} {r['annualized_returns']*100:+>8.2f}% {r['r_squared']:<8.4f} {r['today_pct']:+>7.2f}%")

    lines.append("")
    lines.append(sep)
    lines.append(f"📅 报告生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("📡 数据来源: 新浪财经 / 东方财富 (akshare)")
    lines.append(f"📌 策略: 七星ETF轮动 | 动量周期: {LOOKBACK_DAYS}天 | 持仓: {HOLDINGS_NUM}只")

    return "\n".join(lines)


def generate_json_report(results, rank_top5, idx_realtime, risk_state, today_str):
    report = {
        "report_date": today_str,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "top5": [],
        "all_results": [],
        "market": {},
        "risk_state": {},
        "total_etfs_analyzed": len(results),
    }

    if rank_top5:
        for i, r in enumerate(rank_top5, 1):
            report["top5"].append({
                "rank": i,
                "code": r["code"],
                "name": r["name"],
                "score": round(r["score"], 4),
                "annualized_returns": round(r["annualized_returns"], 6),
                "r_squared": round(r["r_squared"], 4),
                "close": round(r["current_price"], 4),
                "today_pct": round(r["today_pct"], 2),
            })

    if results:
        for r in results:
            report["all_results"].append({
                "code": r["code"],
                "name": r["name"],
                "score": round(r["score"], 4),
                "annualized_returns": round(r["annualized_returns"], 6),
                "r_squared": round(r["r_squared"], 4),
                "close": round(r["current_price"], 4),
                "today_pct": round(r["today_pct"], 2),
            })

    if idx_realtime:
        for code, info in idx_realtime.items():
            report["market"][code] = {
                "name": info.get("name"),
                "close": info.get("close"),
                "pct_chg": info.get("pct_chg"),
            }

    if risk_state:
        report["risk_state"] = {
            "bias_pct": round(risk_state["bias"] * 100, 2),
            "rsi": round(risk_state["current_rsi"], 1) if risk_state["current_rsi"] is not None else None,
            "drawdown_pct": round(risk_state["drawdown"] * 100, 2),
            "should_enter_range": risk_state["should_enter_range"],
            "reasons": risk_state["range_enter_reasons"],
        }

    return json.dumps(report, ensure_ascii=False, indent=2)


# ==================== 主函数 ====================
def main():
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    weekday = today.weekday()
    is_weekend = weekday >= 5

    print(f"七星ETF轮动策略 - 收盘日报生成器")
    print(f"日期: {today_str}")
    print(f"{'='*60}")

    if is_weekend:
        print("📌 周末非交易日，使用最近交易日数据")

    # Step 1: 获取ETF实时行情（更新名称）
    print("\n[1/5] 获取ETF实时行情...")
    etf_spot = fetch_etf_spot_data()
    if etf_spot:
        for code, info in etf_spot.items():
            if code in ETF_POOL:
                name = info.get("name", "")
                if name:
                    old = ETF_POOL[code]
                    ETF_POOL[code] = (old[0], old[1], name)
        print(f"  ✅ 获取到 {len(etf_spot)} 只ETF行情")
    else:
        print(f"  ⚠️ 无法获取ETF实时行情，使用内置名称")

    # Step 2: 获取指数行情
    print("\n[2/5] 获取指数行情...")
    idx_realtime = fetch_index_realtime(etf_spot)
    if idx_realtime:
        for code in ["000001", "000300", "000688"]:
            info = idx_realtime.get(code)
            if info:
                print(f"  {info['name']}: {info['close']:.2f} ({info['pct_chg']:+.2f}%)")

    idx_300 = fetch_index_data("000300", days=60)
    if idx_300 is not None:
        print(f"  沪深300日线: {len(idx_300)} 条记录")

    risk_state = get_risk_benchmark_state(idx_300)
    filter_name = get_current_filter(risk_state)
    if risk_state:
        reasons_str = ""
        if risk_state["should_enter_range"]:
            reasons_str = f" [触发震荡期: {'; '.join(risk_state['range_enter_reasons'])}]"
        print(f"  策略状态: {filter_name}{reasons_str}")

    # Step 3: 获取各ETF数据并计算动量
    print("\n[3/5] 获取各ETF日线数据并计算动量...")
    results = []
    failed = 0
    filtered = 0
    total = len(ETF_POOL_MAIN)
    idx = 0

    for code_6digit, (sina_sym, ptrade_code, etf_name) in ETF_POOL_MAIN.items():
        idx += 1
        try:
            df = fetch_etf_data(sina_sym, days=LOOKBACK_DAYS + 20)
            if df is not None:
                metrics = calculate_momentum(code_6digit, df, etf_name)
                if metrics is not None:
                    # 补充今日涨跌幅
                    if etf_spot and code_6digit in etf_spot:
                        metrics["today_pct"] = etf_spot[code_6digit].get("pct_chg", 0)
                    results.append(metrics)
                    print(f"  [{idx}/{total}] ✓ {code_6digit} {etf_name:<16} 得分={metrics['score']:.2f}")
                else:
                    filtered += 1
                    if idx <= total:
                        print(f"  [{idx}/{total}] - {code_6digit} {etf_name:<16} 过滤排除")
            else:
                failed += 1
                print(f"  [{idx}/{total}] ✗ {code_6digit} {etf_name:<16} 数据获取失败")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            failed += 1
            print(f"  [{idx}/{total}] ✗ {code_6digit} {etf_name:<16} 错误: {e}")

    print(f"\n  ✅ 成功: {len(results)}, 过滤排除: {filtered}, 数据失败: {failed}")

    # 排序
    results.sort(key=lambda x: x["score"], reverse=True)
    rank_top5 = results[:5]

    # Step 4: 生成报告
    print("\n[4/5] 生成报告...")
    report_text = generate_report(results, rank_top5, idx_realtime, risk_state, today_str)
    report_json = generate_json_report(results, rank_top5, idx_realtime, risk_state, today_str)

    report_file = os.path.join(REPORT_DIR, f"qixing_report_{today_str}.md")
    json_file = os.path.join(REPORT_DIR, f"qixing_report_{today_str}.json")
    latest_link = os.path.join(REPORT_DIR, "qixing_report_latest.md")

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_text)
    with open(json_file, "w", encoding="utf-8") as f:
        f.write(report_json)

    # 更新最新链接
    if os.path.islink(latest_link):
        os.unlink(latest_link)
    try:
        os.symlink(os.path.basename(report_file), latest_link)
    except:
        pass

    print(f"  报告已保存: {report_file}")
    print(f"  JSON已保存: {json_file}")

    # Step 5: 输出报告
    print(f"\n[5/5] 输出报告")
    print(f"{'='*60}")
    print()
    print(report_text)

    return report_text, report_file


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        traceback.print_exc()
        sys.exit(1)
