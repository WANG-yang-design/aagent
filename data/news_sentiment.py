"""
新闻情绪分析 - 多源策略（绕过系统代理）
优先级：东方财富搜索 → 东方财富公告 → AkShare（无代理） → 中性降级
全部请求使用 httpx(proxy=None, trust_env=False) 绕过本地代理
"""
import json
import logging
import re
import time
from typing import List, Tuple

import httpx

logger = logging.getLogger(__name__)

# ── 缓存（30分钟TTL，避免重复请求）─────────────────────────────────────────
_CACHE: dict = {}
_CACHE_TTL = 30 * 60

# ── 情绪词表 ──────────────────────────────────────────────────────────────────
POSITIVE = [
    "利好", "增长", "突破", "创新高", "上涨", "盈利", "获批", "中标",
    "合作", "回购", "增持", "业绩预增", "扭亏为盈", "超预期", "大涨",
    "订单", "战略合作", "新产品", "发布", "涨停", "分红", "派息",
    "高送转", "重组", "并购", "扩产", "中奖", "新高",
]
NEGATIVE = [
    "利空", "下跌", "亏损", "减持", "诉讼", "调查", "违规", "风险",
    "下调", "退市", "减少", "业绩预减", "亏损扩大", "跌停", "处罚",
    "质押", "违约", "曝光", "下滑", "低于预期", "监管", "立案",
    "ST", "问询函", "警示", "冻结", "强制执行",
]

# 复用同一个 httpx Client（绕过系统代理）
_HTTP = httpx.Client(
    proxy=None,
    trust_env=False,
    timeout=8,
    follow_redirects=True,
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    },
)


def _market_code(symbol: str) -> Tuple[str, int]:
    """返回 (市场字符串, 东财市场整数)"""
    c = symbol.zfill(6)
    if c.startswith(("6", "5", "9")):
        return "sh", 1
    if c.startswith(("4", "8")):
        return "bj", 0
    return "sz", 0


def _score(text: str) -> float:
    pos = sum(1 for w in POSITIVE if w in text)
    neg = sum(1 for w in NEGATIVE if w in text)
    t = pos + neg
    return 0.0 if t == 0 else (pos - neg) / t


# ── 数据源 1：东方财富 JSONP 搜索 API ─────────────────────────────────────────

def _fetch_em_search(symbol: str, limit: int) -> List[str]:
    """东方财富搜索接口（与 akshare 相同 URL，但用 httpx 绕过代理）"""
    try:
        param = json.dumps({
            "uid": "", "keyword": symbol,
            "type": ["cmsArticleWebOld"],
            "client": "web", "clientType": "web", "clientVersion": "curr",
            "param": {"cmsArticleWebOld": {
                "searchScope": "default", "sort": "default",
                "pageIndex": 1, "pageSize": limit,
                "preTag": "", "postTag": "",
            }},
        }, separators=(",", ":"))
        r = _HTTP.get(
            "https://search-api-web.eastmoney.com/search/jsonp",
            params={"cb": "cb", "param": param},
            headers={"Referer": "https://www.eastmoney.com/"},
        )
        m = re.search(r"\w+\((.+)\)\s*$", r.text, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group(1))
        items = data.get("result", {}).get("cmsArticleWebOld", [])
        return [f"{x.get('title','')} {x.get('content','')[:80]}" for x in items if x.get("title")]
    except Exception as e:
        logger.debug(f"[{symbol}] EM搜索API: {type(e).__name__}: {e}")
        return []


# ── 数据源 2：东方财富新闻列表 API ────────────────────────────────────────────

def _fetch_em_newslist(symbol: str, limit: int) -> List[str]:
    """东方财富个股新闻列表接口"""
    try:
        _, mkt_int = _market_code(symbol)
        r = _HTTP.get(
            "https://np-listapi.eastmoney.com/comm/web/getListInfo",
            params={
                "client": "web", "type": "1",
                "mTypeAndCode": f"{mkt_int},{symbol}",
                "pageSize": limit, "pageIndex": 1,
            },
            headers={"Referer": "https://quote.eastmoney.com/"},
        )
        data = r.json()
        items = data.get("data", {}).get("list", []) or []
        return [f"{x.get('title','')}" for x in items if x.get("title")]
    except Exception as e:
        logger.debug(f"[{symbol}] EM新闻列表: {type(e).__name__}: {e}")
        return []


# ── 数据源 3：东方财富公告 API ────────────────────────────────────────────────

def _fetch_em_announcement(symbol: str, limit: int) -> List[str]:
    """东方财富公告接口（公告标题含较多关键词）"""
    try:
        r = _HTTP.get(
            "https://np-anotice-stock.eastmoney.com/api/security/ann",
            params={
                "sr": -1, "page_size": limit, "page_index": 1,
                "ann_type": "A", "client_source": "web",
                "f_node": 0, "s_node": 0, "keyword": symbol,
            },
        )
        data = r.json()
        items = data.get("data", {}).get("list", []) or []
        return [x.get("TITLE", "") for x in items if x.get("TITLE")]
    except Exception as e:
        logger.debug(f"[{symbol}] EM公告: {type(e).__name__}: {e}")
        return []


# ── 数据源 4：AkShare（显式禁用环境代理后调用）────────────────────────────────

def _fetch_akshare(symbol: str, limit: int) -> List[str]:
    """AkShare 备用源（临时清除代理环境变量）"""
    import os
    saved = {}
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=symbol)
        if df is None or not hasattr(df, "empty") or df.empty:
            return []
        rows = []
        for _, row in df.head(limit).iterrows():
            title   = str(row.get("新闻标题", "") or "")
            content = str(row.get("新闻内容", "") or "")[:80]
            if title:
                rows.append(f"{title} {content}")
        return rows
    except Exception as e:
        logger.debug(f"[{symbol}] AkShare: {type(e).__name__}: {e}")
        return []
    finally:
        os.environ.update(saved)


# ── 主入口 ────────────────────────────────────────────────────────────────────

def get_stock_news_sentiment(symbol: str, limit: int = 10) -> dict:
    """
    获取个股新闻并计算情绪（带缓存 + 四源降级）

    Returns
    -------
    dict: score / label / news_count / sentiment_text
    """
    code = symbol.zfill(6)

    # 缓存命中
    now = time.time()
    if code in _CACHE:
        ts, result = _CACHE[code]
        if now - ts < _CACHE_TTL:
            return result

    texts: List[str] = []
    source = ""

    # 依次尝试各源
    texts = _fetch_em_search(code, limit)
    if texts:
        source = "EM搜索"

    if not texts:
        texts = _fetch_em_newslist(code, limit)
        if texts:
            source = "EM新闻列表"

    if not texts:
        texts = _fetch_em_announcement(code, limit)
        if texts:
            source = "EM公告"

    if not texts:
        texts = _fetch_akshare(code, limit)
        if texts:
            source = "AkShare"

    if not texts:
        logger.warning(f"[{symbol}] 所有新闻源均失败，返回中性情绪")
        result = _neutral()
        _CACHE[code] = (now, result)
        return result

    scores = [_score(t) for t in texts]
    avg = sum(scores) / len(scores)

    if avg > 0.1:
        label = "positive"
        text  = f"利好/偏多（{len(texts)}条，{source}，评分:{avg:.2f}）"
    elif avg < -0.1:
        label = "negative"
        text  = f"利空/偏空（{len(texts)}条，{source}，评分:{avg:.2f}）"
    else:
        label = "neutral"
        text  = f"中性（{len(texts)}条，{source}，评分:{avg:.2f}）"

    result = {
        "score":          round(avg, 3),
        "label":          label,
        "news_count":     len(texts),
        "sentiment_text": text,
    }
    logger.info(f"[{symbol}] 新闻情绪: {len(texts)}条({source}) → {label}")
    _CACHE[code] = (now, result)
    return result


def _neutral() -> dict:
    return {"score": 0.0, "label": "neutral", "news_count": 0, "sentiment_text": "无数据/中性"}
