"""
技术指标计算模块
包含：MA / RSI / MACD / 成交量均线 / 量比
"""
from typing import Tuple

import numpy as np
import pandas as pd


# ── 基础指标 ──────────────────────────────────────────────────────────────

def calc_ma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(window=period).mean()
    loss  = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs    = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))


def calc_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """返回 (DIF, DEA, MACD柱)"""
    ema_fast = series.ewm(span=fast,   adjust=False).mean()
    ema_slow = series.ewm(span=slow,   adjust=False).mean()
    dif      = ema_fast - ema_slow
    dea      = dif.ewm(span=signal, adjust=False).mean()
    hist     = (dif - dea) * 2
    return dif, dea, hist


# ── 批量添加指标 ──────────────────────────────────────────────────────────

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    为 DataFrame 添加所有技术指标，原地修改后返回。
    要求 df 含列: close, volume
    """
    df = df.copy()
    df["ma5"]  = calc_ma(df["close"], 5)
    df["ma20"] = calc_ma(df["close"], 20)
    df["ma60"] = calc_ma(df["close"], 60)
    df["rsi"]  = calc_rsi(df["close"], 14)

    df["macd_dif"], df["macd_dea"], df["macd_hist"] = calc_macd(df["close"])

    df["vol_ma20"] = df["volume"].rolling(window=20).mean()
    df["vol_ratio"] = df["volume"] / (df["vol_ma20"] + 1e-10)

    # 只丢弃 MACD/RSI 未就绪的极早期行（约26根），保留MA60不足时的行
    df.dropna(subset=["rsi", "macd_dif"], inplace=True)
    # MA60/MA20不足时用已有的较短均线填充（展示用，不影响AI决策）
    df["ma60"] = df["ma60"].fillna(df["ma20"]).fillna(df["ma5"])
    df["ma20"] = df["ma20"].fillna(df["ma5"])
    df["vol_ma20"] = df["vol_ma20"].fillna(df["volume"])
    return df


def get_latest_indicators(df: pd.DataFrame) -> dict:
    """提取最新一行的技术指标快照，附带衍生字段供 AI 使用"""
    if df.empty:
        return {}
    row   = df.iloc[-1]
    price = float(row["close"])
    ma5   = float(row["ma5"])
    ma20  = float(row["ma20"])
    ma60  = float(row["ma60"])

    # ── 均线排列 ──────────────────────────────────────────────────────────
    if ma5 > ma20 > ma60:
        ma_arr = "多头排列（MA5>MA20>MA60）"
    elif ma5 < ma20 < ma60:
        ma_arr = "空头排列（MA5<MA20<MA60）"
    else:
        ma_arr = "均线粘合/交叉（方向不明）"

    ma20_dist = round((price - ma20) / ma20 * 100, 2) if ma20 > 0 else 0.0
    ma60_dist = round((price - ma60) / ma60 * 100, 2) if ma60 > 0 else 0.0

    # ── 5日涨跌幅 ────────────────────────────────────────────────────────
    change_5d = 0.0
    if len(df) >= 6:
        prev5 = float(df.iloc[-6]["close"])
        change_5d = round((price - prev5) / prev5 * 100, 2) if prev5 > 0 else 0.0

    # ── RSI 区间描述 ──────────────────────────────────────────────────────
    rsi_val = float(row["rsi"])
    if rsi_val > 78:
        rsi_zone = "超买区（>78，追高风险）"
    elif rsi_val > 65:
        rsi_zone = "偏强（65~78）"
    elif rsi_val < 25:
        rsi_zone = "超卖区（<25，反弹关注）"
    elif rsi_val < 40:
        rsi_zone = "偏弱（25~40）"
    else:
        rsi_zone = "中性区间（40~65）"

    # ── MACD 金叉/死叉 状态 ───────────────────────────────────────────────
    hist_cur  = float(row["macd_hist"])
    macd_cross = "无明显交叉"
    if len(df) >= 3:
        h = df["macd_hist"].iloc[-3:].values.tolist()
        if h[-2] <= 0 < h[-1]:
            macd_cross = "刚金叉（1日前）"
        elif h[-3] <= 0 < h[-2]:
            macd_cross = "金叉（2日前）"
        elif h[-2] >= 0 > h[-1]:
            macd_cross = "刚死叉（1日前）"
        elif h[-3] >= 0 > h[-2]:
            macd_cross = "死叉（2日前）"
        elif hist_cur > 0:
            macd_cross = "金叉区间（DIF>DEA）"
        else:
            macd_cross = "死叉区间（DIF<DEA）"

    return {
        "price":          round(price, 3),
        "ma5":            round(ma5,   3),
        "ma20":           round(ma20,  3),
        "ma60":           round(ma60,  3),
        "ma_arrangement": ma_arr,
        "ma20_dist_pct":  ma20_dist,
        "ma60_dist_pct":  ma60_dist,
        "change_5d_pct":  change_5d,
        "rsi":            round(rsi_val, 2),
        "rsi_zone":       rsi_zone,
        "macd_dif":       round(float(row["macd_dif"]),  4),
        "macd_dea":       round(float(row["macd_dea"]),  4),
        "macd_hist":      round(hist_cur,                4),
        "macd_cross":     macd_cross,
        "vol":            int(row["volume"]),
        "vol_avg":        int(row["vol_ma20"]),
        "vol_ratio":      round(float(row["vol_ratio"]), 2),
    }


def get_recent_bars(df: pd.DataFrame, n: int = 20) -> list:
    """返回最近 n 根日线的 OHLCV + 技术数据（供 AI 读取趋势）"""
    if df.empty:
        return []
    tail = df.tail(n + 1).copy()
    tail["chg_pct"] = tail["close"].pct_change() * 100
    rows = []
    for idx, row in tail.tail(n).iterrows():
        rows.append({
            "date":      str(idx.date()),
            "open":      round(float(row["open"]),      3) if "open"   in row and not np.isnan(row["open"])   else 0.0,
            "high":      round(float(row["high"]),      3) if "high"   in row and not np.isnan(row["high"])   else 0.0,
            "low":       round(float(row["low"]),       3) if "low"    in row and not np.isnan(row["low"])    else 0.0,
            "close":     round(float(row["close"]),     3),
            "chg_pct":   round(float(row["chg_pct"]),   2) if not np.isnan(row["chg_pct"]) else 0.0,
            "vol_ratio": round(float(row["vol_ratio"]),  2),
        })
    return rows
