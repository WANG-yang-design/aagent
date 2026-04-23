import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import StockList

logger = logging.getLogger("stock_search")
_fetch_lock = threading.Lock()
_fetching = False


# ── 内置热门股票（兜底数据，baostock 未拉取时可用）────────────────────────────
_BUILTIN = [
    ("000001", "平安银行", "深主板"), ("000002", "万科A", "深主板"),
    ("000333", "美的集团", "深主板"), ("000651", "格力电器", "深主板"),
    ("000858", "五粮液", "深主板"), ("000895", "双汇发展", "深主板"),
    ("002415", "海康威视", "深主板"), ("300015", "爱尔眼科", "创业板"),
    ("300059", "东方财富", "创业板"), ("300122", "智飞生物", "创业板"),
    ("300124", "汇川技术", "创业板"), ("300750", "宁德时代", "创业板"),
    ("600000", "浦发银行", "沪主板"), ("600009", "上海机场", "沪主板"),
    ("600016", "民生银行", "沪主板"), ("600036", "招商银行", "沪主板"),
    ("600048", "保利发展", "沪主板"), ("600104", "上汽集团", "沪主板"),
    ("600276", "恒瑞医药", "沪主板"), ("600309", "万华化学", "沪主板"),
    ("600519", "贵州茅台", "沪主板"), ("600585", "海螺水泥", "沪主板"),
    ("600887", "伊利股份", "沪主板"), ("600900", "长江电力", "沪主板"),
    ("601012", "隆基绿能", "沪主板"), ("601166", "兴业银行", "沪主板"),
    ("601288", "农业银行", "沪主板"), ("601318", "中国平安", "沪主板"),
    ("601398", "工商银行", "沪主板"), ("601857", "中国石油", "沪主板"),
    ("603288", "海天味业", "沪主板"), ("688111", "金山办公", "科创板"),
    ("688599", "天合光能", "科创板"),
]


def _needs_update(db: Session) -> bool:
    count = db.query(StockList).count()
    if count < 50:
        return True
    latest = db.query(StockList).order_by(StockList.updated_at.desc()).first()
    if not latest:
        return True
    return datetime.utcnow() - latest.updated_at > timedelta(days=7)


def _seed_builtin(db: Session):
    now = datetime.utcnow()
    for code, name, market in _BUILTIN:
        if not db.query(StockList).filter(StockList.code == code).first():
            db.add(StockList(code=code, name=name, market=market, updated_at=now))
    db.commit()


def _fetch_from_baostock():
    global _fetching
    db = SessionLocal()
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != "0":
            logger.warning(f"[股票列表] baostock 登录失败: {lg.error_msg}")
            return
        rs = bs.query_stock_basic()
        stocks = []
        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()
            code_full = row[0]
            name = row[1]
            market = row[6] if len(row) > 6 else ""
            code = code_full.split(".")[-1] if "." in code_full else code_full
            if len(code) == 6 and code.isdigit():
                stocks.append((code, name, market))
        bs.logout()

        now = datetime.utcnow()
        for code, name, market in stocks:
            existing = db.query(StockList).filter(StockList.code == code).first()
            if existing:
                existing.name = name
                existing.market = market
                existing.updated_at = now
            else:
                db.add(StockList(code=code, name=name, market=market, updated_at=now))
        db.commit()
        logger.info(f"[股票列表] 已更新 {len(stocks)} 只股票")
    except Exception as e:
        logger.error(f"[股票列表] baostock 拉取失败: {e}")
        db.rollback()
    finally:
        db.close()
        _fetching = False


def ensure_stock_list(db: Session):
    global _fetching
    _seed_builtin(db)
    if _needs_update(db) and not _fetching:
        with _fetch_lock:
            if not _fetching:
                _fetching = True
                threading.Thread(target=_fetch_from_baostock, daemon=True).start()


def search_stocks(query: str, db: Session, limit: int = 20) -> List[Dict]:
    q = query.strip()
    if not q:
        return []

    results = []
    seen = set()

    # 精确代码匹配
    padded = q.zfill(6) if q.isdigit() else q
    exact = db.query(StockList).filter(StockList.code == padded).first()
    if exact:
        results.append({"code": exact.code, "name": exact.name, "market": exact.market})
        seen.add(exact.code)

    # 模糊匹配（名称包含 or 代码包含）
    fuzzy = (
        db.query(StockList)
        .filter(StockList.name.contains(q) | StockList.code.contains(q))
        .order_by(StockList.code)
        .limit(limit)
        .all()
    )
    for s in fuzzy:
        if s.code not in seen:
            results.append({"code": s.code, "name": s.name, "market": s.market})
            seen.add(s.code)

    return results[:limit]
