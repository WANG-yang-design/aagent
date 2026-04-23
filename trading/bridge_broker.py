"""
桥接 Broker —— 运行在主程序（64位Python）中
通过 HTTP 调用本地桥接服务（32位Python）完成实盘下单
"""
import logging
import os
from typing import List

import urllib.request
import urllib.error
import json

from dotenv import load_dotenv
load_dotenv()

from trading.broker_base import BaseBroker

logger = logging.getLogger(__name__)

BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", 8890))
BRIDGE_URL  = f"http://127.0.0.1:{BRIDGE_PORT}"


def _call(method: str, path: str, data: dict = None, timeout: int = 60) -> dict:
    url = BRIDGE_URL + path
    body = json.dumps(data).encode() if data else None
    req  = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    # 绕过系统代理（Clash等），直连本地桥接服务
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class BridgeBroker(BaseBroker):
    """通过本地桥接服务（32位Python进程）控制东方财富客户端"""

    def __init__(self):
        self._connected = False

    @property
    def name(self) -> str:
        return "real_bridge"

    def connect(self) -> bool:
        # 先检查桥接服务是否在线
        try:
            _call("GET", "/health", timeout=3)
        except Exception:
            logger.error(
                "[桥接] 桥接服务未启动！\n"
                "请先运行：D:\\python38_32\\python.exe D:\\AAgent\\trading\\broker_bridge_server.py"
            )
            return False

        # 发起连接指令
        try:
            result = _call("POST", "/connect", {
                "broker_type":   os.getenv("BROKER_TYPE", "universal_client"),
                "account":       os.getenv("BROKER_ACCOUNT", ""),
                "password":      os.getenv("BROKER_PASSWORD", ""),
                "exe_path":      os.getenv("BROKER_EXE", ""),
                "comm_password": os.getenv("BROKER_COMM_PASSWORD", ""),
            }, timeout=90)
            if result.get("success"):
                self._connected = True
                logger.info("[桥接] 实盘连接成功")
                return True
            else:
                logger.error(f"[桥接] 连接失败: {result.get('error')}")
                return False
        except Exception as e:
            logger.error(f"[桥接] 连接异常: {e}")
            return False

    def _check(self):
        if not self._connected:
            raise RuntimeError("实盘桥接未连接")

    def buy(self, symbol: str, price: float, amount: int) -> dict:
        self._check()
        try:
            r = _call("POST", "/buy", {"symbol": symbol, "price": price, "amount": amount})
            return {"success": r.get("success", False), "order_id": r.get("result", ""), "message": r.get("result", "")}
        except Exception as e:
            logger.error(f"[桥接买入失败] {symbol}: {e}")
            return {"success": False, "order_id": "", "message": str(e)}

    def sell(self, symbol: str, price: float, amount: int) -> dict:
        self._check()
        try:
            r = _call("POST", "/sell", {"symbol": symbol, "price": price, "amount": amount})
            return {"success": r.get("success", False), "order_id": r.get("result", ""), "message": r.get("result", "")}
        except Exception as e:
            logger.error(f"[桥接卖出失败] {symbol}: {e}")
            return {"success": False, "order_id": "", "message": str(e)}

    def get_positions(self) -> List[dict]:
        self._check()
        try:
            raw = _call("GET", "/positions").get("positions", [])
            result = []
            for p in raw:
                symbol = str(p.get("证券代码") or p.get("stock_code") or "")
                if not symbol:
                    continue
                avg_cost = float(p.get("成本价") or p.get("cost_price") or 0)
                shares   = int(float(p.get("股票余额") or p.get("balance") or 0))
                price    = float(p.get("市价") or p.get("market_price") or avg_cost)
                pnl      = float(p.get("盈亏金额") or p.get("profit_loss") or 0)
                pnl_r    = pnl / (avg_cost * shares) if avg_cost * shares > 0 else 0
                result.append({
                    "symbol":       symbol,
                    "name":         str(p.get("证券名称") or p.get("stock_name") or symbol),
                    "shares":       shares,
                    "available":    int(float(p.get("可用余额") or p.get("enable_amount") or 0)),
                    "avg_cost":     avg_cost,
                    "price":        price,
                    "pnl":          pnl,
                    "pnl_ratio":    round(pnl_r, 4),
                    "market_value": float(p.get("市值") or p.get("market_value") or 0),
                    "entry_time":   "",
                })
            return result
        except Exception as e:
            logger.error(f"[桥接持仓查询失败]: {e}")
            return []

    def get_balance(self) -> dict:
        self._check()
        try:
            b = _call("GET", "/balance")
            return {
                "total_asset":    float(b.get("总资产")   or b.get("asset_balance")  or 0),
                "available_cash": float(b.get("可用金额") or b.get("enable_balance") or 0),
                "market_value":   float(b.get("证券市值") or b.get("market_value")   or 0),
                "frozen_cash":    float(b.get("冻结金额") or 0),
            }
        except Exception as e:
            logger.error(f"[桥接余额查询失败]: {e}")
            return {"total_asset": 0, "available_cash": 0, "market_value": 0, "frozen_cash": 0}

    def get_orders(self) -> List[dict]:
        self._check()
        try:
            raw = _call("GET", "/orders").get("orders", [])
            return [{
                "order_id":  str(o.get("成交编号") or ""),
                "symbol":    str(o.get("证券代码") or ""),
                "name":      str(o.get("证券名称") or ""),
                "action":    str(o.get("操作") or ""),
                "price":     float(o.get("成交价格") or 0),
                "shares":    int(float(o.get("成交数量") or 0)),
                "amount":    float(o.get("成交金额") or 0),
                "timestamp": str(o.get("成交时间") or ""),
            } for o in raw]
        except Exception as e:
            logger.warning(f"[桥接成交查询失败]: {e}")
            return []

    def disconnect(self):
        try:
            _call("POST", "/disconnect")
        except Exception:
            pass
        self._connected = False
