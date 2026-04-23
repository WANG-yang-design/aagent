"""
报告生成模块
生成回测报告、实时持仓报告，支持打印和保存
"""
import os
from datetime import datetime
from typing import List

from tabulate import tabulate


def backtest_report(result: dict) -> str:
    """打印并返回回测报告文本"""
    symbol      = result.get("symbol", "")
    start       = result.get("start_date", "")
    end         = result.get("end_date", "")
    init_cap    = result.get("initial_capital", 0)
    final_val   = result.get("final_value", 0)
    total_ret   = result.get("total_return", 0)
    annual_ret  = result.get("annual_return", 0)
    max_dd      = result.get("max_drawdown", 0)
    sharpe      = result.get("sharpe_ratio", 0)
    total_tr    = result.get("total_trades", 0)
    won         = result.get("won_trades", 0)
    lost        = result.get("lost_trades", 0)
    win_rate    = result.get("win_rate", 0)

    hit_target = "✓ 达标" if annual_ret >= 0.20 else "✗ 未达标"

    lines = [
        "=" * 62,
        f"  量化交易Agent  回测报告",
        f"  股票: {symbol}   {start[:4]}-{start[4:6]}-{start[6:]} ~ {end[:4]}-{end[4:6]}-{end[6:]}",
        "=" * 62,
        f"  初始资金       {init_cap:>14,.2f}  元",
        f"  最终净值       {final_val:>14,.2f}  元",
        f"  总收益率       {total_ret:>13.2%}",
        f"  年化收益率     {annual_ret:>13.2%}   (目标≥20% {hit_target})",
        f"  最大回撤       {max_dd:>13.2%}",
        f"  夏普比率       {sharpe:>14.3f}",
        "  " + "-" * 46,
        f"  总交易次数     {total_tr:>14d}",
        f"  盈利笔数       {won:>14d}",
        f"  亏损笔数       {lost:>14d}",
        f"  胜率           {win_rate:>13.2%}",
        "=" * 62,
    ]
    text = "\n".join(lines)
    print(text)
    return text


def portfolio_report(risk_manager, trade_log: List[dict]) -> str:
    """打印并返回当前持仓和交易记录报告"""
    s = risk_manager.summary()
    lines = [
        "=" * 62,
        f"  模拟盘实时报告   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 62,
        f"  可用现金:  {s['current_capital']:>12,.2f}  元",
        f"  持仓股票:  {s['positions']:>12d}  只",
        f"  今日交易:  {s['today_trades']:>12d}  次",
        f"  总盈亏:    {s['total_pnl']:>12,.2f}  元  ({s['total_return']:.2%})",
        "",
    ]

    # 持仓明细
    if risk_manager.positions:
        lines.append("【当前持仓】")
        rows = [
            [sym,
             pos["shares"],
             f"{pos['avg_cost']:.2f}",
             pos["entry_time"][:10],
             f"{pos['cost']:,.2f}"]
            for sym, pos in risk_manager.positions.items()
        ]
        lines.append(tabulate(rows, headers=["股票", "股数", "成本价", "建仓日", "投入资金"], tablefmt="simple"))
        lines.append("")

    # 交易记录（最近20条）
    if trade_log:
        lines.append(f"【交易记录】（共 {len(trade_log)} 条，显示最近20条）")
        recent = trade_log[-20:]
        rows = [
            [
                t.get("time", "")[:16],
                t.get("symbol", ""),
                t.get("action", ""),
                f"{t.get('price', 0):.2f}",
                t.get("shares", ""),
                f"{t.get('pnl', 0):.2f}" if "pnl" in t else "-",
                (t.get("reason") or "")[:22],
            ]
            for t in recent
        ]
        lines.append(tabulate(rows,
            headers=["时间", "股票", "操作", "价格", "股数", "盈亏", "原因"],
            tablefmt="simple"))

    text = "\n".join(lines)
    print(text)
    return text


def save_report(content: str, filename: str = None):
    """保存报告到 reports/ 目录"""
    os.makedirs("reports", exist_ok=True)
    if filename is None:
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    path = os.path.join("reports", filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"报告已保存: {path}")
    return path
