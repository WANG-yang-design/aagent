"""
交易引擎（统一模拟盘 / 实盘）
职责：定时扫描 → 技术分析 → AI 决策 → 风控 → 下单 → 记录日志 + DB
"""
import asyncio
import logging
import threading
import time
from datetime import datetime, time as dtime
from typing import Callable, List, Optional

import config
from ai_decision.agent import get_ai_decision
from data.market_data import get_historical_data, get_realtime_quote
from data.news_sentiment import get_stock_news_sentiment
from database import db
from indicators.technical import add_indicators, get_latest_indicators, get_recent_bars
from risk.risk_manager import RiskManager
from trading.broker_base import BaseBroker
from trading.paper_trader import PaperBroker
from utils.logger import trade_logger

logger = logging.getLogger(__name__)

_MORNING_OPEN    = dtime(9, 30)
_MORNING_CLOSE   = dtime(11, 30)
_AFTERNOON_OPEN  = dtime(13, 0)
_AFTERNOON_CLOSE = dtime(15, 0)


def _in_trading_hours() -> bool:
    now = datetime.now().time()
    return (
        _MORNING_OPEN  <= now <= _MORNING_CLOSE or
        _AFTERNOON_OPEN <= now <= _AFTERNOON_CLOSE
    )


class TradingEngine:
    """
    统一交易引擎
    mode  : "paper"（模拟盘）或 "real"（实盘）
    broker: 注入的 Broker 实例；为 None 时自动创建 PaperBroker
    """

    def __init__(
        self,
        symbols: List[str] = None,
        mode: str = "paper",
        broker: Optional[BaseBroker] = None,
        interval: int = 60,
        push_callback: Optional[Callable] = None,
        fail_on_connect_error: bool = False,
    ):
        self.symbols  = list(dict.fromkeys(symbols or config.DEFAULT_SYMBOLS))  # 去重保序
        self.mode     = mode
        self.interval = interval
        self.push_callback = push_callback   # 回调给 WebSocket 广播
        self.fail_on_connect_error = fail_on_connect_error

        # 风控
        self.risk_manager = RiskManager(initial_capital=config.INITIAL_CAPITAL)

        # Broker
        if broker is not None:
            self.broker = broker
        elif mode == "real":
            logger.info("[引擎] 创建实盘Broker，准备连接...")
            rb = self._create_real_broker()
            if rb is None:
                logger.error("[引擎] 创建实盘Broker失败（返回None）")
                if fail_on_connect_error:
                    raise RuntimeError("创建实盘Broker失败")
                else:
                    self.mode = "paper"
                    self.broker = PaperBroker(self.risk_manager)
            else:
                logger.info(f"[引擎] Broker已创建，开始连接...")
                if rb.connect():
                    logger.info("[引擎] 实盘连接成功")
                    self.broker = rb
                else:
                    logger.error("[引擎] 实盘连接失败")
                    if fail_on_connect_error:
                        raise RuntimeError("连接实盘失败，请检查桥接服务状态和 .env 配置")
                    else:
                        logger.warning("[引擎] 实盘连接失败，降级为模拟盘")
                        self.mode = "paper"
                        self.broker = PaperBroker(self.risk_manager)
        else:
            self.broker = PaperBroker(self.risk_manager)

        self.running = False
        self._thread: Optional[threading.Thread] = None

        # 最新信号缓存（供 API 读取）
        self.latest_signals: dict = {}   # symbol → analysis dict

        logger.info(f"[引擎] 初始化完成  模式={self.mode}  标的={self.symbols}")

    # ── 创建实盘 Broker（按 BROKER_TYPE 自动选择）────────────────────────

    @staticmethod
    def _create_real_broker():
        broker_type = config.BROKER_TYPE.lower()
        try:
            if broker_type == "miniqmt":
                from trading.miniqmt_trader import MiniQMTBroker
                return MiniQMTBroker()
            else:
                # universal_client / ths_client 等走桥接服务（32位Python代理）
                from trading.bridge_broker import BridgeBroker
                return BridgeBroker()
        except Exception as e:
            logger.error(f"[引擎] 创建实盘Broker失败: {e}")
            return None

    # ── 分析单支股票 ──────────────────────────────────────────────────────

    def analyze_symbol(self, symbol: str, user_context: dict = None) -> dict:
        from datetime import timedelta
        end_dt   = datetime.now().strftime("%Y%m%d")
        start_dt = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")

        df = get_historical_data(symbol, start_dt, end_dt)
        if df.empty:
            return {}

        df          = add_indicators(df)
        indicators  = get_latest_indicators(df)
        recent_bars = get_recent_bars(df, n=20)

        quote = get_realtime_quote(symbol)
        is_realtime = False
        data_date   = str(df.index[-1].date()) if not df.empty else ""
        if quote and quote.get("price", 0) > 0:
            indicators["price"] = quote["price"]
            name        = quote.get("name", symbol)
            is_realtime = quote.get("is_realtime", False)
            data_date   = quote.get("data_date", data_date)
        else:
            name = symbol

        # 如果实时行情获取不到名称，用baostock查
        if not name or name == symbol:
            try:
                from data.market_data import get_stock_name
                name = get_stock_name(symbol)
            except Exception:
                pass

        # 更新模拟持仓的当前价格
        if symbol in self.risk_manager.positions:
            self.risk_manager.positions[symbol]["current_price"] = indicators["price"]

        sentiment = get_stock_news_sentiment(symbol, limit=5)

        # ── 分时摘要：优先用实时行情的今日OHLC，再尝试分钟K ──────────────
        intraday_summary = {}

        # 第一优先：实时行情已包含今日开/高/低/现价（腾讯/新浪 API 直接提供）
        if quote and quote.get("open", 0) > 0:
            try:
                rt_price  = float(quote.get("price") or indicators.get("price", 0))
                rt_open   = float(quote.get("open",  0))
                rt_high   = float(quote.get("high",  0)) or rt_price
                rt_low    = float(quote.get("low",   0)) or rt_price
                rt_prev   = float(quote.get("prev_close", 0))

                if rt_price > 0 and rt_open > 0:
                    # 涨跌幅以昨收为基准（更准确）
                    base = rt_prev if rt_prev > 0 else rt_open
                    pct_chg = (rt_price - base) / base * 100

                    # 日内趋势：现价与开盘的偏差
                    dev = (rt_price - rt_open) / rt_open
                    trend = "上行" if dev > 0.003 else ("下行" if dev < -0.003 else "横盘")

                    intraday_summary = {
                        "open":               rt_open,
                        "high":               rt_high,
                        "low":                rt_low,
                        "latest":             rt_price,
                        "pct_change":         pct_chg,
                        "vol_ratio_intraday": 1.0,   # 实时行情无法精确计算量比，置1
                        "trend":              trend,
                    }
                    logger.debug(f"[{symbol}] 分时摘要来自实时行情: {rt_open}/{rt_high}/{rt_low}/{rt_price}")
            except Exception as e:
                logger.debug(f"[{symbol}] 实时行情构建分时摘要失败: {e}")

        # 第二优先：尝试获取今日分时K线（补充量比等信息）
        if not intraday_summary or intraday_summary.get("vol_ratio_intraday", 1.0) == 1.0:
            try:
                from data.market_data import get_minute_data_cached
                df_min = get_minute_data_cached(symbol, period="5", days=2)
                if not df_min.empty:
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    df_today = df_min[df_min.index.strftime("%Y-%m-%d") == today_str]
                    df_base  = df_min  # 全部用于算均量

                    if not df_today.empty:
                        # 今日数据存在，用分时K精确计算
                        open_price = float(df_today["open"].iloc[0])
                        high_price = float(df_today["high"].max())
                        low_price  = float(df_today["low"].min())
                        latest     = float(df_today["close"].iloc[-1])
                        base       = float(quote.get("prev_close", open_price)) if quote else open_price
                        pct_chg    = (latest - base) / base * 100 if base > 0 else 0

                        avg_vol    = float(df_base["volume"].mean()) if "volume" in df_base.columns else 0
                        recent_vol = float(df_today["volume"].iloc[-6:].mean()) if "volume" in df_today.columns and len(df_today) >= 6 else avg_vol
                        vol_ratio  = recent_vol / avg_vol if avg_vol > 0 else 1.0

                        closes = df_today["close"].values
                        if len(closes) >= 10:
                            recent_m = closes[-5:].mean()
                            prev_m   = closes[-10:-5].mean()
                            trend = "上行" if recent_m > prev_m * 1.002 else ("下行" if recent_m < prev_m * 0.998 else "横盘")
                        else:
                            trend = intraday_summary.get("trend", "数据不足")

                        intraday_summary.update({
                            "open":               open_price,
                            "high":               max(high_price, intraday_summary.get("high", 0)),
                            "low":                min(low_price,  intraday_summary.get("low",  999999)),
                            "latest":             latest,
                            "pct_change":         pct_chg,
                            "vol_ratio_intraday": vol_ratio,
                            "trend":              trend,
                        })
                        logger.debug(f"[{symbol}] 分时摘要已用今日分时K补充（量比={vol_ratio:.2f}）")
            except Exception as e:
                logger.debug(f"[{symbol}] 分时K获取失败（非关键）: {e}")

        # 传入当前持仓，让AI感知持仓状态
        current_position = self.risk_manager.positions.get(symbol)
        decision = get_ai_decision(
            symbol, indicators,
            sentiment.get("sentiment_text", "中性"),
            position=current_position,
            user_context=user_context,
            intraday_summary=intraday_summary if intraday_summary else None,
            recent_bars=recent_bars,
        )

        # 持仓中更新名称缓存
        try:
            from database import db
            if name and name != symbol:
                db.update_symbol_name(symbol, name)
        except Exception:
            pass

        return {
            "symbol":           symbol,
            "name":             name,
            "indicators":       indicators,
            "sentiment":        sentiment,
            "decision":         decision,
            "position":         current_position,
            "intraday_summary": intraday_summary,
            "is_realtime":      is_realtime,
            "data_date":        data_date,
            "timestamp":        datetime.now().isoformat(),
        }

    # ── 执行决策 ──────────────────────────────────────────────────────────

    def _execute(self, analysis: dict):
        if not analysis:
            return

        symbol     = analysis["symbol"]
        decision   = analysis["decision"]
        action     = decision.get("action", "HOLD").upper()
        confidence = float(decision.get("confidence", 0))
        price      = analysis["indicators"].get("price", 0)
        reason     = decision.get("reason", "")
        sig_str    = decision.get("signal_strength", "WEAK")
        risk_lvl   = decision.get("risk_level", "HIGH")

        if price <= 0:
            return

        # 先检查强制止损/止盈
        force_exit, force_reason = self.risk_manager.check_force_exit(symbol, price)
        if force_exit:
            if symbol in self.risk_manager.positions:
                pos = self.risk_manager.positions[symbol]
                result = self.broker.sell(symbol, price, pos["shares"])
                if result.get("success"):
                    pnl = result.get("pnl") or (
                        (price - pos["avg_cost"]) * pos["shares"]
                    )
                    pnl_r = pnl / pos.get("cost", price * pos["shares"] + 1e-10)
                    self._record_trade(symbol, "SELL(风控)", price, pos["shares"],
                                       pnl=pnl, pnl_ratio=pnl_r, reason=force_reason)
            return

        if action == "BUY":
            ok, msg, shares = self.risk_manager.check_buy(symbol, price, confidence)
            if ok:
                result = self.broker.buy(symbol, price, shares)
                if result.get("success"):
                    # PaperBroker 在 buy() 里已调用 open_position
                    if self.mode == "real":
                        self.risk_manager.open_position(symbol, price, shares)
                    self._record_trade(symbol, "BUY", price, shares,
                                       confidence=confidence, signal_strength=sig_str,
                                       risk_level=risk_lvl, reason=reason)
            else:
                logger.debug(f"[风控拒绝] {symbol} BUY: {msg}")

        elif action == "SELL" and symbol in self.risk_manager.positions:
            pos = self.risk_manager.positions[symbol]
            result = self.broker.sell(symbol, price, pos["shares"])
            if result.get("success"):
                if self.mode == "real":
                    self.risk_manager.close_position(symbol, price)
                pnl = result.get("pnl") or (
                    (price - pos["avg_cost"]) * pos["shares"]
                )
                pnl_r = pnl / pos.get("cost", price * pos["shares"] + 1e-10)
                self._record_trade(symbol, "SELL", price, pos["shares"],
                                   pnl=pnl, pnl_ratio=pnl_r, reason=reason)

    def _record_trade(self, symbol: str, action: str, price: float, shares: int, **kwargs):
        """写入数据库 + 交易日志"""
        db.insert_trade(
            symbol=symbol, action=action, price=price, shares=shares,
            mode=self.mode, **kwargs,
        )
        trade_logger.log({
            "symbol": symbol, "action": action,
            "price": price, "shares": shares,
            "amount": price * shares,
            "mode": self.mode,
            **kwargs,
        })
        # 推送 WebSocket 更新
        if self.push_callback:
            try:
                self.push_callback({
                    "type": "trade",
                    "symbol": symbol, "action": action,
                    "price": price, "shares": shares,
                    **{k: v for k, v in kwargs.items() if v is not None},
                })
            except Exception:
                pass

    # ── 一轮扫描 ──────────────────────────────────────────────────────────

    def run_once(self) -> List[dict]:
        results = []
        for sym in self.symbols:
            try:
                analysis = self.analyze_symbol(sym)
                if analysis:
                    self._execute(analysis)
                    self.latest_signals[sym] = analysis
                    results.append(analysis)
            except Exception as e:
                logger.error(f"[{sym}] 扫描异常: {e}", exc_info=True)

        # 推送 BUY 信号邮件通知
        try:
            from notify.email_notify import send_signal_email
            send_signal_email(results, source="监控扫描")
        except Exception as e:
            logger.debug(f"[通知] 邮件推送异常: {e}")

        # 保存组合快照
        try:
            prices = {s: a["indicators"]["price"]
                      for s, a in self.latest_signals.items()
                      if a.get("indicators", {}).get("price", 0) > 0}
            bal = self.broker.get_balance()
            total  = bal.get("total_asset", self.risk_manager.portfolio_value(prices))
            cash   = bal.get("available_cash", self.risk_manager.current_capital)
            pos_val = total - cash
            pnl    = total - config.INITIAL_CAPITAL
            ret    = pnl / config.INITIAL_CAPITAL
            db.insert_snapshot(total, cash, pos_val, total_pnl=pnl, total_return=ret, mode=self.mode)

            if self.push_callback:
                self.push_callback({
                    "type": "portfolio",
                    "total_asset": total,
                    "cash": cash,
                    "positions_value": pos_val,
                    "total_pnl": pnl,
                    "total_return": ret,
                })
        except Exception as e:
            logger.warning(f"快照保存失败: {e}")

        return results

    # ── 持续运行 ──────────────────────────────────────────────────────────

    def _run_loop(self):
        logger.info(f"[引擎] 启动 mode={self.mode} interval={self.interval}s")
        while self.running:
            if _in_trading_hours():
                logger.info("── 新一轮扫描 ──")
                self.run_once()
                time.sleep(self.interval)
            else:
                # 非交易时段：检查是否刚收盘，发送日报
                try:
                    from notify.email_notify import check_and_send_daily_summary
                    check_and_send_daily_summary(self)
                except Exception as e:
                    logger.debug(f"[日报] 检查异常: {e}")
                logger.debug("非交易时段，休眠…")
                time.sleep(300)

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        logger.info("[引擎] 已停止")

    def add_symbol(self, symbol: str):
        if symbol not in self.symbols:
            self.symbols.append(symbol)
            db.add_symbol(symbol)

    def remove_symbol(self, symbol: str):
        self.symbols = [s for s in self.symbols if s != symbol]
        db.remove_symbol(symbol)

    def get_status(self) -> dict:
        bal   = self.broker.get_balance()
        # 按当前模式过滤今日统计，避免模拟盘/实盘数据混合
        stats = db.get_trade_stats(mode=self.mode)
        total = bal.get("total_asset", config.INITIAL_CAPITAL)
        init  = config.INITIAL_CAPITAL
        pnl   = round(total - init, 2)
        return {
            "running":         self.running,
            "mode":            self.mode,
            "symbols":         self.symbols,
            "total_asset":     total,
            "cash":            bal.get("available_cash", 0),
            "positions_value": bal.get("market_value", 0),
            "today_trades":    self.risk_manager.today_trades,
            "today_pnl":       stats.get("total_pnl", 0),
            "total_pnl":       pnl,
            "total_return":    round(pnl / init, 4) if init > 0 else 0,
            "initial_capital": init,
            "positions":       self.broker.get_positions(),
        }
