"""
券商接口抽象基类
所有 Broker 实现必须继承此类
"""
from abc import ABC, abstractmethod
from typing import List


class BaseBroker(ABC):

    @abstractmethod
    def buy(self, symbol: str, price: float, amount: int) -> dict:
        """
        买入
        Returns: {"success": bool, "order_id": str, "message": str}
        """

    @abstractmethod
    def sell(self, symbol: str, price: float, amount: int) -> dict:
        """卖出"""

    @abstractmethod
    def get_positions(self) -> List[dict]:
        """
        持仓列表
        Returns: [{"symbol": "000001", "shares": 1000, "avg_cost": 10.5, ...}]
        """

    @abstractmethod
    def get_balance(self) -> dict:
        """
        账户资金
        Returns: {"total_asset": 1000000, "available_cash": 500000, ...}
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Broker 名称标识"""

    def cancel_order(self, order_id: str) -> dict:
        """撤单（可选实现）"""
        return {"success": False, "message": "该Broker不支持撤单"}

    def get_orders(self) -> List[dict]:
        """当日委托（可选实现）"""
        return []
