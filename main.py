#!/usr/bin/env python3
"""
量化交易 Agent  -  主程序
============================================================
用法:
  python main.py analyze 000001 600036       # 分析股票，获取AI决策
  python main.py backtest 000001             # 回测（默认近5年）
  python main.py backtest 000001 --start 20200101 --end 20241231
  python main.py paper 000001 600036         # 启动模拟盘
  python main.py paper 000001 --once         # 模拟盘只跑一轮（测试）
"""

'''  # 分析股票，获取AI交易信号
  python -X utf8 main.py analyze 000001 600519
  # 5年历史回测
  python -X utf8 main.py backtest 300750 --start 20200101 --end 20251231
  # 启动模拟盘（持续运行，60秒扫描一次）
  python -X utf8 main.py paper 000001 600519 300750
  # 模拟盘只跑一轮（测试用）
  python -X utf8 main.py paper 000001 --once'''

import argparse
import logging
import os
import sys

# 强制 stdout/stderr 使用 UTF-8（解决 Windows GBK 终端乱码）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── 日志配置 ──────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/trading.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

# ── 启动检查 ──────────────────────────────────────────────────────────────
import config  # noqa: E402

if not config.AI_API_KEY:
    print("[错误] .env 中未配置 AI_API_KEY，请先填写后再运行")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════
# 子命令：analyze
# ══════════════════════════════════════════════════════════════════════════
def cmd_analyze(symbols: list):
    from datetime import datetime, timedelta

    from ai_decision.agent import get_ai_decision
    from data.market_data import get_historical_data, get_realtime_quote
    from data.news_sentiment import get_stock_news_sentiment
    from indicators.technical import add_indicators, get_latest_indicators

    if not symbols:
        symbols = config.DEFAULT_SYMBOLS

    print(f"\n{'='*62}")
    print(f"  AI 交易信号分析   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*62}")

    for symbol in symbols:
        print(f"\n>> 股票 {symbol}")
        end_dt   = datetime.now().strftime("%Y%m%d")
        start_dt = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")

        df = get_historical_data(symbol, start_dt, end_dt)
        if df.empty:
            print(f"  [!] 无法获取数据，跳过")
            continue

        df         = add_indicators(df)
        indicators = get_latest_indicators(df)

        quote = get_realtime_quote(symbol)
        if quote and quote.get("price", 0) > 0:
            indicators["price"] = quote["price"]
            name = quote.get("name", symbol)
        else:
            name = symbol

        sentiment = get_stock_news_sentiment(symbol, limit=5)
        decision  = get_ai_decision(symbol, indicators, sentiment.get("sentiment_text", "中性"))

        action = decision.get("action", "HOLD")
        color  = {"BUY": "32", "SELL": "31", "HOLD": "33"}.get(action, "0")

        print(f"  股票名称: {name}")
        print(f"  当前价格: {indicators.get('price')}  |  MA5:{indicators.get('ma5')}  MA20:{indicators.get('ma20')}  MA60:{indicators.get('ma60')}")
        print(f"  RSI:{indicators.get('rsi')}  |  MACD DIF:{indicators.get('macd_dif')}  DEA:{indicators.get('macd_dea')}  柱:{indicators.get('macd_hist')}")
        print(f"  量比:{indicators.get('vol_ratio')}  |  情绪:{sentiment.get('sentiment_text', 'N/A')}")
        print(f"  \033[{color}m决策: {action}  置信:{decision.get('confidence', 0):.0%}  强度:{decision.get('signal_strength')}\033[0m")
        print(f"  风险:{decision.get('risk_level')}  |  原因: {decision.get('reason')}")

    print(f"\n{'='*62}\n")


# ══════════════════════════════════════════════════════════════════════════
# 子命令：backtest
# ══════════════════════════════════════════════════════════════════════════
def cmd_backtest(symbols: list, start_date: str, end_date: str):
    from backtest.strategy import run_backtest
    from reports.report_generator import backtest_report, save_report

    if not symbols:
        symbols = config.DEFAULT_SYMBOLS

    for symbol in symbols:
        print(f"\n正在回测 {symbol} …")
        result = run_backtest(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_cash=config.INITIAL_CAPITAL,
        )
        if "error" in result:
            print(f"[错误] {result['error']}")
            continue

        report_text = backtest_report(result)
        save_report(report_text, filename=f"backtest_{symbol}.txt")


# ══════════════════════════════════════════════════════════════════════════
# 子命令：paper
# ══════════════════════════════════════════════════════════════════════════
def cmd_paper(symbols: list, interval: int, once: bool):
    from reports.report_generator import portfolio_report, save_report
    from trading.paper_trader import PaperTrader

    if not symbols:
        symbols = config.DEFAULT_SYMBOLS

    trader = PaperTrader(symbols=symbols, initial_capital=config.INITIAL_CAPITAL)
    print(f"模拟盘启动  标的: {', '.join(symbols)}")
    print("按 Ctrl+C 停止\n")

    try:
        if once:
            trader.run_once()
        else:
            trader.run(interval=interval)
    except KeyboardInterrupt:
        print("\n[已停止]")

    report_text = portfolio_report(trader.risk_manager, trader.trade_log)
    save_report(report_text, filename=f"paper_report_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")


# ══════════════════════════════════════════════════════════════════════════
# 子命令：web
# ══════════════════════════════════════════════════════════════════════════
def cmd_web(port: int = 8888):
    import uvicorn
    from database import db

    # 写入默认监控标的
    if not db.get_symbols():
        for sym in config.DEFAULT_SYMBOLS:
            db.add_symbol(sym)

    print("=" * 55)
    print("  量化交易 Agent  Web 可视化管理平台")
    print(f"  浏览器访问: http://127.0.0.1:{port}")
    print(f"  API 文档:   http://127.0.0.1:{port}/docs")
    print()
    print("  [提示] 若浏览器显示502/无法访问：")
    print("  Clash 用户请在 Clash 设置中将 127.0.0.1 加入绕过列表")
    print("  或在浏览器地址栏直接输入 127.0.0.1:8888（而非localhost）")
    print("=" * 55)

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="量化交易 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # analyze
    p_a = sub.add_parser("analyze", help="分析股票并获取AI信号")
    p_a.add_argument("symbols", nargs="*", help="股票代码（不填则用默认列表）")

    # backtest
    p_b = sub.add_parser("backtest", help="策略回测")
    p_b.add_argument("symbols",    nargs="*",  help="股票代码")
    p_b.add_argument("--start",    default=None, help="开始日期 YYYYMMDD（默认近5年）")
    p_b.add_argument("--end",      default=None, help="结束日期 YYYYMMDD（默认今天）")

    # paper
    p_p = sub.add_parser("paper", help="模拟盘交易")
    p_p.add_argument("symbols",    nargs="*",  help="股票代码")
    p_p.add_argument("--interval", type=int,   default=60, help="扫描间隔秒数（默认60）")
    p_p.add_argument("--once",     action="store_true",    help="只执行一轮后退出")

    # web
    p_w = sub.add_parser("web", help="启动可视化 Web 应用")
    p_w.add_argument("--port", type=int, default=8888, help="端口（默认8888）")

    args = parser.parse_args()

    if args.cmd == "analyze":
        cmd_analyze(args.symbols)
    elif args.cmd == "backtest":
        cmd_backtest(args.symbols, args.start, args.end)
    elif args.cmd == "paper":
        cmd_paper(args.symbols, args.interval, args.once)
    elif args.cmd == "web":
        cmd_web(args.port)


if __name__ == "__main__":
    main()
