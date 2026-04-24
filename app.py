"""
量化交易 Agent  ─  Web 应用
启动：python app.py
访问：http://localhost:8889
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

# ── 编码修复 ──────────────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── 日志 ──────────────────────────────────────────────────────────────────
from utils.logger import setup_logging
setup_logging()
logger = logging.getLogger("app")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

import config
from database import db
from trading.engine import TradingEngine

# ── 初始化用户数据库 ──────────────────────────────────────────────────────────
from backend.database import init_db
init_db()

app = FastAPI(title="量化交易 Agent", version="4.0")

# ── CORS（允许前端跨域，含 Vercel 域名）────────────────────────────────────────
_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "https://*.vercel.app",
]
import os as _os
_extra = _os.getenv("CORS_ORIGINS", "")
if _extra:
    _ALLOWED_ORIGINS.extend(_extra.split(","))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册新路由 ────────────────────────────────────────────────────────────────
from backend.routers.auth_router import router as auth_router
from backend.routers.users_router import router as users_router
from backend.routers.stocks_router import router as stocks_router
from backend.routers.portfolio_router import router as portfolio_router

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(stocks_router)
app.include_router(portfolio_router)


@app.on_event("startup")
def _on_startup():
    _load_sector_cache()

# ── WebSocket 连接池 ───────────────────────────────────────────────────────
_ws_clients: List[WebSocket] = []


async def _broadcast(data: dict):
    msg = json.dumps(data, ensure_ascii=False)
    dead = []
    for ws in list(_ws_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


def _sync_push(data: dict):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast(data), loop)
    except Exception:
        pass


# ── 全局交易引擎 ──────────────────────────────────────────────────────────
_engine: Optional[TradingEngine] = None


def _get_engine() -> TradingEngine:
    global _engine
    if _engine is None:
        symbols = db.get_symbols() or list(config.DEFAULT_SYMBOLS)
        _engine = TradingEngine(
            symbols=symbols,
            mode="paper",
            interval=60,
            push_callback=_sync_push,
        )
    return _engine


# ── 静态文件 ──────────────────────────────────────────────────────────────
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ══════════════════════════════════════════════════════════════════════════
# REST API
# ══════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def index():
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>static/index.html not found</h1>")


@app.get("/api/health")
def api_health():
    return {"ok": True}


@app.get("/api/status")
def api_status():
    eng = _get_engine()
    return eng.get_status()


@app.get("/api/signals")
def api_signals():
    eng = _get_engine()
    result = []
    for sym, analysis in eng.latest_signals.items():
        if not analysis:
            continue
        d   = analysis.get("decision", {})
        ind = analysis.get("indicators", {})
        result.append({
            "symbol":          sym,
            "name":            analysis.get("name", sym),
            "price":           ind.get("price", 0),
            "rsi":             ind.get("rsi", 0),
            "vol_ratio":       ind.get("vol_ratio", 0),
            "action":          d.get("action", "HOLD"),
            "confidence":      d.get("confidence", 0),
            "signal_strength": d.get("signal_strength", "WEAK"),
            "risk_level":      d.get("risk_level", "HIGH"),
            "reason":          d.get("reason", ""),
            "sentiment":       analysis.get("sentiment", {}).get("label", "neutral"),
            "timestamp":       analysis.get("timestamp", ""),
        })
    return result


# ── 扫描（手动触发）────────────────────────────────────────────────────────

@app.post("/api/engine/scan")
def api_engine_scan():
    eng = _get_engine()
    results = eng.run_once()
    return {"scanned": len(results), "signals": api_signals()}


# ── 标的管理 ──────────────────────────────────────────────────────────────

class SymbolReq(BaseModel):
    symbol: str


@app.post("/api/symbols/add")
def api_add_symbol(req: SymbolReq):
    eng = _get_engine()
    sym = req.symbol.strip().zfill(6)
    eng.add_symbol(sym)
    return {"symbols": eng.symbols}


@app.post("/api/symbols/remove")
def api_remove_symbol(req: SymbolReq):
    eng = _get_engine()
    eng.remove_symbol(req.symbol)
    return {"symbols": eng.symbols}


@app.get("/api/symbols")
def api_symbols():
    eng = _get_engine()
    named = db.get_symbols_with_names()
    name_map = {r["symbol"]: r["name"] for r in named}
    result = []
    for sym in eng.symbols:
        name = name_map.get(sym, sym)
        if not name or name == sym:
            try:
                from data.market_data import get_stock_name
                name = get_stock_name(sym)
            except Exception:
                name = sym
        result.append({"symbol": sym, "name": name})
    return {"symbols": eng.symbols, "named": result}


# ── 收藏股票 ──────────────────────────────────────────────────────────────

@app.get("/api/favorites")
def api_get_favorites():
    favs = db.get_favorites()
    result = []
    for f in favs:
        name = f["name"]
        if not name or name == f["symbol"]:
            try:
                from data.market_data import get_stock_name
                name = get_stock_name(f["symbol"])
            except Exception:
                name = f["symbol"]
        result.append({"symbol": f["symbol"], "name": name, "starred": True})
    return result


@app.post("/api/favorites/{symbol}")
def api_add_favorite(symbol: str, req: SymbolReq = None):
    sym = symbol.strip().zfill(6)
    name = None
    try:
        from data.market_data import get_stock_name
        name = get_stock_name(sym)
    except Exception:
        pass
    db.add_favorite(sym, name)
    return {"status": "added", "symbol": sym}


@app.delete("/api/favorites/{symbol}")
def api_remove_favorite(symbol: str):
    db.remove_favorite(symbol)
    return {"status": "removed", "symbol": symbol}


@app.get("/api/favorites/{symbol}/check")
def api_check_favorite(symbol: str):
    return {"symbol": symbol, "starred": db.is_favorite(symbol)}


# ── 实时行情（轻量，前端价格刷新专用）────────────────────────────────────

@app.get("/api/quote/{symbol}")
def api_quote(symbol: str):
    """
    轻量实时行情（腾讯→新浪→baostock历史）
    前端价格刷新专用，任何情况下都返回最后已知价格
    """
    from data.market_data import get_realtime_quote
    q = get_realtime_quote(symbol)
    if not q or q.get("price", 0) <= 0:
        raise HTTPException(status_code=503, detail=f"暂无 {symbol} 行情数据")
    return q


# ── 分析 ──────────────────────────────────────────────────────────────────

class AnalyzeReq(BaseModel):
    holding: str = ""    # 持仓情况，如"持有500股，成本12.5元"或"空仓"
    capital: str = ""    # 可用资金，如"5万"
    note:    str = ""    # 备注/问题，如"今天涨停，是否追高？"


@app.get("/api/analyze/{symbol}")
def api_analyze_get(symbol: str):
    """快速分析（不带用户上下文）"""
    return _do_analyze(symbol, None)


@app.post("/api/analyze/{symbol}")
def api_analyze_post(symbol: str, req: AnalyzeReq):
    """带用户上下文的AI分析"""
    user_context = {
        "holding": req.holding,
        "capital": req.capital,
        "note":    req.note,
    }
    return _do_analyze(symbol, user_context)


def _do_analyze(symbol: str, user_context: dict) -> dict:
    eng = _get_engine()
    analysis = eng.analyze_symbol(symbol, user_context=user_context)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"无法获取 {symbol} 数据")
    eng.latest_signals[symbol] = analysis
    d    = analysis.get("decision", {})
    ind  = analysis.get("indicators", {})
    name = analysis.get("name", symbol)
    sent = analysis.get("sentiment", {}).get("label", "neutral")

    # 持久化每次AI分析结果
    try:
        db.insert_analysis(symbol, name, d, ind, sent)
    except Exception as e:
        logger.warning(f"[分析历史] 写入失败 {symbol}: {e}")

    return {
        "symbol":           symbol,
        "name":             name,
        "indicators":       ind,
        "sentiment":        analysis.get("sentiment", {}),
        "intraday_summary": analysis.get("intraday_summary", {}),
        "action":           d.get("action", "HOLD"),
        "confidence":       d.get("confidence", 0),
        "signal_strength":  d.get("signal_strength", "WEAK"),
        "risk_level":       d.get("risk_level", "HIGH"),
        "reason":           d.get("reason", ""),
        "stop_loss":        d.get("stop_loss"),
        "take_profit":      d.get("take_profit"),
        "stop_loss_pct":    d.get("stop_loss_pct"),
        "take_profit_pct":  d.get("take_profit_pct"),
        "position_advice":  d.get("position_advice", ""),
        "is_realtime":      analysis.get("is_realtime", False),
        "data_date":        analysis.get("data_date", ""),
        "timestamp":        analysis.get("timestamp", ""),
    }


# ── 股票分析历史 ─────────────────────────────────────────────────────────

@app.get("/api/analysis/{symbol}/history")
def api_analysis_history(symbol: str, limit: int = 50):
    sym = symbol.strip().zfill(6)
    rows = db.get_analysis_history(sym, limit=limit)
    stats = db.get_analysis_stats(sym)
    return {"symbol": sym, "history": rows, "stats": stats}


@app.get("/api/analysis/recent")
def api_analysis_recent(limit: int = 100):
    """返回最近所有股票的分析记录（跨股票）"""
    with db._conn() as con:
        rows = con.execute(
            """SELECT id, timestamp, date, symbol, name, action, confidence,
                      signal_strength, risk_level, reason, price, rsi,
                      ma_arrangement, vol_ratio, sentiment
               FROM stock_analysis_history
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── 板块龙头扫描 ─────────────────────────────────────────────────────────

_SECTOR_CACHE_FILE = Path("data/sector_cache.json")
_sector_cache: dict = {"signals": [], "hot_sectors": [], "scanned_at": ""}


def _load_sector_cache():
    """启动时从文件恢复上次扫描结果"""
    global _sector_cache
    try:
        if _SECTOR_CACHE_FILE.exists():
            _sector_cache = json.loads(_SECTOR_CACHE_FILE.read_text(encoding="utf-8"))
            logger.info(f"[板块缓存] 已恢复 {len(_sector_cache.get('signals', []))} 条记录"
                        f"（{_sector_cache.get('scanned_at', '')}）")
    except Exception as e:
        logger.warning(f"[板块缓存] 读取失败: {e}")


def _save_sector_cache():
    """将当前缓存写入文件"""
    try:
        _SECTOR_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SECTOR_CACHE_FILE.write_text(
            json.dumps(_sector_cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"[板块缓存] 写入失败: {e}")


def _build_sector_out(r: dict) -> dict:
    d   = r.get("decision", {})
    ind = r.get("indicators", {})
    return {
        "symbol":          r.get("symbol", ""),
        "name":            r.get("name", ""),
        "sector":          r.get("sector", ""),
        "price":           ind.get("price", 0),
        "rsi":             ind.get("rsi", 0),
        "vol_ratio":       ind.get("vol_ratio", 0),
        "action":          d.get("action", "HOLD"),
        "confidence":      d.get("confidence", 0),
        "signal_strength": d.get("signal_strength", "WEAK"),
        "risk_level":      d.get("risk_level", "HIGH"),
        "reason":          d.get("reason", ""),
        "stop_loss":       d.get("stop_loss"),
        "take_profit":     d.get("take_profit"),
        "stop_loss_pct":   d.get("stop_loss_pct"),
        "take_profit_pct": d.get("take_profit_pct"),
        "position_advice": d.get("position_advice", ""),
        "sentiment":       r.get("sentiment", {}).get("label", "neutral"),
        "timestamp":       r.get("timestamp", ""),
    }


@app.post("/api/sector/scan")
def api_sector_scan():
    """扫描板块龙头股（价格<=50元），AI分析，结果持久化缓存"""
    global _sector_cache
    from trading.sector_leaders import scan_sector_leaders, get_hot_sectors, SECTOR_LEADERS
    eng = _get_engine()
    results = scan_sector_leaders(eng, max_price=50.0)

    try:
        from notify.email_notify import send_signal_email
        send_signal_email(results, source="板块龙头扫描")
    except Exception as e:
        logger.warning(f"板块通知失败: {e}")

    out         = [_build_sector_out(r) for r in results]
    hot_sectors = get_hot_sectors(results)
    scanned_at  = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 持久化缓存
    _sector_cache = {"signals": out, "hot_sectors": hot_sectors, "scanned_at": scanned_at}
    _save_sector_cache()

    return {
        "scanned":     len(results),
        "signals":     out,
        "hot_sectors": hot_sectors,
        "sectors":     list(SECTOR_LEADERS.keys()),
        "scanned_at":  scanned_at,
    }


@app.get("/api/sector/results")
def api_sector_results():
    """返回上次扫描的缓存结果（不触发新扫描）"""
    return {
        "signals":     _sector_cache.get("signals", []),
        "hot_sectors": _sector_cache.get("hot_sectors", []),
        "scanned_at":  _sector_cache.get("scanned_at", ""),
        "count":       len(_sector_cache.get("signals", [])),
    }


@app.get("/api/sector/list")
def api_sector_list():
    """返回板块列表和对应股票"""
    from trading.sector_leaders import SECTOR_LEADERS, ALL_LEADERS
    return {"sectors": SECTOR_LEADERS, "total": len(ALL_LEADERS)}


# ── 持仓管理 ──────────────────────────────────────────────────────────────

class HoldingReq(BaseModel):
    symbol:   str
    name:     str = ""
    shares:   float
    avg_cost: float
    note:     str = ""

@app.get("/api/holdings")
def api_get_holdings():
    rows = db.get_holdings()
    # 补充现价和浮盈
    result = []
    for r in rows:
        item = dict(r)
        try:
            from data.market_data import get_realtime_quote
            q = get_realtime_quote(r["symbol"])
            item["price"]    = q.get("price", 0)
            item["prev_close"] = q.get("prev_close", 0)
        except Exception:
            item["price"] = 0
        cost = r["avg_cost"] or 0
        price = item.get("price", 0)
        item["pnl_pct"] = round((price - cost) / cost * 100, 2) if cost > 0 and price > 0 else 0
        item["pnl_amt"] = round((price - cost) * r["shares"], 2) if cost > 0 and price > 0 else 0
        result.append(item)
    return result

@app.post("/api/holdings")
def api_upsert_holding(req: HoldingReq):
    sym = req.symbol.strip().zfill(6)
    name = req.name
    if not name:
        try:
            from data.market_data import get_stock_name
            name = get_stock_name(sym)
        except Exception:
            name = sym
    db.upsert_holding(sym, name, req.shares, req.avg_cost, req.note)
    return {"status": "ok", "symbol": sym}

@app.delete("/api/holdings/{symbol}")
def api_delete_holding(symbol: str):
    db.remove_holding(symbol)
    return {"status": "ok"}

@app.post("/api/holdings/scan")
def api_holdings_scan():
    """对所有持仓进行AI分析（告知AI持仓上下文），返回SELL/ADD信号"""
    rows = db.get_holdings()
    if not rows:
        return {"scanned": 0, "signals": []}
    eng = _get_engine()
    results = []
    for r in rows:
        sym  = r["symbol"]
        shares   = r["shares"]
        avg_cost = r["avg_cost"]
        note     = r.get("note", "")
        user_context = {
            "holding": f"持有 {shares:.0f} 股，均价 {avg_cost:.3f} 元",
            "capital": "",
            "note":    note or "请结合技术面给出加仓或减仓/清仓建议",
        }
        try:
            analysis = eng.analyze_symbol(sym, user_context=user_context)
            if analysis:
                analysis["holding_shares"] = shares
                analysis["holding_cost"]   = avg_cost
                eng.latest_signals[sym] = analysis
                results.append(analysis)
        except Exception as e:
            logger.error(f"[持仓扫描] {sym} 异常: {e}")

    # 推送邮件：BUY(加仓)正常频率，SELL红色一次性
    try:
        from notify.email_notify import send_signal_email, send_holding_sell_email
        buy_sigs  = [r for r in results if r.get("decision", {}).get("action") == "BUY"]
        sell_sigs = [r for r in results if r.get("decision", {}).get("action") == "SELL"]
        if buy_sigs:
            send_signal_email(buy_sigs, source="持仓加仓信号")
        if sell_sigs:
            send_holding_sell_email(sell_sigs)
    except Exception as e:
        logger.warning(f"[持仓通知] {e}")

    out = []
    for r in results:
        d   = r.get("decision", {})
        ind = r.get("indicators", {})
        out.append({
            "symbol":          r.get("symbol", ""),
            "name":            r.get("name", ""),
            "price":           ind.get("price", 0),
            "action":          d.get("action", "HOLD"),
            "confidence":      d.get("confidence", 0),
            "signal_strength": d.get("signal_strength", "WEAK"),
            "risk_level":      d.get("risk_level", "HIGH"),
            "reason":          d.get("reason", ""),
            "stop_loss":       d.get("stop_loss"),
            "take_profit":     d.get("take_profit"),
            "stop_loss_pct":   d.get("stop_loss_pct"),
            "take_profit_pct": d.get("take_profit_pct"),
            "position_advice": d.get("position_advice", ""),
            "holding_shares":  r.get("holding_shares", 0),
            "holding_cost":    r.get("holding_cost", 0),
            "timestamp":       r.get("timestamp", ""),
        })
    return {"scanned": len(results), "signals": out}


@app.post("/api/daily/summary")
def api_daily_summary():
    """手动触发当日概要邮件（收盘后调用）"""
    from notify.email_notify import send_daily_summary, _daily_summary_sent_date
    import notify.email_notify as _ne
    eng = _get_engine()
    portfolio = None
    try:
        portfolio = eng.broker.get_balance()
    except Exception:
        pass
    # 强制发送（忽略当日已发检查）
    _ne._daily_summary_sent_date = None
    send_daily_summary(eng.latest_signals, portfolio, source="手动触发")
    return {"status": "ok", "signals_count": len(eng.latest_signals)}


# ── 通知设置 ──────────────────────────────────────────────────────────────

class EmailConfigReq(BaseModel):
    smtp_host:    str
    smtp_port:    int
    sender:       str
    sender_pass:  str
    receiver:     str
    min_confidence: float = 0.60

@app.post("/api/notify/config")
def api_notify_config(req: EmailConfigReq):
    """运行时更新邮件配置（重启失效；持久化请写 .env 文件）"""
    config.EMAIL_ENABLED       = True
    config.EMAIL_SMTP_HOST     = req.smtp_host
    config.EMAIL_SMTP_PORT     = req.smtp_port
    config.EMAIL_SENDER        = req.sender
    config.EMAIL_SENDER_PASS   = req.sender_pass
    config.EMAIL_RECEIVER      = req.receiver
    config.NOTIFY_MIN_CONFIDENCE = req.min_confidence
    return {"status": "ok", "enabled": True}

@app.post("/api/notify/test")
def api_notify_test():
    """发送 BUY 信号测试邮件"""
    from notify.email_notify import send_test_email
    ok, msg = send_test_email()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@app.post("/api/notify/test/sell")
def api_notify_test_sell():
    """发送持仓 SELL 信号测试邮件"""
    from notify.email_notify import send_test_sell_email
    ok, msg = send_test_sell_email()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@app.post("/api/notify/test/ai_fail")
def api_notify_test_ai_fail():
    """发送 AI 接口失败告警测试邮件"""
    from notify.email_notify import send_test_ai_fail_email
    ok, msg = send_test_ai_fail_email()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@app.post("/api/notify/test/daily")
def api_notify_test_daily():
    """发送每日收盘概要测试邮件"""
    from notify.email_notify import send_test_daily_email
    ok, msg = send_test_daily_email()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}

@app.get("/api/notify/status")
def api_notify_status():
    return {
        "enabled":          getattr(config, "EMAIL_ENABLED", False),
        "smtp_host":        getattr(config, "EMAIL_SMTP_HOST", ""),
        "smtp_port":        getattr(config, "EMAIL_SMTP_PORT", 465),
        "sender":           getattr(config, "EMAIL_SENDER", ""),
        "receiver":         getattr(config, "EMAIL_RECEIVER", ""),
        "min_confidence":   getattr(config, "NOTIFY_MIN_CONFIDENCE", 0.60),
        "cooldown_minutes": getattr(config, "NOTIFY_COOLDOWN_MINUTES", 60),
    }


# ── 回测 ──────────────────────────────────────────────────────────────────

class BacktestReq(BaseModel):
    symbol:       str
    start_date:   str   = None
    end_date:     str   = None
    initial_cash: float = None


@app.post("/api/backtest")
def api_backtest(req: BacktestReq):
    from backtest.strategy import run_backtest
    cash = req.initial_cash if req.initial_cash and req.initial_cash > 0 else config.INITIAL_CAPITAL
    result = run_backtest(
        symbol=req.symbol,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_cash=cash,
    )
    return result


# ── 行情数据（日线 / 周线）────────────────────────────────────────────────

@app.get("/api/kline/{symbol}")
def api_kline(symbol: str, days: int = 120, period: str = "daily", refresh: bool = False):
    from indicators.technical import add_indicators
    from data.market_data import get_historical_data_cached

    freq = "w" if period == "weekly" else "d"
    end_dt   = datetime.now().strftime("%Y%m%d")
    if freq == "w":
        start_dt = (datetime.now() - timedelta(days=365 * 2)).strftime("%Y%m%d")
    else:
        start_dt = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y%m%d")

    df = get_historical_data_cached(symbol, start_dt, end_dt, frequency=freq, force_refresh=refresh)

    if df.empty:
        raise HTTPException(status_code=404, detail="无数据")

    df = add_indicators(df)
    df = df.tail(days)

    try:
        from data.market_data import get_stock_name
        name = db.get_symbol_name(symbol) or get_stock_name(symbol)
        if name and name != symbol:
            db.update_symbol_name(symbol, name)
    except Exception:
        name = symbol

    last_date = str(df.index[-1].date()) if not df.empty else ""
    return {
        "symbol":    symbol,
        "name":      name,
        "last_date": last_date,
        "dates":     [str(d.date()) for d in df.index],
        "open":      df["open"].round(3).tolist(),
        "high":      df["high"].round(3).tolist(),
        "low":       df["low"].round(3).tolist(),
        "close":     df["close"].round(3).tolist(),
        "volume":    df["volume"].tolist(),
        "ma5":       df["ma5"].round(3).fillna(0).tolist(),
        "ma20":      df["ma20"].round(3).fillna(0).tolist(),
        "ma60":      df["ma60"].round(3).fillna(0).tolist(),
        "macd_dif":  df["macd_dif"].round(4).fillna(0).tolist(),
        "macd_dea":  df["macd_dea"].round(4).fillna(0).tolist(),
        "macd_hist": df["macd_hist"].round(4).fillna(0).tolist(),
        "rsi":       df["rsi"].round(2).fillna(50).tolist(),
    }


# ── 分钟级行情 ────────────────────────────────────────────────────────────

@app.get("/api/kline/{symbol}/minute")
def api_kline_minute(symbol: str, period: str = "5", days: int = 5):
    """
    分钟级 K 线（腾讯今日分时 + baostock 历史，交易时段实时）
    period: 1 / 5 / 15 / 30 / 60
    """
    import pandas as pd
    from data.market_data import get_minute_data_cached, _in_trading_hours, get_realtime_quote

    df = get_minute_data_cached(symbol, period=period, days=days)

    today_str = datetime.now().strftime("%Y-%m-%d")

    # 交易时段且无今日数据 → 用实时行情补一根当日bar（保证图上有今日价格）
    if _in_trading_hours():
        has_today = not df.empty and str(df.index[-1].date()) == today_str
        if not has_today:
            try:
                q = get_realtime_quote(symbol)
                if q and q.get("price", 0) > 0 and q.get("open", 0) > 0:
                    period_int = int(period) if period.isdigit() else 5
                    now = datetime.now().replace(second=0, microsecond=0)
                    aligned = now.replace(minute=(now.minute // period_int) * period_int)
                    bar = pd.DataFrame([{
                        "open":   q["open"],
                        "high":   q.get("high", q["price"]),
                        "low":    q.get("low",  q["price"]),
                        "close":  q["price"],
                        "volume": q.get("volume", 0),
                    }], index=pd.DatetimeIndex([aligned]))
                    df = pd.concat([df, bar]).sort_index() if not df.empty else bar
                    logger.info(f"[{symbol}] 实时行情补今日bar: {aligned}")
            except Exception as e:
                logger.debug(f"[{symbol}] 补今日bar失败: {e}")

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail="暂无分时数据（交易时段外且本地无缓存，请在交易时段内加载一次）"
        )

    times     = [str(dt) for dt in df.index]
    last_time = times[-1] if times else ""
    is_today  = last_time.startswith(today_str) if last_time else False
    return {
        "times":     times,
        "last_time": last_time,
        "is_today":  is_today,
        "open":      df["open"].round(3).tolist(),
        "high":      df["high"].round(3).tolist(),
        "low":       df["low"].round(3).tolist(),
        "close":     df["close"].round(3).tolist(),
        "volume":    df["volume"].round(0).tolist() if "volume" in df.columns else [],
    }


# ── WebSocket ─────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        eng = _get_engine()
        await ws.send_text(json.dumps({
            "type": "init",
            **eng.get_status(),
        }, ensure_ascii=False))
        while True:
            data = await asyncio.wait_for(ws.receive_text(), timeout=30)
            if data == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


# ══════════════════════════════════════════════════════════════════════════
# 启动入口
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    existing = db.get_symbols()
    if not existing:
        for sym in config.DEFAULT_SYMBOLS:
            db.add_symbol(sym)

    print("=" * 55)
    print("  量化交易 Agent  Web 应用  v3.0")
    print(f"  访问地址: http://127.0.0.1:8889")
    print(f"  API 文档: http://127.0.0.1:8889/docs")
    print("=" * 55)

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8889,
        reload=False,
        log_level="info",
    )
