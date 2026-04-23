from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.stock_search import ensure_stock_list, search_stocks

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search")
def search(q: str = Query("", min_length=0), db: Session = Depends(get_db)):
    ensure_stock_list(db)
    if not q or len(q.strip()) == 0:
        return {"results": []}
    results = search_stocks(q.strip(), db, limit=15)

    # 批量获取实时价格（轻量）
    enriched = []
    for s in results:
        item = {"code": s["code"], "name": s["name"], "market": s["market"], "price": 0.0, "change_pct": 0.0}
        try:
            from data.market_data import get_realtime_quote
            q_data = get_realtime_quote(s["code"])
            if q_data and q_data.get("price", 0) > 0:
                item["price"] = round(q_data["price"], 3)
                prev = q_data.get("prev_close", 0)
                if prev and prev > 0:
                    item["change_pct"] = round((q_data["price"] - prev) / prev * 100, 2)
        except Exception:
            pass
        enriched.append(item)
    return {"results": enriched}


@router.get("/{symbol}/price")
def get_price(symbol: str):
    sym = symbol.strip().zfill(6)
    try:
        from data.market_data import get_realtime_quote
        q = get_realtime_quote(sym)
        if q and q.get("price", 0) > 0:
            prev = q.get("prev_close", 0)
            change_pct = round((q["price"] - prev) / prev * 100, 2) if prev else 0
            return {"symbol": sym, "price": q["price"], "change_pct": change_pct, "prev_close": prev}
    except Exception:
        pass
    raise HTTPException(503, f"无法获取 {sym} 实时行情")
