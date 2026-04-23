"""
板块龙头股扫描模块
维护各主要板块的代表性龙头股列表，支持批量分析并推送 BUY 信号
"""
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
# 各板块龙头股列表（持续维护，可在此处增删改）
# ══════════════════════════════════════════════════════════════════════════
SECTOR_LEADERS: Dict[str, List[str]] = {
    "半导体/芯片": ["002371", "603501", "002049", "603986", "600460", "002916"],
    "人工智能":    ["002230", "603877", "000977", "600410", "002236", "603019"],
    "新能源汽车":  ["002594", "002460", "603799", "002831", "600884", "601127"],
    "光伏/储能":   ["601012", "600438", "002463", "600732", "002129", "601877"],
    "军工/航空":   ["600893", "600038", "000768", "002985", "600765", "600760"],
    "医药/生物":   ["600276", "603259", "000538", "002589", "600196", "603222"],
    "消费/白酒":   ["000858", "002304", "600887", "000568", "603369", "000799"],
    "银行/金融":   ["600036", "000001", "601166", "002142", "601318", "600030"],
    "机器人/自动化":["002008", "000425", "002756", "603501", "002967", "600690"],
    "云计算/软件": ["002049", "603533", "000977", "600588", "002236", "600570"],
}

# 各板块指数代码（用于获取板块涨跌情况参考）
SECTOR_INDEX: Dict[str, str] = {
    "半导体/芯片": "sh.000688",
    "新能源汽车":  "sh.399976",
    "光伏/储能":   "sh.399986",
    "军工/航空":   "sh.399967",
    "医药/生物":   "sh.399913",
    "消费/白酒":   "sh.000932",
    "银行/金融":   "sh.399986",
}

# 全部龙头股列表（去重）
ALL_LEADERS: List[str] = list(dict.fromkeys(
    sym for syms in SECTOR_LEADERS.values() for sym in syms
))

# 反查：symbol → sector
SYMBOL_TO_SECTOR: Dict[str, str] = {
    sym: sector
    for sector, syms in SECTOR_LEADERS.items()
    for sym in syms
}


def get_all_leaders() -> List[str]:
    """返回所有板块龙头股代码（去重）"""
    return ALL_LEADERS


def get_sector_for_symbol(symbol: str) -> str:
    """返回股票所属板块名称"""
    return SYMBOL_TO_SECTOR.get(symbol, "其他")


def _is_main_board(symbol: str) -> bool:
    """只保留沪深主板：60xxxx / 000xxx / 001xxx / 002xxx / 003xxx"""
    s = symbol.zfill(6)
    return s.startswith(("600", "601", "603", "605",
                          "000", "001", "002", "003"))


def scan_sector_leaders(engine, max_price: float = 50.0) -> List[dict]:
    """
    扫描所有板块龙头股，返回分析结果列表。
    max_price: 只分析股价低于此值的股票（默认50元），高价股跳过以节省时间。
    """
    from data.market_data import get_realtime_quote

    results = []
    total = len(ALL_LEADERS)
    skipped = 0
    logger.info(f"[板块龙头] 开始扫描 {total} 支龙头股（价格上限 {max_price} 元）")

    for i, sym in enumerate(ALL_LEADERS):
        try:
            # ── 板块过滤：只保留沪深主板 ────────────────────────────────
            if not _is_main_board(sym):
                logger.debug(f"[板块龙头] [{i+1}/{total}] {sym} 非主板，跳过")
                skipped += 1
                continue

            # ── 价格预检：先拿实时报价，超过上限直接跳过 ──────────────────
            q = get_realtime_quote(sym)
            price = q.get("price", 0) if q else 0
            if price > max_price:
                logger.debug(
                    f"[板块龙头] [{i+1}/{total}] {sym} 股价 {price:.2f} > {max_price}，跳过"
                )
                skipped += 1
                continue

            analysis = engine.analyze_symbol(sym)
            if analysis:
                analysis["sector"] = get_sector_for_symbol(sym)
                engine.latest_signals[sym] = analysis
                results.append(analysis)
                d = analysis.get("decision", {})
                logger.info(
                    f"[板块龙头] [{i+1}/{total}] {sym} {price:.2f}元 "
                    f"→ {d.get('action','?')} {d.get('confidence',0):.0%}"
                )
        except Exception as e:
            logger.error(f"[板块龙头] {sym} 分析异常: {e}")

    logger.info(
        f"[板块龙头] 扫描完成：{len(results)} 支有效，{skipped} 支因价格>{max_price}元跳过"
    )
    return results


def group_by_sector(results: List[dict]) -> Dict[str, List[dict]]:
    """将分析结果按板块分组"""
    grouped: Dict[str, List[dict]] = {}
    for r in results:
        sector = r.get("sector", "其他")
        grouped.setdefault(sector, []).append(r)
    return grouped


def get_hot_sectors(results: List[dict], top_n: int = 3) -> List[str]:
    """
    根据分析结果判断最热板块（BUY信号最多的板块）
    返回最多 top_n 个板块名
    """
    from collections import Counter
    buy_by_sector: Counter = Counter()
    for r in results:
        action = r.get("decision", {}).get("action", "HOLD")
        if action == "BUY":
            buy_by_sector[r.get("sector", "其他")] += 1
    return [s for s, _ in buy_by_sector.most_common(top_n)]
