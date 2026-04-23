"""
模拟盘 Broker 实现
"""
import logging
from typing import List

from risk.risk_manager import RiskManager
from trading.broker_base import BaseBroker

logger = logging.getLogger(__name__)


class PaperBroker(BaseBroker):
    """本地模拟盘，不发送任何真实订单"""

    def __init__(self, risk_manager: RiskManager):
        self.rm = risk_manager

    @property
    def name(self) -> str:
        return "paper"

    def buy(self, symbol: str, price: float, amount: int) -> dict:
        self.rm.open_position(symbol, price, amount)
        return {"success": True, "order_id": f"PAPER_{symbol}", "message": "模拟买入成功"}

    def sell(self, symbol: str, price: float, amount: int) -> dict:
        result = self.rm.close_position(symbol, price)
        if result:
            return {"success": True, "order_id": f"PAPER_{symbol}", "message": "模拟卖出成功",
                    "pnl": result.get("pnl"), "pnl_ratio": result.get("pnl_ratio")}
        return {"success": False, "order_id": "", "message": "未持有该股票"}

    def get_positions(self) -> List[dict]:
        result = []
        # 尝试从DB获取名称（缓存）
        try:
            from database.db import get_symbol_name
            _name_cache = {}
            def _get_name(sym):
                if sym not in _name_cache:
                    _name_cache[sym] = get_symbol_name(sym) or sym
                return _name_cache[sym]
        except Exception:
            def _get_name(sym):
                return sym

        for sym, pos in self.rm.positions.items():
            cur_price = pos.get("current_price", pos["avg_cost"])
            avg_cost  = pos["avg_cost"]
            shares    = pos["shares"]
            pnl       = (cur_price - avg_cost) * shares
            pnl_ratio = (cur_price - avg_cost) / avg_cost if avg_cost > 0 else 0
            result.append({
                "symbol":       sym,
                "name":         _get_name(sym),
                "shares":       shares,
                "available":    shares,
                "avg_cost":     avg_cost,
                "price":        cur_price,
                "pnl":          pnl,
                "pnl_ratio":    pnl_ratio,
                "market_value": cur_price * shares,
                "entry_time":   pos.get("entry_time", ""),
            })
        return result

    def get_balance(self) -> dict:
        total = self.rm.portfolio_value()
        return {
            "total_asset":    round(total, 2),
            "available_cash": round(self.rm.current_capital, 2),
            "market_value":   round(total - self.rm.current_capital, 2),
            "frozen_cash":    0.0,
        }
