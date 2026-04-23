"""
风险管理模块
规则：
  - 单次仓位 ≤ 总资金 50%
  - 单日最大亏损 ≤ 10%
  - 单日交易次数 ≤ 100
  - 止损 5% / 止盈 15%
  - AI 置信度 < 0.60 不交易
"""
import logging
from datetime import date, datetime
from typing import Dict, Optional, Tuple

import config

logger = logging.getLogger(__name__)

# 每笔交易固定手续费（元），买卖各一次
COMMISSION_PER_TRADE = float(getattr(config, "COMMISSION", 5.0))


class RiskManager:
    def __init__(
        self,
        initial_capital:      float = config.INITIAL_CAPITAL,
        max_position_ratio:   float = config.MAX_POSITION_RATIO,
        max_daily_loss_ratio: float = config.MAX_DAILY_LOSS_RATIO,
        max_daily_trades:     int   = config.MAX_DAILY_TRADES,
        stop_loss_ratio:      float = config.STOP_LOSS_RATIO,
        take_profit_ratio:    float = config.TAKE_PROFIT_RATIO,
        min_confidence:       float = config.MIN_CONFIDENCE,
    ):
        self.initial_capital      = initial_capital
        self.max_position_ratio   = max_position_ratio
        self.max_daily_loss_ratio = max_daily_loss_ratio
        self.max_daily_trades     = max_daily_trades
        self.stop_loss_ratio      = stop_loss_ratio
        self.take_profit_ratio    = take_profit_ratio
        self.min_confidence       = min_confidence

        self.current_capital: float       = initial_capital
        self.positions:       Dict[str, dict] = {}   # symbol → position dict
        self.today_trades:    int         = 0
        self.today_date:      date        = date.today()
        self.day_start_cap:   float       = initial_capital

    # ── 内部工具 ──────────────────────────────────────────────────────────

    def _refresh_day(self):
        today = date.today()
        if today != self.today_date:
            self.today_date    = today
            self.today_trades  = 0
            self.day_start_cap = self.portfolio_value()

    def _daily_loss_ratio(self) -> float:
        return (self.current_capital - self.day_start_cap) / self.day_start_cap

    # ── 买入检查 ──────────────────────────────────────────────────────────

    def check_buy(
        self, symbol: str, price: float, confidence: float
    ) -> Tuple[bool, str, int]:
        """
        Returns
        -------
        (allowed, reason, shares)
        shares 为建议买入手数（100股整数倍），0 表示不买
        """
        self._refresh_day()

        if symbol in self.positions:
            return False, "已持有该股，不重复建仓", 0

        if self.today_trades >= self.max_daily_trades:
            return False, f"今日交易次数已达上限 {self.max_daily_trades}", 0

        if self._daily_loss_ratio() < -self.max_daily_loss_ratio:
            return False, f"今日亏损 {self._daily_loss_ratio():.1%} 已达风控上限", 0

        if confidence < self.min_confidence:
            return False, f"AI置信度 {confidence:.0%} < 阈值 {self.min_confidence:.0%}", 0

        # 仓位计算
        invest = self.current_capital * self.max_position_ratio
        shares = int(invest / price / 100) * 100   # 向下取整到手（100股）
        if shares <= 0:
            return False, "可用资金不足一手", 0

        actual_cost = shares * price
        if actual_cost > self.current_capital:
            shares = int(self.current_capital / price / 100) * 100
        if shares <= 0:
            return False, "资金不足以购买最小手数", 0

        return True, "通过全部风控检查", shares

    # ── 卖出检查（强制止损/止盈）────────────────────────────────────────

    def check_force_exit(self, symbol: str, price: float) -> Tuple[bool, str]:
        """检查是否需要强制平仓（止损/止盈），与AI决策无关"""
        if symbol not in self.positions:
            return False, "未持仓"
        pos = self.positions[symbol]
        pnl = (price - pos["avg_cost"]) / pos["avg_cost"]
        if pnl <= -self.stop_loss_ratio:
            return True, f"触发止损 {pnl:.2%}"
        if pnl >= self.take_profit_ratio:
            return True, f"触发止盈 {pnl:.2%}"
        return False, f"持仓盈亏 {pnl:.2%}"

    # ── 开/平仓执行 ───────────────────────────────────────────────────────

    def open_position(self, symbol: str, price: float, shares: int):
        cost       = price * shares
        commission = COMMISSION_PER_TRADE
        total_paid = cost + commission
        self.positions[symbol] = {
            "shares":         shares,
            "avg_cost":       price,
            "entry_price":    price,
            "entry_time":     datetime.now().isoformat(),
            "cost":           cost,           # 不含手续费的原始成本
            "buy_commission": commission,     # 买入手续费
        }
        self.current_capital -= total_paid
        self.today_trades    += 1
        logger.info(
            f"[开仓] {symbol}  {shares}股 @ {price:.2f}  "
            f"成本={cost:.2f}  手续费={commission:.2f}  剩余现金={self.current_capital:.2f}"
        )

    def close_position(self, symbol: str, price: float) -> dict:
        if symbol not in self.positions:
            return {}
        pos            = self.positions.pop(symbol)
        proceeds       = price * pos["shares"]
        sell_commission = COMMISSION_PER_TRADE
        net_proceeds   = proceeds - sell_commission
        # 实际盈亏 = 净收益 - (原始成本 + 买入手续费)
        total_cost     = pos["cost"] + pos.get("buy_commission", COMMISSION_PER_TRADE)
        pnl            = net_proceeds - total_cost
        pnl_r          = pnl / total_cost if total_cost > 0 else 0
        self.current_capital += net_proceeds
        self.today_trades    += 1
        logger.info(
            f"[平仓] {symbol}  {pos['shares']}股 @ {price:.2f}  "
            f"毛收益={proceeds:.2f}  手续费={sell_commission:.2f}  "
            f"盈亏={pnl:.2f}({pnl_r:.2%})"
        )
        return {
            "symbol":      symbol,
            "shares":      pos["shares"],
            "entry_price": pos["entry_price"],
            "exit_price":  price,
            "pnl":         round(pnl, 2),
            "pnl_ratio":   round(pnl_r, 4),
            "commission":  sell_commission,
        }

    # ── 汇总 ─────────────────────────────────────────────────────────────

    def portfolio_value(self, prices: Optional[Dict[str, float]] = None) -> float:
        """账户总市值（现金 + 持仓市值）
        优先级：外部传入prices > position['current_price'] > avg_cost
        """
        prices = prices or {}
        stock_val = 0.0
        for s, p in self.positions.items():
            cur = (
                prices.get(s)
                or p.get("current_price")
                or p["avg_cost"]
            )
            stock_val += p["shares"] * cur
        return self.current_capital + stock_val

    def summary(self) -> dict:
        return {
            "current_capital": round(self.current_capital, 2),
            "positions":       len(self.positions),
            "today_trades":    self.today_trades,
            "total_pnl":       round(self.portfolio_value() - self.initial_capital, 2),
            "total_return":    round(
                (self.portfolio_value() - self.initial_capital) / self.initial_capital, 4
            ),
        }
