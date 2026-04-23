from datetime import date as _date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Position, Transaction, User
from backend.schemas import BuyReq, SellReq

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _get_current_price(symbol: str) -> float:
    try:
        from data.market_data import get_realtime_quote
        q = get_realtime_quote(symbol)
        if q and q.get("price", 0) > 0:
            return q["price"]
    except Exception:
        pass
    return 0.0


@router.get("/positions")
def get_positions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    positions = db.query(Position).filter(Position.user_id == current_user.id).all()
    result = []
    total_cost = 0.0
    total_market_value = 0.0

    for pos in positions:
        price = _get_current_price(pos.symbol)
        market_value = round(price * pos.shares, 2) if price > 0 else round(pos.total_cost, 2)
        unrealized_pnl = round(market_value - pos.total_cost, 2)
        unrealized_pnl_pct = round(unrealized_pnl / pos.total_cost * 100, 2) if pos.total_cost > 0 else 0

        total_cost += pos.total_cost
        total_market_value += market_value

        result.append({
            "id": pos.id,
            "symbol": pos.symbol,
            "name": pos.name,
            "shares": pos.shares,
            "avg_cost": round(pos.avg_cost, 3),
            "total_cost": round(pos.total_cost, 2),
            "current_price": price,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "updated_at": pos.updated_at.strftime("%Y-%m-%d %H:%M") if pos.updated_at else "",
        })

    # Summary
    total_unrealized = round(total_market_value - total_cost, 2)
    total_unrealized_pct = round(total_unrealized / total_cost * 100, 2) if total_cost > 0 else 0

    # Realized P&L from transactions
    sell_txns = db.query(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.action == "SELL",
    ).all()
    total_realized = round(sum(t.realized_pnl for t in sell_txns), 2)

    return {
        "positions": result,
        "summary": {
            "total_cost": round(total_cost, 2),
            "market_value": round(total_market_value, 2),
            "unrealized_pnl": total_unrealized,
            "unrealized_pnl_pct": total_unrealized_pct,
            "realized_pnl": total_realized,
            "total_pnl": round(total_unrealized + total_realized, 2),
            "position_count": len(result),
        },
    }


@router.post("/buy")
def buy(req: BuyReq, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.shares <= 0 or req.price <= 0:
        raise HTTPException(400, "股数和价格必须大于0")

    sym = req.symbol.strip().zfill(6)
    name = req.name.strip()
    if not name:
        try:
            from data.market_data import get_stock_name
            name = get_stock_name(sym) or sym
        except Exception:
            name = sym

    buy_date = req.date or str(_date.today())
    amount = round(req.price * req.shares, 2)

    # Upsert position
    pos = db.query(Position).filter(Position.user_id == current_user.id, Position.symbol == sym).first()
    if pos:
        new_total_cost = pos.total_cost + amount
        new_shares = pos.shares + req.shares
        pos.avg_cost = round(new_total_cost / new_shares, 4)
        pos.shares = new_shares
        pos.total_cost = round(new_total_cost, 2)
        pos.name = name
    else:
        pos = Position(
            user_id=current_user.id,
            symbol=sym,
            name=name,
            shares=req.shares,
            avg_cost=round(req.price, 4),
            total_cost=amount,
        )
        db.add(pos)

    # Record transaction
    txn = Transaction(
        user_id=current_user.id,
        symbol=sym,
        name=name,
        action="BUY",
        price=req.price,
        shares=req.shares,
        amount=amount,
        date=buy_date,
        note=req.note,
    )
    db.add(txn)
    db.commit()
    return {"status": "ok", "symbol": sym, "shares": req.shares, "price": req.price, "amount": amount}


@router.post("/sell")
def sell(req: SellReq, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.shares <= 0 or req.price <= 0:
        raise HTTPException(400, "股数和价格必须大于0")

    sym = req.symbol.strip().zfill(6)
    pos = db.query(Position).filter(Position.user_id == current_user.id, Position.symbol == sym).first()
    if not pos:
        raise HTTPException(404, f"未找到 {sym} 的持仓")
    if req.shares > pos.shares:
        raise HTTPException(400, f"卖出股数 {req.shares} 超过持仓 {pos.shares}")

    sell_date = req.date or str(_date.today())
    amount = round(req.price * req.shares, 2)
    cost_basis = round(pos.avg_cost * req.shares, 2)
    realized_pnl = round(amount - cost_basis, 2)
    realized_pnl_pct = round(realized_pnl / cost_basis * 100, 2) if cost_basis > 0 else 0

    # Update or remove position
    if req.shares >= pos.shares:
        db.delete(pos)
    else:
        pos.shares = round(pos.shares - req.shares, 0)
        pos.total_cost = round(pos.avg_cost * pos.shares, 2)

    txn = Transaction(
        user_id=current_user.id,
        symbol=sym,
        name=pos.name,
        action="SELL",
        price=req.price,
        shares=req.shares,
        amount=amount,
        realized_pnl=realized_pnl,
        realized_pnl_pct=realized_pnl_pct,
        date=sell_date,
        note=req.note,
    )
    db.add(txn)
    db.commit()
    return {
        "status": "ok",
        "symbol": sym,
        "realized_pnl": realized_pnl,
        "realized_pnl_pct": realized_pnl_pct,
    }


@router.delete("/positions/{position_id}")
def delete_position(position_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pos = db.query(Position).filter(Position.id == position_id, Position.user_id == current_user.id).first()
    if not pos:
        raise HTTPException(404, "持仓不存在")
    db.delete(pos)
    db.commit()
    return {"status": "ok"}


@router.get("/transactions")
def get_transactions(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txns = (
        db.query(Transaction)
        .filter(Transaction.user_id == current_user.id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "name": t.name,
            "action": t.action,
            "price": t.price,
            "shares": t.shares,
            "amount": t.amount,
            "realized_pnl": t.realized_pnl,
            "realized_pnl_pct": t.realized_pnl_pct,
            "date": t.date,
            "note": t.note,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
        }
        for t in txns
    ]
