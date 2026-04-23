"""
实盘交易模块（基于 easytrader）
针对东方财富证券优化（universal_client / 同花顺下单端）

.env 配置项：
  BROKER_TYPE=universal_client   # 东方财富证券固定用此值
  BROKER_ACCOUNT=资金账号
  BROKER_PASSWORD=交易密码
  BROKER_EXE=C:\\东方财富证券\\交易终端\\xiadan.exe
  BROKER_COMM_PASSWORD=         # 通讯密码（没有留空）

easytrader 支持的类型速查：
  universal_client  通用同花顺客户端（东方财富/国信/方正/光大等）
  ths               同花顺标准版
  yh_client         银河证券
  ht_client         华泰证券
  htzq_client       海通证券
  gj_client         国金证券
  gf_client         广发证券
  miniqmt           东财QMT / 迅投miniQMT（需另装xtquant）
"""
import logging
import os
from typing import List

from dotenv import load_dotenv
load_dotenv()

from trading.broker_base import BaseBroker

logger = logging.getLogger(__name__)

# 东方财富证券下单程序常见路径（按优先级尝试）
# 注：新版东方财富使用 maintrade.exe（同花顺内核），旧版为 xiadan.exe
_EMF_EXE_CANDIDATES = [
    r"D:\stock\east\maintrade.exe",           # 用户实际安装路径（优先）
    r"D:\stock\east\mainfree.exe",            # 主启动器（备用，部分版本可用）
    r"C:\东方财富证券\交易终端\maintrade.exe",
    r"C:\东方财富证券\交易终端\xiadan.exe",
    r"C:\东方财富证券\下单\xiadan.exe",
    r"C:\东方财富证券\THS\xiadan.exe",
    r"C:\Program Files\东方财富证券\maintrade.exe",
    r"C:\Program Files\东方财富证券\xiadan.exe",
    r"C:\Program Files (x86)\东方财富证券\xiadan.exe",
    r"C:\ths\xiadan.exe",                     # easytrader 默认路径
]


def _find_emf_exe() -> str:
    """自动探测东方财富证券 xiadan.exe 路径"""
    cfg = os.getenv("BROKER_EXE", "")
    if cfg and os.path.exists(cfg):
        return cfg
    for path in _EMF_EXE_CANDIDATES:
        if os.path.exists(path):
            logger.info(f"[实盘] 自动找到东财客户端: {path}")
            return path
    return cfg   # 找不到时仍返回配置值（连接时会报错提示用户）


class RealBroker(BaseBroker):
    """
    通过 easytrader 控制本机东方财富证券客户端进行实盘交易
    连接前必须确保：
      1. 东方财富证券 PC 客户端已安装（含同花顺下单端 xiadan.exe）
      2. .env 中填写了正确的账号/密码/exe路径
    """

    def __init__(self):
        self._broker_type   = os.getenv("BROKER_TYPE",          "universal_client")
        self._account       = os.getenv("BROKER_ACCOUNT",       "")
        self._password      = os.getenv("BROKER_PASSWORD",      "")
        self._comm_password = os.getenv("BROKER_COMM_PASSWORD", "")
        self._exe_path      = _find_emf_exe()
        self._user          = None
        self._connected     = False

    @property
    def name(self) -> str:
        return f"real_{self._broker_type}"

    # ── 连接 ──────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        启动并登录东方财富证券 PC 客户端
        easytrader 会自动：
          1. 打开 xiadan.exe（如未运行则自动启动）
          2. 输入账号密码完成登录
          3. 定位到买入/卖出功能页面
        """
        if not self._account or not self._password:
            logger.error("[实盘] 未配置账号/密码，请检查 .env 文件")
            return False

        try:
            import easytrader
            self._user = easytrader.use(self._broker_type)

            kwargs = dict(
                user=self._account,
                password=self._password,
                exe_path=self._exe_path or None,
            )
            if self._comm_password:
                kwargs["comm_password"] = self._comm_password

            logger.info(f"[实盘] 正在连接东方财富证券...  exe={self._exe_path}")
            self._user.prepare(**kwargs)
            self._connected = True
            logger.info("[实盘] 东方财富证券连接成功")
            return True

        except FileNotFoundError:
            logger.error(
                f"[实盘] 找不到东方财富证券客户端: {self._exe_path}\n"
                "请在 .env 中设置正确的 BROKER_EXE 路径，\n"
                "例如: BROKER_EXE=D:\\stock\\east\\maintrade.exe"
            )
        except Exception as e:
            logger.error(f"[实盘] 连接失败: {e}")

        self._connected = False
        return False

    def _check_conn(self):
        if not self._connected or self._user is None:
            raise RuntimeError("实盘未连接，请先点击 Web 界面「启动实盘」或调用 connect()")

    # ── 下单接口 ──────────────────────────────────────────────────────────

    def buy(self, symbol: str, price: float, amount: int) -> dict:
        """
        买入委托
        price=0 时使用市价（东方财富同花顺端支持市价单）
        """
        self._check_conn()
        try:
            result = self._user.buy(symbol, price=price, amount=amount)
            logger.info(f"[实盘买入] {symbol}  {amount}股 @ {price:.2f}  回报: {result}")
            return {"success": True, "order_id": str(result), "message": str(result)}
        except Exception as e:
            logger.error(f"[实盘买入失败] {symbol}: {e}")
            return {"success": False, "order_id": "", "message": str(e)}

    def sell(self, symbol: str, price: float, amount: int) -> dict:
        """卖出委托"""
        self._check_conn()
        try:
            result = self._user.sell(symbol, price=price, amount=amount)
            logger.info(f"[实盘卖出] {symbol}  {amount}股 @ {price:.2f}  回报: {result}")
            return {"success": True, "order_id": str(result), "message": str(result)}
        except Exception as e:
            logger.error(f"[实盘卖出失败] {symbol}: {e}")
            return {"success": False, "order_id": "", "message": str(e)}

    def cancel_order(self, order_id: str) -> dict:
        """撤单"""
        self._check_conn()
        try:
            self._user.cancel_entrust(order_id)
            return {"success": True, "message": "撤单成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── 账户查询 ──────────────────────────────────────────────────────────

    def get_positions(self) -> List[dict]:
        """
        查询持仓
        东方财富同花顺端返回字段：
          证券代码/证券名称/股票余额/可用余额/成本价/市价/盈亏金额/盈亏比例/市值
        """
        self._check_conn()
        try:
            raw = self._user.position
            result = []
            for p in raw:
                symbol = str(p.get("证券代码") or p.get("stock_code") or "")
                if not symbol:
                    continue
                result.append({
                    "symbol":       symbol,
                    "name":         str(p.get("证券名称") or p.get("stock_name") or symbol),
                    "shares":       int(float(p.get("股票余额")  or p.get("balance")       or 0)),
                    "available":    int(float(p.get("可用余额")  or p.get("enable_amount")  or 0)),
                    "avg_cost":     float(p.get("成本价")        or p.get("cost_price")     or 0),
                    "price":        float(p.get("市价")          or p.get("market_price")   or 0),
                    "pnl":          float(p.get("盈亏金额")      or p.get("profit_loss")    or 0),
                    "pnl_ratio":    _to_pct(p.get("盈亏比例")   or p.get("profit_loss_ratio") or 0),
                    "market_value": float(p.get("市值")          or p.get("market_value")   or 0),
                    "entry_time":   "",
                })
            return result
        except Exception as e:
            logger.error(f"[实盘持仓查询失败]: {e}")
            return []

    def get_balance(self) -> dict:
        """
        查询资金
        东方财富同花顺端返回字段：
          总资产/可用金额/证券市值/冻结金额
        """
        self._check_conn()
        try:
            b = self._user.balance
            if isinstance(b, list):
                b = b[0] if b else {}
            return {
                "total_asset":    float(b.get("总资产")    or b.get("asset_balance")  or 0),
                "available_cash": float(b.get("可用金额")  or b.get("enable_balance") or 0),
                "market_value":   float(b.get("证券市值")  or b.get("market_value")   or 0),
                "frozen_cash":    float(b.get("冻结金额")  or 0),
            }
        except Exception as e:
            logger.error(f"[实盘余额查询失败]: {e}")
            return {"total_asset": 0, "available_cash": 0, "market_value": 0, "frozen_cash": 0}

    def get_orders(self) -> List[dict]:
        """查询当日成交"""
        self._check_conn()
        try:
            raw = self._user.current_deal
            result = []
            for o in raw:
                result.append({
                    "order_id":  str(o.get("成交编号") or ""),
                    "symbol":    str(o.get("证券代码") or ""),
                    "name":      str(o.get("证券名称") or ""),
                    "action":    str(o.get("操作")     or ""),
                    "price":     float(o.get("成交价格") or 0),
                    "shares":    int(float(o.get("成交数量") or 0)),
                    "amount":    float(o.get("成交金额") or 0),
                    "timestamp": str(o.get("成交时间")  or ""),
                })
            return result
        except Exception as e:
            logger.warning(f"[实盘成交查询失败]: {e}")
            return []

    def disconnect(self):
        self._connected = False
        self._user = None
        logger.info("[实盘] 已断开连接")


# ── 工具函数 ──────────────────────────────────────────────────────────────

def _to_pct(val) -> float:
    """将 '12.34%' 或 0.1234 统一转为小数"""
    if val is None:
        return 0.0
    s = str(val).replace("%", "").strip()
    try:
        f = float(s)
        return f / 100 if abs(f) > 1.5 else f   # >1.5 认为是百分数
    except ValueError:
        return 0.0
