"""
行情数据模块
日/周历史: baostock（主）
实时行情: 腾讯行情 qt.gtimg.cn（CDN直连，无代理问题，替代 AkShare）
股票名称: 腾讯行情（含名称字段）+ baostock 降级
分时数据: baostock（5/15/30/60分钟，含A股+ETF）
"""
import logging
import re
from datetime import datetime, timedelta

import baostock as bs
import httpx
import pandas as pd

logger = logging.getLogger(__name__)

# ── 腾讯行情客户端（全局复用，绕过所有代理）────────────────────────────────
_tx_client = httpx.Client(proxy=None, trust_env=False, timeout=5)


def _in_trading_hours() -> bool:
    """判断当前是否在 A 股交易时段（不含法定节假日）"""
    from datetime import time as dtime
    now = datetime.now()
    if now.weekday() >= 5:          # 周六/周日
        return False
    t = now.time()
    return (dtime(9, 25) <= t <= dtime(11, 30) or
            dtime(13, 0) <= t <= dtime(15, 5))


def _last_trading_date() -> str:
    """
    最近已完成的交易日日期（字符串 YYYY-MM-DD）。
    规则：周内且 >= 15:05 → 今天；否则向前找最近工作日。
    仅排除周末，不处理法定节假日（节假日时显示会略有偏差）。
    """
    from datetime import time as dtime
    now = datetime.now()
    if now.weekday() < 5 and now.time() >= dtime(15, 5):
        return now.strftime("%Y-%m-%d")
    d = now - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")

# ── baostock 连接管理 ─────────────────────────────────────────────────────
_bs_logged_in = False


def _ensure_bs_login():
    global _bs_logged_in
    if not _bs_logged_in:
        lg = bs.login()
        if lg.error_code != "0":
            raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")
        _bs_logged_in = True


def _symbol_to_bs(symbol: str) -> str:
    return f"sh.{symbol}" if symbol.startswith(("6", "5")) else f"sz.{symbol}"


def _symbol_to_tx(symbol: str) -> str:
    """腾讯行情前缀：沪市 sh，深市 sz"""
    return f"sh{symbol}" if symbol.startswith(("6", "5")) else f"sz{symbol}"


# ══════════════════════════════════════════════════════════════════════════
# 腾讯行情 API（实时价格 + 股票名称）
# URL: http://qt.gtimg.cn/q=sh600000
# 响应: v_sh600000="1~名称~代码~价格~昨收~今开~总量~...~时间~涨额~涨幅%~最高~最低~...";
# 字段索引（0-based，split('~')，经实测验证）：
#   1=名称  3=最新价  4=昨收  5=今开  6=成交量(手)
#   29=空   30=时间戳(YYYYMMDDHHmmss)  31=涨跌额  32=涨跌幅%  33=今日最高  34=今日最低
# ══════════════════════════════════════════════════════════════════════════

def _get_quote_tencent(symbol: str) -> dict:
    """
    腾讯行情 - 单股实时价格，CDN直连，极速无代理
    响应格式: v_sh600000="1~名称~代码~价格~昨收~今开~总量~...~时间戳~涨额~涨幅~最高~最低~..."
    字段索引(0-based，实测): 1=名称 3=价格 4=昨收 5=今开 6=量
                              29=空 30=时间戳(YYYYMMDDHHmmss) 31=涨额 32=涨幅% 33=最高 34=最低
    """
    try:
        url = f"http://qt.gtimg.cn/q={_symbol_to_tx(symbol)}"
        resp = _tx_client.get(url)
        text = resp.text
        logger.debug(f"[{symbol}] 腾讯行情原始: {text[:120]}")

        m = re.search(r'"([^"]*)"', text)
        if not m or not m.group(1).strip():
            logger.debug(f"[{symbol}] 腾讯行情空响应")
            return {}

        parts = m.group(1).split("~")
        if len(parts) < 4:
            return {}

        def _f(i, default=0.0):
            try:
                v = parts[i].strip() if i < len(parts) else ""
                return float(v) if v else default
            except (ValueError, IndexError):
                return default

        price = _f(3)
        prev_close = _f(4)

        # 如果当前价为0（休市/停牌），用昨收代替
        if price <= 0:
            price = prev_close
        if price <= 0:
            logger.debug(f"[{symbol}] 腾讯行情价格为0")
            return {}

        is_rt   = _in_trading_hours()
        dt_date = datetime.now().strftime("%Y-%m-%d") if is_rt else _last_trading_date()
        # [30] = "YYYYMMDDHHmmss"，取 HHmmss 后8位中前6位 → "HHmmss"
        time_str = ""
        if len(parts) > 30 and len(parts[30]) >= 14:
            time_str = parts[30][8:14]   # "20260417152012" → "152012"

        return {
            "name":        parts[1].strip() if len(parts) > 1 else symbol,
            "price":       price,
            "prev_close":  prev_close,
            "open":        _f(5),
            "high":        _f(33),   # 今日最高（实测字段33）
            "low":         _f(34),   # 今日最低（实测字段34）
            "volume":      _f(6),
            "time":        time_str,
            "is_realtime": is_rt,
            "data_date":   dt_date,
        }
    except Exception as e:
        logger.debug(f"[{symbol}] 腾讯行情异常: {e}")
        return {}


def _get_quote_sina(symbol: str) -> dict:
    """
    新浪行情备用 - 当腾讯API失败时使用
    URL: http://hq.sinajs.cn/list=sh513400
    响应: var hq_str_sh513400="名称,今开,昨收,价格,高,低,...,日期,时间,00";
    字段(0-based): 0=名称 1=今开 2=昨收 3=价格 4=高 5=低 30=日期 31=时间
    """
    try:
        prefix = "sh" if symbol.startswith(("6", "5")) else "sz"
        url = f"http://hq.sinajs.cn/list={prefix}{symbol}"
        # 新浪行情需要 Referer 头，否则可能返回空
        resp = _tx_client.get(url, headers={
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        })
        text = resp.text
        logger.debug(f"[{symbol}] 新浪行情原始: {text[:120]}")

        m = re.search(r'"([^"]*)"', text)
        if not m or not m.group(1).strip():
            return {}

        parts = m.group(1).split(",")
        if len(parts) < 4:
            return {}

        def _f(i, default=0.0):
            try:
                v = parts[i].strip() if i < len(parts) else ""
                return float(v) if v else default
            except (ValueError, IndexError):
                return default

        price = _f(3)
        prev_close = _f(2)
        if price <= 0:
            price = prev_close
        if price <= 0:
            return {}

        is_rt   = _in_trading_hours()
        dt_date = datetime.now().strftime("%Y-%m-%d") if is_rt else _last_trading_date()
        return {
            "name":        parts[0].strip(),
            "price":       price,
            "prev_close":  prev_close,
            "open":        _f(1),
            "high":        _f(4),
            "low":         _f(5),
            "volume":      _f(8),
            "time":        parts[31].strip() if len(parts) > 31 else "",
            "is_realtime": is_rt,
            "data_date":   dt_date,
        }
    except Exception as e:
        logger.debug(f"[{symbol}] 新浪行情异常: {e}")
        return {}


# ══════════════════════════════════════════════════════════════════════════
# 股票名称
# ══════════════════════════════════════════════════════════════════════════

def get_stock_name(symbol: str) -> str:
    """
    返回股票名称（三级降级）
    1. DB 缓存
    2. 腾讯行情 API（实时，含名称字段）
    3. baostock query_stock_basic
    """
    # 1. DB 缓存
    try:
        from database.db import get_symbol_name
        cached = get_symbol_name(symbol)
        if cached and cached != symbol:
            return cached
    except Exception:
        pass

    # 2. 腾讯/新浪行情（响应含名称字段）
    try:
        q = _get_quote_tencent(symbol) or _get_quote_sina(symbol)
        name = (q.get("name") or "").strip()
        if name:
            _cache_name(symbol, name)
            return name
    except Exception:
        pass

    # 3. baostock
    try:
        _ensure_bs_login()
        rs = bs.query_stock_basic(code=_symbol_to_bs(symbol))
        df2 = rs.get_data()
        if not df2.empty and "code_name" in df2.columns:
            name = str(df2.iloc[0]["code_name"]).strip()
            if name:
                _cache_name(symbol, name)
                return name
    except Exception:
        pass

    return symbol


def _cache_name(symbol: str, name: str):
    try:
        from database.db import update_symbol_name
        update_symbol_name(symbol, name)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
# 实时行情
# ══════════════════════════════════════════════════════════════════════════

def get_realtime_quote(symbol: str) -> dict:
    """
    单股实时行情（三级降级）
    1. 腾讯行情 API（CDN直连，is_realtime=True）
    2. 新浪行情 API（备用，is_realtime=True）
    3. baostock 最新收盘（is_realtime=False）
    """
    q = _get_quote_tencent(symbol)
    if q and q.get("price", 0) > 0:
        logger.debug(f"[{symbol}] 腾讯行情成功: {q['price']}")
        return q

    logger.info(f"[{symbol}] 腾讯行情失败，尝试新浪行情")
    q = _get_quote_sina(symbol)
    if q and q.get("price", 0) > 0:
        logger.debug(f"[{symbol}] 新浪行情成功: {q['price']}")
        return q

    logger.info(f"[{symbol}] 实时行情均失败，降级baostock历史收盘")
    return _fallback_realtime(symbol)


def _fallback_realtime(symbol: str) -> dict:
    """baostock 最新一天收盘价（历史数据，is_realtime=False）"""
    try:
        df = get_historical_data(
            symbol,
            end_date=datetime.now().strftime("%Y%m%d"),
            start_date=(datetime.now() - timedelta(days=5)).strftime("%Y%m%d"),
        )
        if df.empty:
            return {}
        last = df.iloc[-1]
        last_date = str(last.name.date()) if hasattr(last.name, "date") else str(last.name)[:10]
        name = get_stock_name(symbol)
        return {
            "symbol":      symbol,
            "name":        name,
            "price":       float(last["close"]),
            "volume":      float(last.get("volume", 0)),
            "pct_change":  float(last.get("pct_change", 0)),
            "is_realtime": False,
            "data_date":   last_date,
        }
    except Exception as e:
        logger.error(f"[{symbol}] 降级行情也失败: {e}")
        return {}


# ══════════════════════════════════════════════════════════════════════════
# 历史日/周线（主用 baostock）
# ══════════════════════════════════════════════════════════════════════════

def get_historical_data(
    symbol: str,
    start_date: str = None,
    end_date: str = None,
    period: str = "daily",
    frequency: str = "d",
) -> pd.DataFrame:
    """获取A股历史行情（前复权），frequency: 'd'=日 | 'w'=周"""
    global _bs_logged_in

    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y%m%d")

    s = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    e = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    try:
        _ensure_bs_login()
        freq = frequency if frequency in ("d", "w", "m") else "d"
        rs = bs.query_history_k_data_plus(
            _symbol_to_bs(symbol),
            "date,open,high,low,close,volume,amount,pctChg,turn",
            start_date=s, end_date=e,
            frequency=freq, adjustflag="2",
        )
        if rs.error_code != "0":
            logger.warning(f"[{symbol}] baostock查询失败({rs.error_msg})")
            _bs_logged_in = False
            return pd.DataFrame()

        df = rs.get_data()
        if df is None or df.empty:
            logger.warning(f"[{symbol}] baostock历史数据为空")
            return pd.DataFrame()

        df.rename(columns={"pctChg": "pct_change", "turn": "turnover"}, inplace=True)
        for col in ("open", "high", "low", "close", "volume", "amount", "pct_change", "turnover"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)
        df.dropna(subset=["close", "volume"], inplace=True)
        logger.info(f"[{symbol}] baostock历史 {len(df)} 条")
        return df

    except Exception as e:
        logger.error(f"[{symbol}] baostock历史异常: {e}")
        _bs_logged_in = False
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════
# 带DB缓存的历史数据（对外主接口）
# ══════════════════════════════════════════════════════════════════════════

def get_historical_data_cached(
    symbol: str,
    start_date: str = None,
    end_date: str = None,
    frequency: str = "d",
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    优先读本地SQLite缓存，不足时增量拉取。
    首次调用从网络拉全量，此后只增量更新，极快。
    force_refresh=True 时强制从网络重新拉取最新数据。
    """
    from database import db as _db

    today    = datetime.now().strftime("%Y-%m-%d")
    end_str  = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}" if end_date else today
    default_years = 2 if frequency == "w" else 5
    start_str = (
        f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
        if start_date
        else (datetime.now() - timedelta(days=365 * default_years)).strftime("%Y-%m-%d")
    )
    period = frequency

    last_date  = _db.get_klines_last_date(symbol, period)
    row_count  = _db.count_klines(symbol, period)
    min_rows   = 100 if frequency == "w" else 300
    data_ok    = last_date and row_count >= min_rows

    need_fetch = True
    fetch_from = start_date or (datetime.now() - timedelta(days=365 * default_years)).strftime("%Y%m%d")

    if force_refresh:
        # 除权等企业行为会导致前复权历史价格全部重算，必须清空重下
        _db.delete_klines(symbol, period)
        logger.info(f"[{symbol}] 强制刷新：清除旧K线缓存，重新全量下载")
        need_fetch = True
        fetch_from = start_date or (datetime.now() - timedelta(days=365 * default_years)).strftime("%Y%m%d")
    elif data_ok:
        last_dt = datetime.strptime(last_date, "%Y-%m-%d")
        if last_date >= today:
            need_fetch = False
        elif frequency == "w" and (datetime.now() - last_dt).days <= 7:
            need_fetch = False
        else:
            fetch_from = (last_dt + timedelta(days=1)).strftime("%Y%m%d")

    if need_fetch:
        fetch_end = end_date or datetime.now().strftime("%Y%m%d")
        if fetch_from > fetch_end:
            need_fetch = False

    if need_fetch:
        fetch_end = end_date or datetime.now().strftime("%Y%m%d")
        try:
            df_new = get_historical_data(symbol, fetch_from, fetch_end, frequency=frequency)
            if not df_new.empty:
                rows = [{
                    "date":       str(idx.date()),
                    "open":       float(row.get("open",   0) or 0),
                    "high":       float(row.get("high",   0) or 0),
                    "low":        float(row.get("low",    0) or 0),
                    "close":      float(row.get("close",  0) or 0),
                    "volume":     float(row.get("volume", 0) or 0),
                    "amount":     float(row.get("amount", 0) or 0),
                    "pct_change": float(row.get("pct_change", 0) or 0),
                } for idx, row in df_new.iterrows()]
                _db.upsert_klines(symbol, rows, period)
                logger.info(f"[{symbol}] K线缓存写入 {len(rows)} 条")
        except Exception as e:
            logger.warning(f"[{symbol}] K线网络更新失败，用缓存: {e}")

    # 从DB读取
    klines = _db.get_klines(symbol, start_str, end_str, period)
    if not klines:
        logger.warning(f"[{symbol}] K线缓存为空，直接网络获取")
        return get_historical_data(symbol, start_date, end_date, frequency=frequency)

    df = pd.DataFrame(klines)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df.sort_index(inplace=True)
    for col in ("open", "high", "low", "close", "volume", "amount", "pct_change"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["close"], inplace=True)
    logger.info(f"[{symbol}] DB缓存K线 {len(df)} 条 ({period})")
    return df


# ══════════════════════════════════════════════════════════════════════════
# 腾讯今日分时数据
# 接口1: web.ifzq.gtimg.cn/appstock/app/minute/query  —— 1分钟累计量价，全天可用
# 接口2: qt.gtimg.cn 今日OHLC  → 合成单根汇总bar（保底，仅交易时段无数据时用）
# ══════════════════════════════════════════════════════════════════════════

def _parse_ifzq_minute(symbol: str) -> list:
    """
    调用腾讯 web.ifzq.gtimg.cn 分时接口，返回1分钟(datetime, price, vol)列表。
    响应格式: min_data_sz002361={"data":{"sz002361":{"data":{"date":"20260417",
        "data":["0930 18.80 60251 ...", ...]}}}}
    volume字段为累计量，需差分计算每分钟实际成交量。
    """
    try:
        code = _symbol_to_tx(symbol)          # e.g. "sz002361"
        url  = (f"https://web.ifzq.gtimg.cn/appstock/app/minute/query"
                f"?_var=min_data_{code}&code={code}")
        resp = _tx_client.get(url, timeout=8)
        text = resp.text

        m = re.search(r'=(\{.*\})', text, re.DOTALL)
        if not m:
            return []
        obj  = __import__("json").loads(m.group(1))
        data_node = obj["data"][code]["data"]
        date_str  = data_node.get("date", "")       # "20260417"
        raw_list  = data_node.get("data", [])

        if not date_str or len(date_str) != 8:
            return []
        year  = int(date_str[:4])
        month = int(date_str[4:6])
        day   = int(date_str[6:])

        rows = []
        prev_vol = 0.0
        for item in raw_list:
            parts = item.split()
            if len(parts) < 3:
                continue
            t_str = parts[0]           # "0930"
            if len(t_str) != 4:
                continue
            try:
                price    = float(parts[1])
                cum_vol  = float(parts[2])
                vol      = max(0.0, cum_vol - prev_vol)
                prev_vol = cum_vol
                dt = datetime(year, month, day, int(t_str[:2]), int(t_str[2:]), 0)
                rows.append((dt, price, vol))
            except (ValueError, IndexError):
                continue
        return rows
    except Exception as e:
        logger.debug(f"[{symbol}] ifzq分时解析失败: {e}")
        return []


def get_intraday_bars_tencent(symbol: str, period: int = 5) -> pd.DataFrame:
    """
    获取今日分时K线，两种方式：
    1. web.ifzq.gtimg.cn 1分钟价量 → 重采样为目标周期（全天可用，数据完整）
    2. qt.gtimg.cn 今日OHLC       → 合成单根汇总bar（保底，仅交易时段）
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    today     = datetime.now().date()

    # ── 方式1: 腾讯分时接口（1分钟→N分钟重采样）────────────────────────
    try:
        rows = _parse_ifzq_minute(symbol)
        # 只保留今日数据（API一般只返回当日，但做防御过滤）
        today_rows = [(dt, p, v) for dt, p, v in rows if dt.date() == today]

        if today_rows:
            df_1m = pd.DataFrame(today_rows, columns=["dt", "price", "vol"]).set_index("dt").sort_index()
            rule   = f"{period}min"
            df_ohlc = df_1m["price"].resample(rule, label="left", closed="left").ohlc()
            df_vol  = df_1m["vol"].resample(rule, label="left", closed="left").sum()
            df_out  = df_ohlc.copy()
            df_out["volume"] = df_vol
            df_out.dropna(subset=["close"], inplace=True)
            if not df_out.empty:
                logger.info(f"[{symbol}] ifzq分时 {len(df_out)} 根 {period}min 日期={today_str}")
                return df_out
            logger.debug(f"[{symbol}] ifzq分时重采样后为空")
        else:
            logger.debug(f"[{symbol}] ifzq分时无今日数据（返回{len(rows)}行）")

    except Exception as e:
        logger.debug(f"[{symbol}] ifzq分时失败: {e}")

    # ── 方式2: qt.gtimg.cn 实时行情 → 合成今日单根bar（交易日保底）────
    from datetime import time as _dtime
    _now = datetime.now()
    _is_trading_day = _now.weekday() < 5 and _dtime(9, 15) <= _now.time() <= _dtime(18, 0)
    if _is_trading_day:
        try:
            q = _get_quote_tencent(symbol)
            if not q:
                q = _get_quote_sina(symbol)
            if q and q.get("price", 0) > 0 and q.get("open", 0) > 0:
                now = datetime.now().replace(second=0, microsecond=0)
                aligned_min = (now.minute // period) * period
                bar_dt = now.replace(minute=aligned_min)
                df_bar = pd.DataFrame([{
                    "open":   q["open"],
                    "high":   q.get("high", q["price"]),
                    "low":    q.get("low",  q["price"]),
                    "close":  q["price"],
                    "volume": q.get("volume", 0),
                }], index=pd.DatetimeIndex([bar_dt]))
                logger.info(f"[{symbol}] 实时行情合成今日bar: {bar_dt} price={q['price']}")
                return df_bar
        except Exception as e:
            logger.debug(f"[{symbol}] 实时行情合成bar失败: {e}")

    return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════
# 分钟 / 分时数据（baostock，最细5分钟，ETF+A股均支持）
# ══════════════════════════════════════════════════════════════════════════

_BS_FREQ_MAP = {"1": "5", "5": "5", "15": "15", "30": "30", "60": "60"}


def get_minute_data(symbol: str, period: str = "5", days: int = 5) -> pd.DataFrame:
    """
    获取分钟级行情（前复权），数据源：baostock。
    period: "1"→5分钟 / "5" / "15" / "30" / "60"
    days  : 最近 N 个自然日
    注意：baostock 分钟数据约在 15:30 后才可用，交易时段内为空
    """
    bs_freq  = _BS_FREQ_MAP.get(str(period), "5")
    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=days + 2)

    try:
        _ensure_bs_login()
        rs = bs.query_history_k_data_plus(
            _symbol_to_bs(symbol),
            "time,open,high,low,close,volume",
            start_date=start_dt.strftime("%Y-%m-%d"),
            end_date=end_dt.strftime("%Y-%m-%d"),
            frequency=bs_freq, adjustflag="2",
        )
        if rs.error_code != "0":
            logger.warning(f"[{symbol}] baostock分钟失败({rs.error_msg})")
            return pd.DataFrame()

        df = rs.get_data()
        if df is None or df.empty:
            return pd.DataFrame()

        df["datetime"] = pd.to_datetime(df["time"], format="%Y%m%d%H%M%S%f", errors="coerce")
        df = df.dropna(subset=["datetime"])
        df.set_index("datetime", inplace=True)
        df.sort_index(inplace=True)

        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(subset=["close"], inplace=True)

        logger.info(f"[{symbol}] baostock分钟 {len(df)} 条  freq={bs_freq}")
        return df

    except Exception as e:
        logger.error(f"[{symbol}] 分钟数据获取失败(period={period}): {e}")
        return pd.DataFrame()


def get_minute_data_cached(symbol: str, period: str = "5", days: int = 5) -> pd.DataFrame:
    """
    分时数据，三级优先级：
    1. 腾讯今日分时（交易时段实时，非交易时段也可读昨日）
    2. baostock（约15:30后可用，数据完整但有时延）
    3. DB本地缓存（最后保底）

    对于 days>1 的请求，会把腾讯今日数据与 baostock 历史数据拼接。
    """
    from database import db as _db

    period_int = int(_BS_FREQ_MAP.get(str(period), period))
    today_str  = datetime.now().strftime("%Y-%m-%d")

    # ── 1. 腾讯今日分时 ──────────────────────────────────────────────────
    df_today = pd.DataFrame()
    try:
        df_today = get_intraday_bars_tencent(symbol, period=period_int)
    except Exception as e:
        logger.debug(f"[{symbol}] 腾讯分时获取失败: {e}")

    # ── 2. baostock 历史分钟（最近 days 天）────────────────────────────
    df_bs = pd.DataFrame()
    try:
        df_bs = get_minute_data(symbol, period=period, days=days)
    except Exception:
        pass

    # ── 合并：根据数据可用性动态决定今日数据来源 ────────────────────────
    today_date = datetime.now().date()
    df_bs_today = df_bs[df_bs.index.date == today_date] if not df_bs.empty else pd.DataFrame()
    df_bs_hist  = df_bs[df_bs.index.date <  today_date] if not df_bs.empty else pd.DataFrame()

    # 腾讯分时：只有返回多根bar才算"真实分时"，单根合成bar不算
    tencent_has_real_intraday = not df_today.empty and len(df_today) > 1

    df_live = pd.DataFrame()

    if tencent_has_real_intraday:
        # 腾讯有多根真实今日分时 → 用腾讯今日 + baostock历史
        df_live = pd.concat([df_bs_hist, df_today]).sort_index() if not df_bs_hist.empty else df_today
        logger.info(f"[{symbol}] 腾讯分时今日{len(df_today)}根 + baostock历史{len(df_bs_hist)}根")

    elif not df_bs_today.empty and len(df_bs_today) >= 5:
        # baostock已有今日完整分时（约15:30后）→ 直接使用全部baostock数据，不拼合成bar
        df_live = df_bs
        logger.info(f"[{symbol}] baostock含今日{len(df_bs_today)}根 + 历史{len(df_bs_hist)}根")

    elif not df_today.empty:
        # 只有合成单根bar（交易时段保底）→ 拼在历史末尾
        df_live = pd.concat([df_bs_hist, df_today]).sort_index() if not df_bs_hist.empty else df_today
        logger.info(f"[{symbol}] 合成今日bar + baostock历史{len(df_bs_hist)}根")

    elif not df_bs_hist.empty:
        df_live = df_bs_hist
        logger.info(f"[{symbol}] 无今日分时数据，显示最近历史 {len(df_live)} 根")

    # ── 写回缓存 ─────────────────────────────────────────────────────────
    if not df_live.empty:
        rows = [{
            "dt":     str(idx),
            "open":   float(row.get("open",   0) or 0),
            "high":   float(row.get("high",   0) or 0),
            "low":    float(row.get("low",    0) or 0),
            "close":  float(row.get("close",  0) or 0),
            "volume": float(row.get("volume", 0) or 0),
            "amount": 0.0,
        } for idx, row in df_live.iterrows()]
        _db.upsert_klines_min(symbol, rows, period)
        return df_live

    # ── 3. 降级读本地缓存 ─────────────────────────────────────────────
    cached = _db.get_klines_min(symbol, period)
    if not cached:
        return pd.DataFrame()

    df = pd.DataFrame(cached)
    df["dt"] = pd.to_datetime(df["dt"])
    df.set_index("dt", inplace=True)
    df.sort_index(inplace=True)
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["close"], inplace=True)
    logger.info(f"[{symbol}] 分时本地缓存 {len(df)} 条 period={period}")
    return df


# ── 周线（兼容旧调用）─────────────────────────────────────────────────────

def get_weekly_data(symbol: str, weeks: int = 104) -> pd.DataFrame:
    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(weeks=weeks)
    return get_historical_data(
        symbol,
        start_date=start_dt.strftime("%Y%m%d"),
        end_date=end_dt.strftime("%Y%m%d"),
        frequency="w",
    )
