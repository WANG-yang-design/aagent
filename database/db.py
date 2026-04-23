"""
SQLite 持久化层
表：trades / portfolio_snapshots / watched_symbols / favorites
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

DB_PATH = Path("database/trading.db")
DB_PATH.parent.mkdir(exist_ok=True)

_DDL = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    action          TEXT    NOT NULL,
    price           REAL    NOT NULL,
    shares          INTEGER NOT NULL,
    amount          REAL    NOT NULL,
    pnl             REAL,
    pnl_ratio       REAL,
    confidence      REAL,
    signal_strength TEXT,
    risk_level      TEXT,
    reason          TEXT,
    mode            TEXT    NOT NULL DEFAULT 'paper'
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    total_value     REAL    NOT NULL,
    cash            REAL    NOT NULL,
    positions_value REAL    NOT NULL,
    daily_pnl       REAL    DEFAULT 0,
    total_pnl       REAL    DEFAULT 0,
    total_return    REAL    DEFAULT 0,
    mode            TEXT    DEFAULT 'paper'
);

CREATE TABLE IF NOT EXISTS watched_symbols (
    symbol          TEXT    PRIMARY KEY,
    name            TEXT,
    added_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS favorites (
    symbol          TEXT    PRIMARY KEY,
    name            TEXT,
    added_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS klines (
    symbol      TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    period      TEXT    NOT NULL DEFAULT 'd',
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    amount      REAL,
    pct_change  REAL,
    PRIMARY KEY (symbol, date, period)
);

CREATE TABLE IF NOT EXISTS klines_min (
    symbol      TEXT    NOT NULL,
    dt          TEXT    NOT NULL,
    period      TEXT    NOT NULL DEFAULT '5',
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    amount      REAL,
    PRIMARY KEY (symbol, dt, period)
);

CREATE TABLE IF NOT EXISTS holdings (
    symbol      TEXT    PRIMARY KEY,
    name        TEXT,
    shares      REAL    NOT NULL DEFAULT 0,
    avg_cost    REAL    NOT NULL DEFAULT 0,
    note        TEXT    DEFAULT '',
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_analysis_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    name            TEXT,
    action          TEXT,
    confidence      REAL,
    signal_strength TEXT,
    risk_level      TEXT,
    reason          TEXT,
    stop_loss       REAL,
    take_profit     REAL,
    stop_loss_pct   REAL,
    take_profit_pct REAL,
    position_advice TEXT,
    price           REAL,
    rsi             REAL,
    ma_arrangement  TEXT,
    macd_cross      TEXT,
    vol_ratio       REAL,
    sentiment       TEXT,
    indicators_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_date    ON trades(date);
CREATE INDEX IF NOT EXISTS idx_trades_symbol  ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_mode    ON trades(mode);
CREATE INDEX IF NOT EXISTS idx_snap_date      ON portfolio_snapshots(date);
CREATE INDEX IF NOT EXISTS idx_klines_sym     ON klines(symbol, period, date);
CREATE INDEX IF NOT EXISTS idx_klines_min_sym ON klines_min(symbol, period, dt);
CREATE INDEX IF NOT EXISTS idx_analysis_sym   ON stock_analysis_history(symbol, timestamp);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _migrate():
    """旧库结构升级（幂等）"""
    with _conn() as con:
        try:
            con.execute("""CREATE TABLE IF NOT EXISTS stock_analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL, date TEXT NOT NULL,
                symbol TEXT NOT NULL, name TEXT,
                action TEXT, confidence REAL, signal_strength TEXT, risk_level TEXT,
                reason TEXT, stop_loss REAL, take_profit REAL,
                stop_loss_pct REAL, take_profit_pct REAL, position_advice TEXT,
                price REAL, rsi REAL, ma_arrangement TEXT, macd_cross TEXT,
                vol_ratio REAL, sentiment TEXT, indicators_json TEXT)""")
        except Exception:
            pass
        try:
            con.execute("CREATE INDEX IF NOT EXISTS idx_analysis_sym ON stock_analysis_history(symbol, timestamp)")
        except Exception:
            pass
        try:
            con.execute("ALTER TABLE portfolio_snapshots ADD COLUMN mode TEXT DEFAULT 'paper'")
        except Exception:
            pass
        try:
            con.execute("CREATE INDEX IF NOT EXISTS idx_snap_mode ON portfolio_snapshots(mode)")
        except Exception:
            pass
        # 确保 klines / klines_min 表已建（旧库）
        try:
            con.execute("""CREATE TABLE IF NOT EXISTS klines (
                symbol TEXT NOT NULL, date TEXT NOT NULL, period TEXT NOT NULL DEFAULT 'd',
                open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL, pct_change REAL,
                PRIMARY KEY (symbol, date, period))""")
        except Exception:
            pass
        try:
            con.execute("""CREATE TABLE IF NOT EXISTS klines_min (
                symbol TEXT NOT NULL, dt TEXT NOT NULL, period TEXT NOT NULL DEFAULT '5',
                open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL,
                PRIMARY KEY (symbol, dt, period))""")
        except Exception:
            pass
        try:
            con.execute("""CREATE TABLE IF NOT EXISTS holdings (
                symbol TEXT PRIMARY KEY, name TEXT, shares REAL NOT NULL DEFAULT 0,
                avg_cost REAL NOT NULL DEFAULT 0, note TEXT DEFAULT '', updated_at TEXT NOT NULL)""")
        except Exception:
            pass


def init_db():
    with _conn() as con:
        con.executescript(_DDL)
    _migrate()


# ── trades ────────────────────────────────────────────────────────────────

def insert_trade(
    symbol: str,
    action: str,
    price: float,
    shares: int,
    pnl: float = None,
    pnl_ratio: float = None,
    confidence: float = None,
    signal_strength: str = None,
    risk_level: str = None,
    reason: str = None,
    mode: str = "paper",
) -> int:
    now = datetime.now()
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO trades
               (timestamp, date, symbol, action, price, shares, amount,
                pnl, pnl_ratio, confidence, signal_strength, risk_level, reason, mode)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                now.isoformat(), now.strftime("%Y-%m-%d"),
                symbol, action, price, shares, round(price * shares, 2),
                pnl, pnl_ratio, confidence, signal_strength, risk_level, reason, mode,
            ),
        )
        return cur.lastrowid


def get_trades(
    date: str = None,
    symbol: str = None,
    mode: str = None,
    limit: int = 100,
    offset: int = 0,
) -> List[dict]:
    clauses, params = [], []
    if date:   clauses.append("date = ?");   params.append(date)
    if symbol: clauses.append("symbol = ?"); params.append(symbol)
    if mode:   clauses.append("mode = ?");   params.append(mode)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM trades {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return [dict(r) for r in rows]


def get_trade_stats(date: str = None, mode: str = None) -> dict:
    d = date or datetime.now().strftime("%Y-%m-%d")
    extra = " AND mode = ?" if mode else ""
    params = [d] + ([mode] if mode else [])
    with _conn() as con:
        row = con.execute(
            f"""SELECT
                 COUNT(*) AS total,
                 SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS won,
                 SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS lost,
                 COALESCE(SUM(pnl), 0) AS total_pnl
               FROM trades
               WHERE date = ? AND action LIKE 'SELL%'{extra}""",
            params,
        ).fetchone()
    return dict(row) if row else {"total": 0, "won": 0, "lost": 0, "total_pnl": 0}


# ── portfolio snapshots ───────────────────────────────────────────────────

def insert_snapshot(
    total_value: float,
    cash: float,
    positions_value: float,
    daily_pnl: float = 0,
    total_pnl: float = 0,
    total_return: float = 0,
    mode: str = "paper",
):
    now = datetime.now()
    with _conn() as con:
        con.execute(
            """INSERT INTO portfolio_snapshots
               (timestamp, date, total_value, cash, positions_value,
                daily_pnl, total_pnl, total_return, mode)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                now.isoformat(), now.strftime("%Y-%m-%d"),
                total_value, cash, positions_value,
                daily_pnl, total_pnl, total_return, mode,
            ),
        )


def get_portfolio_history(days: int = 30, mode: str = None) -> List[dict]:
    clause = ("WHERE mode = ?" if mode else "")
    params = ([mode] if mode else [])
    with _conn() as con:
        rows = con.execute(
            f"""SELECT date, MAX(timestamp) AS ts,
                       total_value, cash, total_pnl, total_return, mode
               FROM portfolio_snapshots {clause}
               GROUP BY date
               ORDER BY date DESC
               LIMIT ?""",
            params + [days],
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))


# ── watched symbols ───────────────────────────────────────────────────────

def add_symbol(symbol: str, name: str = None):
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO watched_symbols (symbol, name, added_at) VALUES (?,?,?)",
            (symbol, name or symbol, datetime.now().isoformat()),
        )


def remove_symbol(symbol: str):
    with _conn() as con:
        con.execute("DELETE FROM watched_symbols WHERE symbol = ?", (symbol,))


def get_symbols() -> List[str]:
    with _conn() as con:
        rows = con.execute("SELECT symbol FROM watched_symbols ORDER BY added_at").fetchall()
    return [r["symbol"] for r in rows]


def get_symbols_with_names() -> List[dict]:
    """返回监控股票列表（带名称）"""
    with _conn() as con:
        rows = con.execute(
            "SELECT symbol, name FROM watched_symbols ORDER BY added_at"
        ).fetchall()
    return [dict(r) for r in rows]


def get_symbol_name(symbol: str) -> Optional[str]:
    """从 watched_symbols 或 favorites 表查股票名称"""
    with _conn() as con:
        row = con.execute(
            """SELECT name FROM watched_symbols WHERE symbol=?
               UNION SELECT name FROM favorites WHERE symbol=? LIMIT 1""",
            (symbol, symbol),
        ).fetchone()
    if row and row["name"] and row["name"] != symbol:
        return row["name"]
    return None


def update_symbol_name(symbol: str, name: str):
    """更新 watched_symbols 和 favorites 中的名称"""
    with _conn() as con:
        con.execute(
            "UPDATE watched_symbols SET name=? WHERE symbol=? AND (name IS NULL OR name=?)",
            (name, symbol, symbol),
        )
        con.execute(
            "UPDATE favorites SET name=? WHERE symbol=? AND (name IS NULL OR name=?)",
            (name, symbol, symbol),
        )


# ── favorites ─────────────────────────────────────────────────────────────

def add_favorite(symbol: str, name: str = None):
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO favorites (symbol, name, added_at) VALUES (?,?,?)",
            (symbol, name or symbol, datetime.now().isoformat()),
        )


def remove_favorite(symbol: str):
    with _conn() as con:
        con.execute("DELETE FROM favorites WHERE symbol = ?", (symbol,))


def get_favorites() -> List[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT symbol, name FROM favorites ORDER BY added_at"
        ).fetchall()
    return [dict(r) for r in rows]


def is_favorite(symbol: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM favorites WHERE symbol = ?", (symbol,)
        ).fetchone()
    return row is not None


# ── K线缓存（日线 / 周线）────────────────────────────────────────────────

def upsert_klines(symbol: str, rows: List[dict], period: str = "d"):
    """批量写入/更新日线或周线数据（幂等）"""
    if not rows:
        return
    with _conn() as con:
        con.executemany(
            """INSERT OR REPLACE INTO klines
               (symbol, date, period, open, high, low, close, volume, amount, pct_change)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    symbol,
                    r["date"],
                    period,
                    r.get("open"),
                    r.get("high"),
                    r.get("low"),
                    r.get("close"),
                    r.get("volume"),
                    r.get("amount"),
                    r.get("pct_change"),
                )
                for r in rows
            ],
        )


def get_klines(symbol: str, start_date: str, end_date: str, period: str = "d") -> List[dict]:
    """读取K线缓存（date 格式 YYYY-MM-DD）"""
    with _conn() as con:
        rows = con.execute(
            """SELECT date, open, high, low, close, volume, amount, pct_change
               FROM klines WHERE symbol=? AND period=? AND date>=? AND date<=?
               ORDER BY date""",
            (symbol, period, start_date, end_date),
        ).fetchall()
    return [dict(r) for r in rows]


def get_klines_last_date(symbol: str, period: str = "d") -> Optional[str]:
    """返回DB中该股票+周期最新的日期，无数据返回 None"""
    with _conn() as con:
        row = con.execute(
            "SELECT MAX(date) AS last FROM klines WHERE symbol=? AND period=?",
            (symbol, period),
        ).fetchone()
    return row["last"] if row and row["last"] else None


def count_klines(symbol: str, period: str = "d") -> int:
    """返回DB中该股票K线条数"""
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) AS cnt FROM klines WHERE symbol=? AND period=?",
            (symbol, period),
        ).fetchone()
    return row["cnt"] if row else 0


def delete_klines(symbol: str, period: str = "d"):
    """删除某只股票的全部K线缓存（用于强制重新全量下载）"""
    with _conn() as con:
        con.execute("DELETE FROM klines WHERE symbol=? AND period=?", (symbol, period))


# ── 分钟线缓存 ────────────────────────────────────────────────────────────

def upsert_klines_min(symbol: str, rows: List[dict], period: str = "5"):
    """批量写入分钟线（只保留最近 5 交易日，自动清理旧数据）"""
    if not rows:
        return
    with _conn() as con:
        con.executemany(
            """INSERT OR REPLACE INTO klines_min
               (symbol, dt, period, open, high, low, close, volume, amount)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [
                (
                    symbol,
                    r["dt"],
                    period,
                    r.get("open"),
                    r.get("high"),
                    r.get("low"),
                    r.get("close"),
                    r.get("volume"),
                    r.get("amount"),
                )
                for r in rows
            ],
        )
        # 只保留最近 5 个交易日
        con.execute(
            """DELETE FROM klines_min WHERE symbol=? AND period=?
               AND dt < (SELECT dt FROM klines_min WHERE symbol=? AND period=?
                         ORDER BY dt DESC LIMIT 1 OFFSET 1440)""",
            (symbol, period, symbol, period),
        )


def get_klines_min(symbol: str, period: str = "5", date_prefix: str = None) -> List[dict]:
    """读取分钟线缓存；date_prefix 如 '2024-04-16' 则只返回当天"""
    with _conn() as con:
        if date_prefix:
            rows = con.execute(
                """SELECT dt, open, high, low, close, volume, amount
                   FROM klines_min WHERE symbol=? AND period=? AND dt LIKE ?
                   ORDER BY dt""",
                (symbol, period, date_prefix + "%"),
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT dt, open, high, low, close, volume, amount
                   FROM klines_min WHERE symbol=? AND period=?
                   ORDER BY dt DESC LIMIT 1440""",
                (symbol, period),
            ).fetchall()
            rows = list(reversed(rows))
    return [dict(r) for r in rows]


def get_klines_min_last_dt(symbol: str, period: str = "5") -> Optional[str]:
    """返回分钟线最新的 dt"""
    with _conn() as con:
        row = con.execute(
            "SELECT MAX(dt) AS last FROM klines_min WHERE symbol=? AND period=?",
            (symbol, period),
        ).fetchone()
    return row["last"] if row and row["last"] else None


# ── holdings ──────────────────────────────────────────────────────────────

def upsert_holding(symbol: str, name: str, shares: float, avg_cost: float, note: str = ""):
    with _conn() as con:
        con.execute(
            """INSERT INTO holdings (symbol, name, shares, avg_cost, note, updated_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(symbol) DO UPDATE SET
                 name=excluded.name, shares=excluded.shares,
                 avg_cost=excluded.avg_cost, note=excluded.note,
                 updated_at=excluded.updated_at""",
            (symbol, name or symbol, shares, avg_cost, note or "", datetime.now().isoformat()),
        )


def remove_holding(symbol: str):
    with _conn() as con:
        con.execute("DELETE FROM holdings WHERE symbol=?", (symbol,))


def get_holdings() -> List[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT symbol, name, shares, avg_cost, note, updated_at FROM holdings ORDER BY updated_at"
        ).fetchall()
    return [dict(r) for r in rows]


# ── CSV 导出 ──────────────────────────────────────────────────────────────

def export_trades_csv(path: str, mode: str = None) -> int:
    """导出交易记录到 CSV，返回行数"""
    import csv
    trades = get_trades(mode=mode, limit=100000)
    if not trades:
        return 0
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=trades[0].keys())
        writer.writeheader()
        writer.writerows(trades)
    return len(trades)


# ── stock_analysis_history ────────────────────────────────────────────────

def insert_analysis(
    symbol: str,
    name: str,
    decision: dict,
    indicators: dict,
    sentiment: str = "",
) -> int:
    import json as _json
    now = datetime.now()
    ind = indicators or {}
    dec = decision or {}
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO stock_analysis_history
               (timestamp, date, symbol, name, action, confidence, signal_strength,
                risk_level, reason, stop_loss, take_profit, stop_loss_pct, take_profit_pct,
                position_advice, price, rsi, ma_arrangement, macd_cross, vol_ratio,
                sentiment, indicators_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                now.isoformat(), now.strftime("%Y-%m-%d"),
                symbol, name or symbol,
                dec.get("action"),
                dec.get("confidence"),
                dec.get("signal_strength"),
                dec.get("risk_level"),
                dec.get("reason"),
                dec.get("stop_loss"),
                dec.get("take_profit"),
                dec.get("stop_loss_pct"),
                dec.get("take_profit_pct"),
                dec.get("position_advice"),
                ind.get("price"),
                ind.get("rsi"),
                ind.get("ma_arrangement"),
                ind.get("macd_cross"),
                ind.get("vol_ratio"),
                sentiment,
                _json.dumps(ind, ensure_ascii=False),
            ),
        )
        return cur.lastrowid


def get_analysis_history(symbol: str, limit: int = 50) -> List[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT id, timestamp, date, symbol, name, action, confidence,
                      signal_strength, risk_level, reason, stop_loss, take_profit,
                      stop_loss_pct, take_profit_pct, position_advice,
                      price, rsi, ma_arrangement, macd_cross, vol_ratio, sentiment
               FROM stock_analysis_history
               WHERE symbol = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (symbol, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_analysis_stats(symbol: str) -> dict:
    with _conn() as con:
        row = con.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN action='BUY'  THEN 1 ELSE 0 END) AS buy_count,
                      SUM(CASE WHEN action='SELL' THEN 1 ELSE 0 END) AS sell_count,
                      SUM(CASE WHEN action='HOLD' THEN 1 ELSE 0 END) AS hold_count,
                      AVG(confidence) AS avg_confidence,
                      MAX(timestamp)  AS last_analyzed
               FROM stock_analysis_history WHERE symbol = ?""",
            (symbol,),
        ).fetchone()
    return dict(row) if row else {}


# 初始化
init_db()
