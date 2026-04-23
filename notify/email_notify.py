"""
邮件推送模块
支持 QQ邮箱（smtp.qq.com）、Gmail、163邮箱等
- BUY信号推送（多股票合并一封，竖向卡片布局，手机友好）
- AI接口连续失败告警
- 每日收盘概要
"""
import logging
import smtplib
import ssl
from datetime import datetime, timedelta
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

import config

logger = logging.getLogger(__name__)

# ── 去重缓存 ─────────────────────────────────────────────────────────────
_sent_cache: Dict[str, dict] = {}


def _cooldown() -> int:
    return int(getattr(config, "NOTIFY_COOLDOWN_MINUTES", 60))


def _should_send(symbol: str, action: str) -> bool:
    key = f"{symbol}:{action}"
    entry = _sent_cache.get(key)
    if entry:
        if datetime.now() - entry["sent_at"] < timedelta(minutes=_cooldown()):
            return False
    return True


def _mark_sent(symbol: str, action: str):
    _sent_cache[f"{symbol}:{action}"] = {"sent_at": datetime.now()}


# ── 底层发送 ─────────────────────────────────────────────────────────────

def _smtp_send(subject: str, html_body: str, extra_receivers: list = None):
    """
    单次 SMTP 发送，支持 SSL(465) 和 STARTTLS(587)。
    extra_receivers: 额外抄送地址列表（不为空时合并到 To 头）
    """
    primary = config.EMAIL_RECEIVER
    recipients = [primary]
    if extra_receivers:
        recipients += [r for r in extra_receivers if r and r != primary]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = config.EMAIL_SENDER
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    host = getattr(config, "EMAIL_SMTP_HOST", "smtp.qq.com")
    port = int(getattr(config, "EMAIL_SMTP_PORT", 465))

    if port == 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
            s.login(config.EMAIL_SENDER, config.EMAIL_SENDER_PASS)
            s.sendmail(config.EMAIL_SENDER, recipients, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.ehlo(); s.starttls(); s.login(config.EMAIL_SENDER, config.EMAIL_SENDER_PASS)
            s.sendmail(config.EMAIL_SENDER, recipients, msg.as_string())


def _buy_extra() -> list:
    """返回只收 BUY 的副收件人列表"""
    r1 = getattr(config, "EMAIL_RECEIVER1", "").strip()
    return [r1] if r1 else []


# ── 公共 HTML 外壳 ────────────────────────────────────────────────────────

_CSS = """
body{margin:0;padding:12px;background:#f2f2f7;font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif}
.wrap{max-width:480px;margin:auto}
.header{background:#1c7a3e;color:#fff;border-radius:10px 10px 0 0;padding:14px 16px}
.header h2{margin:0;font-size:18px}
.header p{margin:4px 0 0;font-size:12px;opacity:.8}
.card{background:#fff;border-radius:10px;margin:10px 0;padding:14px 16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.card.buy{border-left:4px solid #1c7a3e}
.card.sell{border-left:4px solid #c0392b}
.card.alert{border-left:4px solid #e67e22}
.card.summary{border-left:4px solid #2980b9}
.sym{font-size:16px;font-weight:700;color:#111}
.name{font-size:12px;color:#888;margin-left:4px}
.badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;margin:6px 0}
.badge.BUY{background:#d4edda;color:#1c7a3e}
.badge.SELL{background:#f8d7da;color:#c0392b}
.badge.HOLD{background:#fff3cd;color:#856404}
.row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f0f0f0;font-size:13px}
.row:last-child{border-bottom:none}
.label{color:#888}
.val{font-weight:600;color:#222;text-align:right}
.reason{background:#f9f9f9;border-radius:6px;padding:8px 10px;margin-top:8px;font-size:12px;color:#444;line-height:1.6}
.footer{text-align:center;font-size:11px;color:#aaa;padding:8px 0 4px}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}
.stat-box{background:#f9f9f9;border-radius:8px;padding:10px;text-align:center}
.stat-num{font-size:22px;font-weight:700;color:#111}
.stat-lbl{font-size:11px;color:#888;margin-top:2px}
"""

def _wrap(title: str, subtitle: str, body_html: str, color: str = "#1c7a3e") -> str:
    hdr_style = f"background:{color}"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{_CSS}</style></head><body>
<div class="wrap">
  <div class="header" style="{hdr_style}">
    <h2>{title}</h2><p>{subtitle}</p>
  </div>
  {body_html}
  <div class="footer">此邮件由量化交易Agent自动发出，仅供参考，不构成投资建议。</div>
</div></body></html>"""


# ── BUY 信号推送 ──────────────────────────────────────────────────────────

def _sig_card(sig: dict) -> str:
    """单支股票的竖向卡片 HTML"""
    d   = sig.get("decision") or sig
    ind = sig.get("indicators") or {}

    symbol      = sig.get("symbol", "")
    name        = sig.get("name", symbol)
    sector      = sig.get("sector", "")
    action      = d.get("action",          sig.get("action",          "HOLD"))
    confidence  = d.get("confidence",      sig.get("confidence",      0))
    strength    = d.get("signal_strength", sig.get("signal_strength", ""))
    risk        = d.get("risk_level",      sig.get("risk_level",      ""))
    reason      = d.get("reason",          sig.get("reason",          ""))
    pos_advice  = d.get("position_advice", sig.get("position_advice", ""))
    price       = ind.get("price",    d.get("price",    sig.get("price",    0)))
    stop_loss   = d.get("stop_loss",       sig.get("stop_loss"))
    take_profit = d.get("take_profit",     sig.get("take_profit"))
    sl_pct      = d.get("stop_loss_pct",   sig.get("stop_loss_pct"))
    tp_pct      = d.get("take_profit_pct", sig.get("take_profit_pct"))

    def _price_str(p, pct):
        if p and pct:
            return f"{p:.3f}（{pct:+.1f}%）"
        return f"{p:.3f}" if p else "—"

    sector_html = f'<span style="font-size:11px;color:#2980b9;margin-left:6px">[{sector}]</span>' if sector else ""
    rows = [
        ("现价",   f"{price:.3f}" if price else "—"),
        ("置信度", f"{confidence:.0%}  {strength}"),
        ("风险等级", risk),
        ("止损价", _price_str(stop_loss, sl_pct)),
        ("止盈价", _price_str(take_profit, tp_pct)),
        ("仓位建议", pos_advice or "—"),
    ]
    rows_html = "".join(
        f'<div class="row"><span class="label">{k}</span><span class="val">{v}</span></div>'
        for k, v in rows
    )
    reason_html = f'<div class="reason">💬 {reason}</div>' if reason else ""
    return f"""
<div class="card {action}">
  <div><span class="sym">{symbol}</span><span class="name">{name}</span>{sector_html}</div>
  <div><span class="badge {action}">{action}</span></div>
  {rows_html}
  {reason_html}
</div>"""


def send_holding_sell_email(signals: list):
    """
    持仓卖出信号：红色卡片，24小时内同一股票只发一次。
    """
    if not getattr(config, "EMAIL_ENABLED", False):
        return
    to_notify = []
    for sig in signals:
        symbol = sig.get("symbol", "")
        # 卖出信号冷却24小时
        key = f"{symbol}:SELL_HOLD"
        entry = _sent_cache.get(key)
        if entry and datetime.now() - entry["sent_at"] < timedelta(hours=24):
            continue
        to_notify.append(sig)

    if not to_notify:
        return

    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        # 卖出卡片：红色主题
        cards = ""
        for sig in to_notify:
            d   = sig.get("decision") or sig
            ind = sig.get("indicators") or {}
            symbol   = sig.get("symbol", "")
            name     = sig.get("name", symbol)
            price    = ind.get("price", d.get("price", 0))
            cost     = sig.get("holding_cost", 0)
            shares   = sig.get("holding_shares", 0)
            reason   = d.get("reason", sig.get("reason", ""))
            pos_adv  = d.get("position_advice", sig.get("position_advice", ""))
            pnl_pct  = (price - cost) / cost * 100 if cost > 0 and price > 0 else 0
            pnl_color = "#c0392b" if pnl_pct < 0 else "#1c7a3e"
            cards += f"""
<div class="card sell">
  <div><span class="sym">{symbol}</span><span class="name">{name}</span>
    <span style="font-size:11px;color:#c0392b;font-weight:700;margin-left:6px">⚠️ 持仓卖出提醒</span></div>
  <div><span class="badge SELL">SELL</span></div>
  <div class="row"><span class="label">持仓</span><span class="val">{shares:.0f} 股  均价 {cost:.3f}</span></div>
  <div class="row"><span class="label">现价</span><span class="val">{price:.3f}</span></div>
  <div class="row"><span class="label">浮盈亏</span><span class="val" style="color:{pnl_color}">{pnl_pct:+.2f}%</span></div>
  <div class="row"><span class="label">建议</span><span class="val">{pos_adv or '减仓/清仓'}</span></div>
  <div class="reason">💬 {reason}</div>
</div>"""

        body = _wrap("⚠️ 持仓卖出提醒", f"共 {len(to_notify)} 支 · {now_str}", cards, color="#c0392b")
        _smtp_send(f"【量化警告】持仓SELL信号 {len(to_notify)}支 {now_str}", body)

        for sig in to_notify:
            _sent_cache[f"{sig.get('symbol','')}:SELL_HOLD"] = {"sent_at": datetime.now()}
        logger.info(f"[通知] 持仓SELL邮件已发 {len(to_notify)} 支")
    except Exception as e:
        logger.error(f"[通知] 持仓SELL邮件失败: {e}")


def send_signal_email(signals: list, source: str = "监控扫描"):
    """发送 BUY 信号邮件（多股合并一封）"""
    if not getattr(config, "EMAIL_ENABLED", False):
        return
    if not signals:
        return

    to_notify: List[dict] = []
    for sig in signals:
        d = sig.get("decision") or sig
        action     = d.get("action",     sig.get("action",     ""))
        confidence = d.get("confidence", sig.get("confidence", 0))
        symbol     = sig.get("symbol", "")
        if action != "BUY":
            continue
        if confidence < getattr(config, "NOTIFY_MIN_CONFIDENCE", 0.55):
            continue
        if not _should_send(symbol, action):
            continue
        to_notify.append(sig)

    if not to_notify:
        return

    try:
        now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")
        cards    = "".join(_sig_card(s) for s in to_notify)
        body     = _wrap(
            title    = f"📈 BUY信号提醒  {len(to_notify)}支",
            subtitle = f"来源：{source} · {now_str}",
            body_html= cards,
            color    = "#1c7a3e",
        )
        subject = f"【量化】{source} BUY信号 {len(to_notify)}支 {now_str}"
        _smtp_send(subject, body, extra_receivers=_buy_extra())
        for sig in to_notify:
            _mark_sent(sig.get("symbol", ""), "BUY")
        logger.info(f"[通知] BUY信号邮件已发 {len(to_notify)} 支（{source}）")
    except Exception as e:
        logger.error(f"[通知] BUY信号邮件发送失败: {e}")


# ── AI 接口连续失败告警 ───────────────────────────────────────────────────

_ai_fail_count: int = 0
_ai_alert_sent_at: Optional[datetime] = None
AI_FAIL_THRESHOLD  = 10       # 连续失败次数阈值
AI_ALERT_COOLDOWN  = 120      # 告警冷却分钟数


def notify_ai_success():
    """AI调用成功时重置计数器"""
    global _ai_fail_count
    _ai_fail_count = 0


def notify_ai_failure(error_msg: str = ""):
    """AI调用失败时累加计数，达到阈值发送告警邮件"""
    global _ai_fail_count, _ai_alert_sent_at
    _ai_fail_count += 1
    logger.debug(f"[AI告警] 连续失败 {_ai_fail_count} 次")

    if _ai_fail_count < AI_FAIL_THRESHOLD:
        return
    if not getattr(config, "EMAIL_ENABLED", False):
        return

    # 告警冷却（避免频繁发送）
    if _ai_alert_sent_at:
        if datetime.now() - _ai_alert_sent_at < timedelta(minutes=AI_ALERT_COOLDOWN):
            return

    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        card = f"""
<div class="card alert">
  <div class="sym">⚠️ AI接口连续调用失败</div>
  <div class="row"><span class="label">连续失败次数</span><span class="val" style="color:#e67e22">{_ai_fail_count} 次</span></div>
  <div class="row"><span class="label">最近错误信息</span><span class="val">{error_msg[:80] or '无'}</span></div>
  <div class="row"><span class="label">告警时间</span><span class="val">{now_str}</span></div>
  <div class="reason">💡 请检查 AI API Key 余额（Token 是否耗尽），或登录 yunwu.ai 充值。</div>
</div>"""
        body = _wrap(
            title    = "⚠️ AI接口异常告警",
            subtitle = f"连续失败 {_ai_fail_count} 次 · {now_str}",
            body_html= card,
            color    = "#e67e22",
        )
        _smtp_send(f"【量化告警】AI接口连续失败 {_ai_fail_count} 次", body)
        _ai_alert_sent_at = datetime.now()
        logger.warning(f"[通知] AI告警邮件已发送，连续失败 {_ai_fail_count} 次")
    except Exception as e:
        logger.error(f"[通知] AI告警邮件发送失败: {e}")


# ── 每日收盘概要 ─────────────────────────────────────────────────────────

_daily_summary_sent_date: Optional[str] = None   # 记录已发送日期，避免重复


def send_daily_summary(signals: dict, portfolio: dict = None, source: str = ""):
    """
    发送每日收盘概要邮件，并记录日志。
    signals  : {symbol: analysis_dict} 当日所有分析结果
    portfolio: 当日组合快照 dict（可选）
    source   : 附加说明
    """
    global _daily_summary_sent_date
    if not getattr(config, "EMAIL_ENABLED", False):
        return

    today = datetime.now().strftime("%Y-%m-%d")
    if _daily_summary_sent_date == today:
        logger.debug("[日报] 今日概要已发送，跳过")
        return

    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        results = [v for v in signals.values() if v]

        # ── 统计 ─────────────────────────────────────────────────────────
        buy_sigs  = [r for r in results if r.get("decision", {}).get("action") == "BUY"]
        sell_sigs = [r for r in results if r.get("decision", {}).get("action") == "SELL"]
        hold_sigs = [r for r in results if r.get("decision", {}).get("action") == "HOLD"]

        # 置信度最高的 BUY 信号排序
        top_buys = sorted(buy_sigs, key=lambda r: r.get("decision", {}).get("confidence", 0), reverse=True)[:5]

        # ── 日志记录 ──────────────────────────────────────────────────────
        log_lines = [
            f"{'='*55}",
            f"  每日收盘概要  {today}",
            f"{'='*55}",
            f"  扫描标的: {len(results)} 支",
            f"  BUY信号:  {len(buy_sigs)} 支  |  SELL: {len(sell_sigs)} 支  |  HOLD: {len(hold_sigs)} 支",
        ]
        if portfolio:
            total = portfolio.get("total_asset", 0)
            pnl   = portfolio.get("total_pnl", 0)
            ret   = portfolio.get("total_return", 0)
            log_lines += [
                f"  总资产:   {total:,.0f} 元",
                f"  当日盈亏: {pnl:+,.0f} 元  ({ret:+.2%})",
            ]
        if top_buys:
            log_lines.append("  ── 今日BUY信号 ──")
            for r in top_buys:
                d = r.get("decision", {})
                log_lines.append(
                    f"    {r['symbol']} {r.get('name','')}  "
                    f"置信:{d.get('confidence',0):.0%}  "
                    f"止损:{d.get('stop_loss') or '—'}  止盈:{d.get('take_profit') or '—'}"
                )
        log_lines.append(f"{'='*55}")
        log_text = "\n".join(log_lines)

        # 写入日志文件
        import os
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"daily_{today.replace('-','')}.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_text + "\n")
        logger.info(f"[日报] 当日概要已写入 {log_file}")

        # ── 构建邮件 ──────────────────────────────────────────────────────
        stat_html = f"""
<div class="card summary">
  <div class="sym">📊 {today} 收盘概要</div>
  <div class="stat-grid" style="margin-top:10px">
    <div class="stat-box"><div class="stat-num">{len(results)}</div><div class="stat-lbl">扫描标的</div></div>
    <div class="stat-box"><div class="stat-num" style="color:#1c7a3e">{len(buy_sigs)}</div><div class="stat-lbl">BUY信号</div></div>
    <div class="stat-box"><div class="stat-num" style="color:#c0392b">{len(sell_sigs)}</div><div class="stat-lbl">SELL信号</div></div>
    <div class="stat-box"><div class="stat-num" style="color:#856404">{len(hold_sigs)}</div><div class="stat-lbl">HOLD观望</div></div>
  </div>
</div>"""

        portfolio_html = ""
        if portfolio:
            total = portfolio.get("total_asset", 0)
            pnl   = portfolio.get("total_pnl", 0)
            ret   = portfolio.get("total_return", 0)
            pnl_color = "#1c7a3e" if pnl >= 0 else "#c0392b"
            portfolio_html = f"""
<div class="card summary">
  <div class="sym">💼 模拟组合快照</div>
  <div class="row"><span class="label">总资产</span><span class="val">¥{total:,.0f}</span></div>
  <div class="row"><span class="label">累计盈亏</span><span class="val" style="color:{pnl_color}">{pnl:+,.0f} 元（{ret:+.2%}）</span></div>
</div>"""

        buy_cards_html = ""
        if top_buys:
            buy_cards_html = '<div class="sym" style="padding:4px 0 6px;color:#1c7a3e;font-size:13px">📈 今日BUY信号（按置信度）</div>'
            buy_cards_html += "".join(_sig_card(r) for r in top_buys)

        body = _wrap(
            title    = f"📋 每日收盘概要",
            subtitle = f"{today} 收盘 · {now_str}",
            body_html= stat_html + portfolio_html + buy_cards_html,
            color    = "#2980b9",
        )
        _smtp_send(f"【量化日报】{today} 收盘概要 BUY{len(buy_sigs)}支", body)
        _daily_summary_sent_date = today
        logger.info(f"[日报] 邮件已发送: {today}")

    except Exception as e:
        logger.error(f"[日报] 发送失败: {e}")


def check_and_send_daily_summary(engine):
    """
    检查是否到收盘时间，到则发送日报。
    在后台线程中定期调用（由 engine 的调度循环负责）。
    """
    from datetime import time as dtime
    now = datetime.now()
    # 周一至周五，15:05 之后
    if now.weekday() >= 5:
        return
    if now.time() < dtime(15, 5):
        return
    send_daily_summary(
        signals   = engine.latest_signals,
        portfolio = engine.broker.get_balance() if hasattr(engine, "broker") else None,
    )


# ── 测试邮件 ─────────────────────────────────────────────────────────────

def _check_enabled():
    if not getattr(config, "EMAIL_ENABLED", False):
        return False, "EMAIL_ENABLED = False，请先在 config 中启用"
    return True, ""


def send_test_email():
    """测试 BUY 信号邮件"""
    ok, msg = _check_enabled()
    if not ok:
        return False, msg
    try:
        fake = [{
            "symbol": "000001", "name": "平安银行", "sector": "银行/金融",
            "action": "BUY", "confidence": 0.75,
            "signal_strength": "MEDIUM", "risk_level": "MEDIUM",
            "reason": "这是一封测试邮件，卡片式布局，手机友好！均线多头排列，量比放大，RSI合理区间。",
            "stop_loss": 9.50, "take_profit": 11.20,
            "stop_loss_pct": -5.0, "take_profit_pct": 12.0,
            "position_advice": "轻仓试探 30%",
            "indicators": {"price": 10.00},
        }]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        cards = "".join(_sig_card(s) for s in fake)
        body = _wrap("📈 BUY信号提醒（测试）", f"测试邮件 · {now_str}", cards)
        _smtp_send("【量化测试】BUY信号邮件验证", body, extra_receivers=_buy_extra())
        extra = _buy_extra()
        note = f"（同时发送至 {extra[0]}）" if extra else ""
        return True, f"BUY信号测试邮件发送成功{note}，请检查收件箱"
    except Exception as e:
        return False, f"发送失败: {e}"


def send_test_sell_email():
    """测试持仓 SELL 信号邮件"""
    ok, msg = _check_enabled()
    if not ok:
        return False, msg
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        fake_sell = [{
            "symbol": "600519", "name": "贵州茅台",
            "decision": {"action": "SELL", "reason": "MACD死叉，量能萎缩，建议减仓止盈。（测试邮件）",
                         "position_advice": "减仓 50% 或设止损清仓"},
            "indicators": {"price": 1680.00},
            "holding_shares": 10,
            "holding_cost": 1500.00,
        }]
        # 直接构建 HTML，绕过24h冷却
        cards = ""
        for sig in fake_sell:
            d       = sig.get("decision", {})
            ind     = sig.get("indicators", {})
            symbol  = sig.get("symbol", "")
            name    = sig.get("name", symbol)
            price   = ind.get("price", 0)
            cost    = sig.get("holding_cost", 0)
            shares  = sig.get("holding_shares", 0)
            reason  = d.get("reason", "")
            pos_adv = d.get("position_advice", "")
            pnl_pct = (price - cost) / cost * 100 if cost > 0 and price > 0 else 0
            pnl_color = "#c0392b" if pnl_pct < 0 else "#1c7a3e"
            cards += f"""
<div class="card sell">
  <div><span class="sym">{symbol}</span><span class="name">{name}</span>
    <span style="font-size:11px;color:#c0392b;font-weight:700;margin-left:6px">⚠️ 持仓卖出提醒（测试）</span></div>
  <div><span class="badge SELL">SELL</span></div>
  <div class="row"><span class="label">持仓</span><span class="val">{shares:.0f} 股  均价 {cost:.3f}</span></div>
  <div class="row"><span class="label">现价</span><span class="val">{price:.3f}</span></div>
  <div class="row"><span class="label">浮盈亏</span><span class="val" style="color:{pnl_color}">{pnl_pct:+.2f}%</span></div>
  <div class="row"><span class="label">建议</span><span class="val">{pos_adv or '减仓/清仓'}</span></div>
  <div class="reason">💬 {reason}</div>
</div>"""
        body = _wrap("⚠️ 持仓卖出提醒（测试）", f"1支 · {now_str}", cards, color="#c0392b")
        _smtp_send("【量化测试】持仓SELL信号邮件验证", body)
        return True, "持仓SELL测试邮件发送成功，请检查收件箱"
    except Exception as e:
        return False, f"发送失败: {e}"


def send_test_ai_fail_email():
    """测试 AI 接口失败告警邮件"""
    ok, msg = _check_enabled()
    if not ok:
        return False, msg
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        fake_count = 10
        fake_err = "HTTPError 429: Too Many Requests / insufficient_quota"
        card = f"""
<div class="card alert">
  <div class="sym">⚠️ AI接口连续调用失败（测试）</div>
  <div class="row"><span class="label">连续失败次数</span><span class="val" style="color:#e67e22">{fake_count} 次</span></div>
  <div class="row"><span class="label">最近错误信息</span><span class="val">{fake_err}</span></div>
  <div class="row"><span class="label">告警时间</span><span class="val">{now_str}</span></div>
  <div class="reason">💡 请检查 AI API Key 余额（Token 是否耗尽），或登录 yunwu.ai 充值。（测试邮件）</div>
</div>"""
        body = _wrap(
            title    = "⚠️ AI接口异常告警（测试）",
            subtitle = f"连续失败 {fake_count} 次 · {now_str}",
            body_html= card,
            color    = "#e67e22",
        )
        _smtp_send("【量化测试】AI告警邮件验证", body)
        return True, "AI告警测试邮件发送成功，请检查收件箱"
    except Exception as e:
        return False, f"发送失败: {e}"


def send_test_daily_email():
    """测试每日收盘概要邮件"""
    ok, msg = _check_enabled()
    if not ok:
        return False, msg
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        # 构造假信号数据
        fake_signals = {
            "000001": {
                "symbol": "000001", "name": "平安银行",
                "decision": {"action": "BUY",  "confidence": 0.78, "stop_loss": 9.5, "take_profit": 11.2,
                             "reason": "均线多头，RSI适中，量比放大。（测试数据）"},
            },
            "600036": {
                "symbol": "600036", "name": "招商银行",
                "decision": {"action": "BUY",  "confidence": 0.70, "stop_loss": 35.0, "take_profit": 42.0,
                             "reason": "MACD金叉确认，价格站上MA20。（测试数据）"},
            },
            "300750": {
                "symbol": "300750", "name": "宁德时代",
                "decision": {"action": "HOLD", "confidence": 0.55, "reason": "横盘震荡，等待方向选择。（测试数据）"},
            },
            "600519": {
                "symbol": "600519", "name": "贵州茅台",
                "decision": {"action": "SELL", "confidence": 0.65, "reason": "MACD死叉，高位放量下跌。（测试数据）"},
            },
        }
        results = [v for v in fake_signals.values()]
        buy_sigs  = [r for r in results if r.get("decision", {}).get("action") == "BUY"]
        sell_sigs = [r for r in results if r.get("decision", {}).get("action") == "SELL"]
        hold_sigs = [r for r in results if r.get("decision", {}).get("action") == "HOLD"]
        top_buys  = sorted(buy_sigs, key=lambda r: r.get("decision", {}).get("confidence", 0), reverse=True)[:5]

        stat_html = f"""
<div class="card summary">
  <div class="sym">📊 {today} 收盘概要（测试）</div>
  <div class="stat-grid" style="margin-top:10px">
    <div class="stat-box"><div class="stat-num">{len(results)}</div><div class="stat-lbl">扫描标的</div></div>
    <div class="stat-box"><div class="stat-num" style="color:#1c7a3e">{len(buy_sigs)}</div><div class="stat-lbl">BUY信号</div></div>
    <div class="stat-box"><div class="stat-num" style="color:#c0392b">{len(sell_sigs)}</div><div class="stat-lbl">SELL信号</div></div>
    <div class="stat-box"><div class="stat-num" style="color:#856404">{len(hold_sigs)}</div><div class="stat-lbl">HOLD观望</div></div>
  </div>
</div>"""
        buy_cards_html = ""
        if top_buys:
            buy_cards_html = '<div class="sym" style="padding:4px 0 6px;color:#1c7a3e;font-size:13px">📈 今日BUY信号（按置信度）</div>'
            buy_cards_html += "".join(_sig_card(r) for r in top_buys)

        body = _wrap(
            title    = "📋 每日收盘概要（测试）",
            subtitle = f"{today} 收盘 · {now_str}",
            body_html= stat_html + buy_cards_html,
            color    = "#2980b9",
        )
        _smtp_send(f"【量化测试】每日日报邮件验证 BUY{len(buy_sigs)}支", body)
        return True, "每日日报测试邮件发送成功，请检查收件箱"
    except Exception as e:
        return False, f"发送失败: {e}"
