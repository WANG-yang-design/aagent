"""
Backtrader 策略回测模块
评分制入场（≥5分）+ 多条件独立出场
"""
import logging
from datetime import datetime, timedelta

import backtrader as bt
import pandas as pd

logger = logging.getLogger(__name__)


class QuantStrategy(bt.Strategy):
    """
    评分制量化策略（最高10分，≥5分入场）
    MA多头+2 / 中期多头+2 / MACD正区+2 / RSI合理+2 / 量比正常+1 / 价格>MA20+1
    出场：止损5% / 止盈15% / MACD负区+均线破坏 / RSI超买>78
    """

    params = dict(
        stop_loss   = 0.05,
        take_profit = 0.15,
        entry_score = 5,      # 入场最低分（满分10）
        rsi_overbuy = 78,     # RSI超买强制出场
    )

    def __init__(self):
        self.sma5   = bt.indicators.SMA(self.data.close, period=5)
        self.sma20  = bt.indicators.SMA(self.data.close, period=20)
        self.sma60  = bt.indicators.SMA(self.data.close, period=60)
        self.rsi    = bt.indicators.RSI(self.data.close, period=14)
        self.macd   = bt.indicators.MACD(
            self.data.close, period_me1=12, period_me2=26, period_signal=9,
        )
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=20)

        self.order       = None
        self.entry_price = 0.0

    def log(self, txt):
        logger.debug(f"[{self.data.datetime.date(0)}] {txt}")

    def next(self):
        if self.order:
            return

        price     = self.data.close[0]
        ma5       = self.sma5[0]
        ma20      = self.sma20[0]
        ma60      = self.sma60[0]
        rsi       = self.rsi[0]
        dif       = self.macd.macd[0]
        dea       = self.macd.signal[0]
        vol_ratio = self.data.volume[0] / max(self.vol_ma[0], 1)

        # ── 持仓中：出场判断 ──────────────────────────────────────────
        if self.position:
            pnl = (price - self.entry_price) / self.entry_price
            if pnl <= -self.p.stop_loss:
                self.order = self.close()
                self.log(f"止损 @ {price:.2f}  盈亏:{pnl:.2%}")
                return
            if pnl >= self.p.take_profit:
                self.order = self.close()
                self.log(f"止盈 @ {price:.2f}  盈亏:{pnl:.2%}")
                return
            # MACD转负 且 均线开始恶化
            if dif < dea and ma5 < ma20:
                self.order = self.close()
                self.log(f"MACD+均线恶化 @ {price:.2f}")
                return
            if rsi > self.p.rsi_overbuy:
                self.order = self.close()
                self.log(f"RSI超买 @ {price:.2f}  RSI:{rsi:.1f}")
                return
            return

        # ── 空仓：评分入场 ────────────────────────────────────────────
        score = 0
        if ma5 > ma20:        score += 2   # 短期多头
        if ma20 > ma60:       score += 2   # 中期多头
        if dif > dea:         score += 2   # MACD金叉区间
        if 30 < rsi < 70:     score += 2   # RSI中性
        if vol_ratio > 0.8:   score += 1   # 量比正常
        if price > ma20:      score += 1   # 价格在MA20之上

        if score >= self.p.entry_score:
            cash = self.broker.getcash()
            size = int(cash * 0.5 / price / 100) * 100
            if size > 0:
                self.order       = self.buy(size=size)
                self.entry_price = price
                self.log(f"买入 {size}股 @ {price:.2f}  评分:{score}/10  RSI:{rsi:.1f}  量比:{vol_ratio:.2f}")

    def notify_order(self, order):
        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price = order.executed.price
            self.log(
                f"{'买入' if order.isbuy() else '卖出'}成交 "
                f"{order.executed.size}股 @ {order.executed.price:.2f}"
            )
        elif order.status in (order.Canceled, order.Rejected):
            self.log("订单取消/拒绝")
        # Submitted/Accepted 时保持 self.order，Completed/Canceled/Rejected 才清除
        if order.status not in (order.Submitted, order.Accepted):
            self.order = None


# ── 回测入口函数 ──────────────────────────────────────────────────────────

def run_backtest(
    symbol:       str,
    start_date:   str   = None,
    end_date:     str   = None,
    initial_cash: float = 1_000_000,
) -> dict:
    """
    运行单支股票回测

    Returns
    -------
    dict 包含各项绩效指标
    """
    from data.market_data import get_historical_data

    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y%m%d")

    logger.info(f"[回测] {symbol}  {start_date} ~ {end_date}")

    df = get_historical_data(symbol, start_date, end_date)
    if df.empty:
        return {"error": f"无法获取 {symbol} 数据"}

    # 确保必要列存在
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            return {"error": f"数据缺少列: {col}"}

    data_feed = bt.feeds.PandasData(
        dataname=df,
        datetime=None,
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        openinterest=-1,
    )

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(data_feed, name=symbol)
    cerebro.addstrategy(QuantStrategy)
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.0003)  # 万3手续费
    cerebro.broker.set_slippage_perc(0.0002)         # 万2滑点

    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name="sharpe",   riskfreerate=0.03, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown,     _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns,      _name="returns",  tann=252)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,_name="trades")

    start_val = cerebro.broker.getvalue()
    results   = cerebro.run()
    end_val   = cerebro.broker.getvalue()

    strat = results[0]
    ta    = strat.analyzers.trades.get_analysis()

    total_trades = ta.get("total",  {}).get("closed",  0)
    won_trades   = ta.get("won",    {}).get("total",   0)
    lost_trades  = ta.get("lost",   {}).get("total",   0)

    total_return = (end_val - start_val) / start_val
    years        = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days / 365.25
    annual_return= (1 + total_return) ** (1 / max(years, 0.1)) - 1
    max_dd       = strat.analyzers.drawdown.get_analysis().get("max", {}).get("drawdown", 0) / 100
    sharpe       = strat.analyzers.sharpe.get_analysis().get("sharperatio") or 0.0
    win_rate     = won_trades / max(total_trades, 1)

    result = {
        "symbol":        symbol,
        "start_date":    start_date,
        "end_date":      end_date,
        "initial_capital": start_val,
        "final_value":   round(end_val, 2),
        "total_return":  round(total_return,  4),
        "annual_return": round(annual_return, 4),
        "max_drawdown":  round(max_dd,        4),
        "sharpe_ratio":  round(sharpe,        3),
        "total_trades":  total_trades,
        "won_trades":    won_trades,
        "lost_trades":   lost_trades,
        "win_rate":      round(win_rate, 4),
    }

    logger.info(
        f"[回测完成] {symbol}  年化={annual_return:.2%}  "
        f"最大回撤={max_dd:.2%}  胜率={win_rate:.2%}  共{total_trades}笔"
    )
    return result
