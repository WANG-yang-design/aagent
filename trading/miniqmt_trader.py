"""
miniQMT 实盘交易模块（基于 xtquant）
不依赖 UI 自动化，兼容 64 位 Python

前置条件：
  1. 东方财富证券 miniQMT 客户端已安装并登录
     （申请地址：东方财富证券 -> 量化交易 -> 申请迅投miniQMT）
  2. pip install xtquant

.env 配置项：
  BROKER_TYPE=miniqmt
  BROKER_ACCOUNT=资金账号
  MINIQMT_PATH=C:\\东方财富证券\\userdata_mini   # miniQMT 客户端数据目录
"""
import logging
import os
import time
from typing import List

from dotenv import load_dotenv
load_dotenv()

from trading.broker_base import BaseBroker

logger = logging.getLogger(__name__)

# miniQMT 客户端数据目录常见路径
_USERDATA_CANDIDATES = [
    os.getenv("MINIQMT_PATH", ""),
    r"C:\东方财富证券\userdata_mini",
    r"C:\国金证券QMT交易端\userdata_mini",
    r"C:\miniQMT\userdata_mini",
    r"D:\miniQMT\userdata_mini",
    r"D:\stock\east\userdata_mini",
]


def _find_userdata() -> str:
    for p in _USERDATA_CANDIDATES:
        if p and os.path.isdir(p):
            return p
    return os.getenv("MINIQMT_PATH", "")


class MiniQMTBroker(BaseBroker):
    """
    通过 xtquant 连接本机 miniQMT 客户端进行实盘交易
    连接前必须确保 miniQMT 客户端已运行并已登录账号
    """

    def __init__(self):
        self._account_id  = os.getenv("BROKER_ACCOUNT", "")
        self._userdata    = _find_userdata()
        self._trader      = None
        self._account     = None
        self._connected   = False
        self._session_id  = int(time.time()) % 100000

    @property
    def name(self) -> str:
        return "real_miniqmt"

    # ── 连接 ──────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        if not self._account_id:
            logger.error("[miniQMT] 未配置 BROKER_ACCOUNT，请检查 .env")
            return False

        if not self._userdata or not os.path.isdir(self._userdata):
            logger.error(
                f"[miniQMT] 找不到 userdata_mini 目录: {self._userdata}\n"
                "请在 .env 中设置 MINIQMT_PATH=<miniQMT安装目录>\\userdata_mini"
            )
            return False

        try:
            from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
            from xtquant.xttype import StockAccount

            class _CB(XtQuantTraderCallback):
                def on_disconnected(self):
                    logger.warning("[miniQMT] 连接断开")
                def on_stock_order(self, order):
                    logger.info(f"[miniQMT] 委托回报: {order}")
                def on_stock_trade(self, trade):
                    logger.info(f"[miniQMT] 成交回报: {trade}")
                def on_order_error(self, order_error):
                    logger.error(f"[miniQMT] 委托失败: {order_error}")

            self._trader = XtQuantTrader(self._userdata, self._session_id)
            self._trader.register_callback(_CB())
            self._trader.start()

            conn = self._trader.connect()
            if conn != 0:
                logger.error(f"[miniQMT] 连接失败，返回码: {conn}")
                return False

            self._account = StockAccount(self._account_id, "STOCK")

            # 订阅账户推送
            self._trader.subscribe_position(self._account)
            self._trader.subscribe_order(self._account)
            self._trader.subscribe_trade(self._account)

            self._connected = True
            logger.info(f"[miniQMT] 连接成功  账户={self._account_id}")
            return True

        except ImportError:
            logger.error(
                "[miniQMT] 未安装 xtquant，请执行：\n"
                "pip install xtquant"
            )
        except Exception as e:
            logger.error(f"[miniQMT] 连接异常: {e}")

        self._connected = False
        return False

    def _check_conn(self):
        if not self._connected or self._trader is None:
            raise RuntimeError("miniQMT 未连接，请先启动实盘模式")

    # ── 下单 ──────────────────────────────────────────────────────────────

    def buy(self, symbol: str, price: float, amount: int) -> dict:
        self._check_conn()
        try:
            from xtquant.xttype import STOCK_BUY, XT_ORDER_FIX_PRICE, XT_ORDER_MARKET
            price_type = XT_ORDER_MARKET if price <= 0 else XT_ORDER_FIX_PRICE
            oid = self._trader.order_stock(
                self._account, symbol, STOCK_BUY,
                amount, price_type, price or 0,
            )
            logger.info(f"[miniQMT买入] {symbol} {amount}股 @ {price}  order_id={oid}")
            return {"success": oid >= 0, "order_id": str(oid), "message": f"order_id={oid}"}
        except Exception as e:
            logger.error(f"[miniQMT买入失败] {symbol}: {e}")
            return {"success": False, "order_id": "", "message": str(e)}

    def sell(self, symbol: str, price: float, amount: int) -> dict:
        self._check_conn()
        try:
            from xtquant.xttype import STOCK_SELL, XT_ORDER_FIX_PRICE, XT_ORDER_MARKET
            price_type = XT_ORDER_MARKET if price <= 0 else XT_ORDER_FIX_PRICE
            oid = self._trader.order_stock(
                self._account, symbol, STOCK_SELL,
                amount, price_type, price or 0,
            )
            logger.info(f"[miniQMT卖出] {symbol} {amount}股 @ {price}  order_id={oid}")
            return {"success": oid >= 0, "order_id": str(oid), "message": f"order_id={oid}"}
        except Exception as e:
            logger.error(f"[miniQMT卖出失败] {symbol}: {e}")
            return {"success": False, "order_id": "", "message": str(e)}

    # ── 查询 ──────────────────────────────────────────────────────────────

    def get_positions(self) -> List[dict]:
        self._check_conn()
        try:
            raw = self._trader.query_stock_positions(self._account)
            result = []
            for p in (raw or []):
                shares = int(p.volume or 0)
                if shares <= 0:
                    continue
                avg_cost = float(p.open_price or 0)
                cur_price = float(p.market_value / shares) if shares > 0 else avg_cost
                pnl = float(p.profit_loss or 0)
                pnl_ratio = pnl / (avg_cost * shares) if avg_cost * shares > 0 else 0
                result.append({
                    "symbol":       p.stock_code,
                    "name":         getattr(p, "stock_name", p.stock_code),
                    "shares":       shares,
                    "available":    int(p.can_use_volume or 0),
                    "avg_cost":     avg_cost,
                    "price":        cur_price,
                    "pnl":          pnl,
                    "pnl_ratio":    round(pnl_ratio, 4),
                    "market_value": float(p.market_value or 0),
                    "entry_time":   "",
                })
            return result
        except Exception as e:
            logger.error(f"[miniQMT持仓查询失败]: {e}")
            return []

    def get_balance(self) -> dict:
        self._check_conn()
        try:
            a = self._trader.query_stock_asset(self._account)
            if a is None:
                return {"total_asset": 0, "available_cash": 0, "market_value": 0, "frozen_cash": 0}
            return {
                "total_asset":    float(a.total_asset or 0),
                "available_cash": float(a.cash or 0),
                "market_value":   float(a.market_value or 0),
                "frozen_cash":    float(a.frozen_cash or 0),
            }
        except Exception as e:
            logger.error(f"[miniQMT资金查询失败]: {e}")
            return {"total_asset": 0, "available_cash": 0, "market_value": 0, "frozen_cash": 0}

    def get_orders(self) -> List[dict]:
        self._check_conn()
        try:
            raw = self._trader.query_stock_trades(self._account)
            result = []
            for o in (raw or []):
                result.append({
                    "order_id":  str(o.order_id),
                    "symbol":    o.stock_code,
                    "name":      getattr(o, "stock_name", o.stock_code),
                    "action":    "BUY" if o.order_type == 23 else "SELL",
                    "price":     float(o.traded_price or 0),
                    "shares":    int(o.traded_volume or 0),
                    "amount":    float(o.traded_amount or 0),
                    "timestamp": str(o.traded_time or ""),
                })
            return result
        except Exception as e:
            logger.warning(f"[miniQMT成交查询失败]: {e}")
            return []

    def disconnect(self):
        if self._trader:
            try:
                self._trader.stop()
            except Exception:
                pass
        self._connected = False
        self._trader = None
        logger.info("[miniQMT] 已断开连接")
