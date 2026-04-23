"""
AI 决策模块
调用 yunwu.ai /v1/responses 接口（OpenAI Responses API），
基于技术指标 + 近期K线 + 分时数据 + 用户自定义输入，生成 BUY / SELL / HOLD 信号
"""
import json
import logging
import re

import httpx

import config

logger = logging.getLogger(__name__)

# ── HTTP 客户端（全局复用，绕过系统代理）──────────────────────────────────────
_base = config.AI_BASE_URL.rstrip("/")
if _base.endswith("/v1"):
    _base = _base[:-3]
_RESPONSES_URL = f"{_base}/v1/responses"

_http = httpx.Client(
    proxy=None,
    trust_env=False,
    timeout=35,
    headers={
        "Authorization": f"Bearer {config.AI_API_KEY}",
        "Content-Type": "application/json",
    },
)


# ── 板块类型 ─────────────────────────────────────────────────────────────────

def _board_type(symbol: str) -> str:
    s = symbol.zfill(6)
    if s.startswith("688") or s.startswith("689"):
        return "科创板（高波动，止损可适当放宽至5~9%）"
    if s.startswith("300") or s.startswith("301"):
        return "创业板（高波动，止损可适当放宽至5~9%）"
    if s.startswith("83") or s.startswith("87") or s.startswith("43"):
        return "北交所（流动性较低，仓位宜轻）"
    if s.startswith("60") or s.startswith("68"):
        return "上交所主板（止损3~6%，止盈10~20%）"
    return "深交所主板（止损3~6%，止盈10~20%）"


# ── System Prompt（规则层，固定不变，可被模型缓存）──────────────────────────

_SYSTEM_PROMPT = """\
你是一个严格遵守纪律的A股量化交易顾问，专注波段操作和中短线交易。

## 核心理念
目标不是"预测涨跌"，而是：在高确定性机会时建议交易，不确定时观望，以提高长期胜率和风险收益比。
宁可错过，不可错判；仓位安全始终优先于潜在收益。

## 持仓决策规则
- 空仓状态：BUY=建仓，HOLD=继续观望，禁止输出SELL
- 有持仓状态：BUY=加仓（需更强信号），SELL=减仓/清仓，HOLD=维持持仓
- 已有持仓且技术面无明显恶化，优先HOLD而非重复BUY
- 已有持仓且亏损超5%或技术破位（价格跌破MA20且量增），必须输出SELL

## 信号强度评分（满分10分）
每满足一项得分，累计分数决定 confidence 和 action：

条件                                            | 分值
均线多头排列（MA5>MA20>MA60）                    | +2
MACD金叉或金叉区间（DIF>DEA）                    | +2
RSI在中性或偏强区间（40~72）                     | +2
量比放大（>=1.5得2分，1.2~1.5得1分）             | +1~2
今日分时趋势与大趋势一致（多头排列+今日上行等）   | +1
5日涨跌幅为正且适度（0%~8%，趋势延续而非追高）   | +1

评分 -> confidence 映射：
- 8~10分：confidence 0.80~0.95，action=BUY（signal_strength=STRONG）
- 6~7分 ：confidence 0.65~0.79，action=BUY（MEDIUM，轻仓）或HOLD
- 4~5分 ：confidence 0.50~0.64，action=HOLD（WEAK）
- 0~3分 ：confidence 0.30~0.49，action=HOLD 或 SELL（持仓恶化时）

## 禁止BUY的条件（任一满足则禁止BUY）
- 均线空头排列（MA5<MA20<MA60）
- RSI>78（超买，追高风险极高）
- 5日涨幅>12%（短期涨幅过大）
- MACD死叉且量比<1.0

## 输出格式（严格JSON，不加任何Markdown包裹）

所有数值字段必须为 number 类型，不得用字符串。reason 不超过120字，直接回应用户关切。

BUY示例：
{"action":"BUY","confidence":0.82,"signal_strength":"STRONG","risk_level":"MEDIUM","reason":"...","stop_loss":10.50,"take_profit":12.80,"stop_loss_pct":-5.0,"take_profit_pct":15.0,"position_advice":"标准仓位50%"}

SELL示例：
{"action":"SELL","confidence":0.75,"signal_strength":"STRONG","risk_level":"HIGH","reason":"...","stop_loss":null,"take_profit":null,"stop_loss_pct":null,"take_profit_pct":null,"position_advice":"建议清仓"}

HOLD（空仓观望）示例：
{"action":"HOLD","confidence":0.55,"signal_strength":"WEAK","risk_level":"MEDIUM","reason":"...","stop_loss":null,"take_profit":null,"stop_loss_pct":null,"take_profit_pct":null,"position_advice":""}

HOLD（持仓中，给出动态止损位）示例：
{"action":"HOLD","confidence":0.70,"signal_strength":"MEDIUM","risk_level":"LOW","reason":"...","stop_loss":10.20,"take_profit":13.50,"stop_loss_pct":-4.5,"take_profit_pct":18.0,"position_advice":"维持持仓，跌破止损价清仓"}
"""


# ── 数据 Prompt 构建（每次请求动态生成）─────────────────────────────────────

def _build_user_context_section(user_context: dict) -> str:
    if not user_context:
        return "用户未提供背景，按空仓处理，根据技术面客观分析。"
    lines = []
    holding = user_context.get("holding", "").strip()
    capital = user_context.get("capital", "").strip()
    note    = user_context.get("note",    "").strip()
    lines.append(f"持仓情况：{holding}" if holding else "持仓情况：未说明（按空仓处理）")
    if capital:
        lines.append(f"可用资金：{capital}")
    if note:
        lines.append(f"用户问题/备注：{note}")
    return "\n".join(lines)


def _build_recent_bars_section(recent_bars: list) -> str:
    if not recent_bars:
        return ""
    n = len(recent_bars)
    lines = [f"## 近{n}日K线（日线，由远到近）",
             "日期          开盘    最高    最低    收盘   涨跌%   量比",
             "-" * 60]
    for b in recent_bars:
        chg_str = f"{b['chg_pct']:+.2f}%"
        o = b.get("open",  b["close"])
        h = b.get("high",  b["close"])
        l = b.get("low",   b["close"])
        lines.append(
            f"{b['date']}  {o:>7.3f} {h:>7.3f} {l:>7.3f} {b['close']:>7.3f}  {chg_str:>6}  {b['vol_ratio']:.2f}"
        )
    return "\n".join(lines)


def _build_intraday_section(intraday_summary: dict) -> str:
    if not intraday_summary:
        return ""
    s = intraday_summary
    o   = s.get("open",   0)
    h   = s.get("high",   0)
    l   = s.get("low",    0)
    c   = s.get("latest", 0)
    pct = s.get("pct_change", 0)

    lines = ["## 今日分时摘要"]
    lines.append(f"- 今日OHLC：开{o:.3f}  高{h:.3f}  低{l:.3f}  现{c:.3f}")
    lines.append(f"- 今日涨跌：{pct:+.2f}%")

    # 形态描述
    if o > 0 and c > 0:
        prev = s.get("prev_close", o)
        gap  = (o - prev) / prev * 100 if prev > 0 else 0
        form = ("高开" if gap > 1.5 else "低开" if gap < -1.5 else "平开")
        form += ("高走" if c > o * 1.003 else "低走" if c < o * 0.997 else "平走")
        lines.append(f"- 形态：{form}")

    vol_r = s.get("vol_ratio_intraday", 0)
    if vol_r and vol_r != 1.0:
        lines.append(f"- 分时量比：{vol_r:.2f}")

    trend = s.get("trend", "")
    if trend:
        lines.append(f"- 分时趋势：{trend}")

    return "\n".join(lines)


def _build_data_prompt(
    symbol: str,
    board: str,
    user_ctx: str,
    ind: dict,
    recent_bars_section: str,
    intraday_section: str,
    sentiment: str,
) -> str:
    return f"""\
## 股票信息
代码：{symbol}　板块：{board}

## 用户操作背景
{user_ctx}

{recent_bars_section}

## 最新技术指标
价格：{ind.get('price', 0)}
均线：MA5={ind.get('ma5', 0)}  MA20={ind.get('ma20', 0)}  MA60={ind.get('ma60', 0)}
均线形态：{ind.get('ma_arrangement', '—')}
偏离MA20：{ind.get('ma20_dist_pct', 0):+.1f}%　偏离MA60：{ind.get('ma60_dist_pct', 0):+.1f}%
5日涨跌幅：{ind.get('change_5d_pct', 0):+.1f}%

RSI：{ind.get('rsi', 50)}（{ind.get('rsi_zone', '—')}）
MACD：DIF={ind.get('macd_dif', 0)}  DEA={ind.get('macd_dea', 0)}  柱={ind.get('macd_hist', 0)}  状态：{ind.get('macd_cross', '—')}

量比：{ind.get('vol_ratio', 1.0)}（当日量={ind.get('vol', 0)}，20日均量={ind.get('vol_avg', 0)}）
市场情绪：{sentiment}

{intraday_section}

## 分析任务
请按以下步骤思考，然后输出一个JSON（不加任何额外文字）：
1. 确认用户持仓状态（影响BUY/SELL的含义）
2. 对照"信号强度评分"逐项打分，得出 confidence 区间
3. 检查是否触发"禁止BUY"或"必须SELL"条件
4. 结合今日分时方向作为短期确认
5. 依据板块类型设定合理止损止盈
6. reason 中用120字以内直接回应用户关切
"""


# ── 主入口 ────────────────────────────────────────────────────────────────────

def get_ai_decision(
    symbol: str,
    indicators: dict,
    sentiment: str = "中性",
    position: dict = None,
    user_context: dict = None,
    intraday_summary: dict = None,
    recent_bars: list = None,
) -> dict:
    """
    调用 AI 获取交易决策

    Parameters
    ----------
    symbol           : 股票代码
    indicators       : get_latest_indicators() 返回的 dict（含衍生字段）
    sentiment        : 新闻情绪文本
    position         : 当前持仓信息 dict，无持仓传 None
    user_context     : 用户自定义输入 dict（holding/capital/note）
    intraday_summary : 分时数据摘要 dict
    recent_bars      : get_recent_bars() 返回的近期K线列表

    Returns
    -------
    dict: action / confidence / signal_strength / risk_level / reason / ...
    """
    price = indicators.get("price", 0)

    # 若用户未传持仓，尝试从 position 自动补充
    if not user_context:
        user_context = {}
    if position and not user_context.get("holding"):
        shares   = position.get("shares",   0)
        avg_cost = position.get("avg_cost", 0)
        if shares > 0 and avg_cost > 0:
            pnl_pct = (price - avg_cost) / avg_cost * 100
            user_context = dict(user_context)
            user_context["holding"] = (
                f"持有 {shares} 股，均价 {avg_cost:.3f}，"
                f"当前浮盈亏 {pnl_pct:+.2f}%"
            )

    board               = _board_type(symbol)
    user_ctx_str        = _build_user_context_section(user_context)
    recent_bars_section = _build_recent_bars_section(recent_bars or [])
    intraday_section    = _build_intraday_section(intraday_summary or {})

    data_prompt = _build_data_prompt(
        symbol, board, user_ctx_str,
        indicators, recent_bars_section, intraday_section, sentiment,
    )

    last_err = None
    raw = ""
    for attempt in range(3):
        try:
            r = _http.post(
                _RESPONSES_URL,
                json={
                    "model":             config.AI_MODEL,
                    "instructions":      _SYSTEM_PROMPT,
                    "input":             [{"role": "user", "content": data_prompt}],
                    "temperature":       0.15,
                    "max_output_tokens": 1000,
                },
            )
            r.raise_for_status()
            data = r.json()
            raw = data["output"][0]["content"][0]["text"].strip()

            # 提取 JSON（兼容被 markdown 包裹的情况）
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            result = json.loads(m.group() if m else raw)

            # 统一字段，防止 AI 漏字段
            result.setdefault("action",          "HOLD")
            result.setdefault("confidence",      0.5)
            result.setdefault("signal_strength", "WEAK")
            result.setdefault("risk_level",      "HIGH")
            result.setdefault("reason",          "无说明")
            result.setdefault("stop_loss",       None)
            result.setdefault("take_profit",     None)
            result.setdefault("stop_loss_pct",   None)
            result.setdefault("take_profit_pct", None)
            result.setdefault("position_advice", "")

            # 确保数值字段是 float（防止 AI 返回字符串形式的数字）
            for key in ("confidence", "stop_loss", "take_profit",
                        "stop_loss_pct", "take_profit_pct"):
                v = result.get(key)
                if v is not None:
                    try:
                        result[key] = float(v)
                    except (ValueError, TypeError):
                        result[key] = None

            logger.info(
                f"[AI] {symbol} → {result['action']}  "
                f"置信:{result['confidence']:.0%}  {result['reason']}"
            )
            try:
                from notify.email_notify import notify_ai_success
                notify_ai_success()
            except Exception:
                pass
            return result

        except json.JSONDecodeError as e:
            last_err = e
            logger.warning(f"[AI] {symbol} JSON解析失败(attempt {attempt+1}): {raw[:120]}")
            continue
        except Exception as e:
            last_err = e
            if attempt < 2:
                import time as _time
                wait = 2 ** attempt      # 指数退避：1s → 2s
                logger.warning(
                    f"[AI] {symbol} 请求失败(attempt {attempt+1}/{type(e).__name__})，"
                    f"{wait}s后重试..."
                )
                _time.sleep(wait)
                continue
            break

    logger.error(f"[AI] {symbol} 决策失败(已重试): {last_err}")
    try:
        from notify.email_notify import notify_ai_failure
        notify_ai_failure(str(last_err)[:120])
    except Exception:
        pass
    return {
        "action":          "HOLD",
        "confidence":      0.0,
        "signal_strength": "WEAK",
        "risk_level":      "HIGH",
        "reason":          f"AI暂时不可用，已HOLD: {str(last_err)[:40]}",
        "stop_loss":       None,
        "take_profit":     None,
        "stop_loss_pct":   None,
        "take_profit_pct": None,
        "position_advice": "",
    }
