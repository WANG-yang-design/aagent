# AAgent 量化交易 Agent 项目文档

> **版本**: 1.0 | **更新日期**: 2026-04-22 | **平台**: Windows 11 / Python 3.x

---

## 一、项目概述

AAgent 是一个面向 A 股市场的 AI 量化交易系统，集成了实时行情获取、技术指标计算、AI 辅助决策、多层风险管理、模拟/实盘交易执行与邮件通知等功能，提供从数据到执行的完整闭环。

**核心流程**:
```
实时行情 → 技术指标 → 新闻情绪 → AI 决策 → 风控检查 → 下单执行 → 通知 + 日志
```

---

## 二、项目结构

```
D:\AAgent/
├── .env                        # 环境变量（API 密钥、邮箱、券商配置）
├── config.py                   # 全局参数（资金、风控、技术指标阈值）
├── requirements.txt            # Python 依赖
├── main.py                     # CLI 入口（analyze / backtest / paper / web）
├── app.py                      # FastAPI Web 应用
├── diagnose.py                 # 环境诊断脚本
│
├── ai_decision/
│   └── agent.py                # AI 决策（调用 yunwu.ai GPT API）
│
├── data/
│   ├── market_data.py          # 行情数据（baostock + 腾讯/新浪，三级降级）
│   └── news_sentiment.py       # 新闻情绪分析（东方财富 + AkShare，四级降级）
│
├── indicators/
│   └── technical.py            # MA / RSI / MACD / 量比指标计算
│
├── database/
│   └── db.py                   # SQLite 持久化（K线、交易、持仓缓存）
│
├── trading/
│   ├── broker_base.py          # 券商抽象基类
│   ├── paper_trader.py         # 模拟盘 Broker
│   ├── real_trader.py          # 实盘 Broker（基础实现）
│   ├── bridge_broker.py        # 64→32 位桥接 Broker
│   ├── miniqmt_trader.py       # MiniQMT Broker
│   ├── engine.py               # 统一交易引擎（定时扫描 + 决策 + 执行）
│   ├── broker_bridge_server.py # 桥接服务端（32 位进程）
│   └── sector_leaders.py       # 板块龙头股维护
│
├── risk/
│   └── risk_manager.py         # 风险管理（仓位 / 亏损 / 止损 / 止盈）
│
├── backtest/
│   └── strategy.py             # Backtrader 评分制回测策略
│
├── reports/
│   └── report_generator.py     # 回测报告 / 持仓报告 / 日报生成
│
├── notify/
│   └── email_notify.py         # 邮件推送（BUY / SELL / 告警 / 日报）
│
├── utils/
│   └── logger.py               # 日志系统（按日期滚动）
│
├── static/                     # Web 前端资源（index.html 等）
├── logs/                       # 运行日志
└── reports/                    # 生成的报告文件
```

---

## 三、核心配置

### 3.1 .env 环境变量

| 变量 | 说明 |
|------|------|
| `AI_API_KEY` | yunwu.ai API 密钥 |
| `AI_BASE_URL` | `https://yunwu.ai/v1` |
| `AI_MODEL` | 使用的 GPT 模型名称 |
| `INITIAL_CAPITAL` | 初始资金（元） |
| `BROKER_TYPE` | 券商类型（`universal_client` / `miniqmt`） |
| `BROKER_ACCOUNT` | 实盘账号 |
| `BROKER_PASSWORD` | 交易密码 |
| `BROKER_EXE` | 东方财富客户端路径 |
| `BRIDGE_PORT` | 桥接服务端口（默认 8890） |
| `EMAIL_ENABLED` | 是否开启邮件通知 |
| `EMAIL_SMTP_HOST` | SMTP 服务器（QQ: `smtp.qq.com:465`） |
| `EMAIL_SENDER` | 发件人 |
| `EMAIL_RECEIVER` | 主收件人（接收所有信号） |
| `EMAIL_RECEIVER1` | 副收件人（仅接收 BUY 信号） |
| `NOTIFY_MIN_CONFIDENCE` | 推送置信度阈值（默认 0.60） |

### 3.2 config.py 参数

```python
# 资金与风控
INITIAL_CAPITAL     = 10_000   # 初始资金（元）
MAX_POSITION_RATIO  = 0.50     # 单次最大仓位（50%）
MAX_DAILY_LOSS_RATIO= 0.10     # 单日最大亏损（10%）
MAX_DAILY_TRADES    = 100      # 单日最大交易次数
STOP_LOSS_RATIO     = 0.05     # 止损线（5%）
TAKE_PROFIT_RATIO   = 0.15     # 止盈线（15%）
MIN_CONFIDENCE      = 0.60     # AI 决策最低置信度

# 技术指标
MA_SHORT = 5 / MA_MID = 20 / MA_LONG = 60
RSI_PERIOD = 14
MACD_FAST = 12 / MACD_SLOW = 26 / MACD_SIGNAL = 9
VOL_MA_PERIOD = 20

# 默认监控标的
DEFAULT_SYMBOLS = ["000001", "600036", "600519", "000858", "300750"]
```

---

## 四、功能模块详解

### 4.1 AI 决策模块（`ai_decision/agent.py`）

调用 yunwu.ai（OpenAI 兼容接口）生成 BUY / SELL / HOLD 交易信号。

**Prompt 结构**:
- **System Prompt**（固定 ~700 字，可模型缓存）：交易规则、信号评分体系、禁止条件
- **User Prompt**：当前持仓状态、资金情况、K 线指标快照

**信号评分规则**（满分 10 分）:

| 条件 | 加分 |
|------|------|
| 均线多头排列（MA5 > MA20 > MA60） | +2 |
| MACD 金叉（DIF 上穿 DEA） | +2 |
| RSI 在中性区（40~65） | +2 |
| 量比 ≥ 1.5（放量） | +2 |
| 量比 1.2~1.5（适度放量） | +1 |
| 分时走势强势 | +1 |
| 5 日涨幅适中 | +1 |

**评分 → 置信度映射**:

| 分数 | 置信度区间 | 强度 |
|------|-----------|------|
| 8~10 | 0.80~0.95 | STRONG |
| 6~7  | 0.65~0.79 | MEDIUM |
| 4~5  | 0.50~0.64 | WEAK |
| 0~3  | 0.30~0.49 | WEAK / → SELL |

**禁止 BUY 条件**（任一触发则禁止）:
- 均线空头排列
- RSI > 78（超买）
- 5 日涨幅 > 12%（追高风险）
- MACD 死叉 + 量比 < 1.0

**输出 JSON 格式**:
```json
{
  "action": "BUY|SELL|HOLD",
  "confidence": 0.0~1.0,
  "signal_strength": "STRONG|MEDIUM|WEAK",
  "risk_level": "LOW|MEDIUM|HIGH",
  "reason": "≤120 字决策理由",
  "stop_loss": 10.50,
  "take_profit": 12.80,
  "stop_loss_pct": -5.0,
  "take_profit_pct": 15.0,
  "position_advice": "仓位建议"
}
```

**容错机制**:
- 3 次重试（指数退避：1s / 2s）
- 兼容 Markdown 包裹的 JSON 响应
- 连续失败 10 次 → 发送邮件告警（120 分钟冷却）

---

### 4.2 行情数据模块（`data/market_data.py`）

#### 实时行情（三级降级）

| 优先级 | 数据源 | 说明 |
|--------|--------|------|
| 1 | 腾讯行情 API | `qt.gtimg.cn`，绕过代理直连 |
| 2 | 新浪行情 API | `hq.sinajs.cn`，备用 |
| 3 | baostock 历史收盘 | 降级保底 |

#### 历史 K 线
- 主源：baostock（前复权）
- 周期：日线（d）/ 周线（w）/ 月线（m）
- 本地 SQLite 缓存：首次全量拉取，后续增量更新
- 支持 `force_refresh` 强制重拉（处理除权等企业行为）

#### 分时数据（四级降级）
1. 腾讯分时接口（1 分钟 → N 分钟重采样）
2. baostock 分钟数据（约 15:30 后可用）
3. 实时行情合成单根 bar（交易时段保底）
4. DB 缓存

**关键特性**：通过 `httpx.Client(proxy=None, trust_env=False)` 绕过 Clash 等系统代理。

---

### 4.3 新闻情绪模块（`data/news_sentiment.py`）

**数据源（四级降级）**：东方财富搜索 API → 东方财富新闻 API → 东方财富公告 API → AkShare

**情绪评分**:
- 正向词表（20+ 词）：利好、增长、突破、创新高、盈利……
- 负向词表（20+ 词）：利空、下跌、亏损、减持、诉讼……
- score = (正数 - 负数) / 总数 ∈ [-1, 1]
- score > 0.1 → `positive` / < -0.1 → `negative` / else → `neutral`
- 30 分钟 TTL 缓存

---

### 4.4 技术指标模块（`indicators/technical.py`）

| 指标 | 参数 | 衍生输出 |
|------|------|---------|
| MA | 5 / 20 / 60 日 | 均线排列（多头/空头/粘合）、MA20/MA60 偏离度 |
| RSI | 14 期 | 区间标签（超买/偏强/中性/偏弱/超卖） |
| MACD | 12/26/9 | 金叉/死叉状态 |
| 成交量 | 20 日均量 | 量比（≥1.5 放量，1.2~1.5 适度放量） |

---

### 4.5 风险管理模块（`risk/risk_manager.py`）

**多层风控体系**:

| 层级 | 检查项 | 触发条件 | 处理 |
|------|--------|---------|------|
| 1 | 置信度 | < 60% | 禁止交易 |
| 2 | 单次仓位 | 买入 > 总资金 50% | 降低手数至上限 |
| 3 | 日亏损 | > 10% | 当日禁止新建仓 |
| 4 | 日交易次数 | > 100 次 | 当日禁止新建仓 |
| 5 | 止损 | 浮损 ≥ -5% | 自动清仓 |
| 6 | 止盈 | 浮盈 ≥ 15% | 自动清仓 |

**买入手数计算**:
```
shares = floor((总资金 × 50%) / 价格 / 100) × 100  # 整手
```

---

### 4.6 交易执行模块（`trading/`）

#### 模拟盘 Broker（`paper_trader.py`）
- 纯内存模拟，不发送真实订单
- 持仓结构：`{symbol: {shares, avg_cost, current_price, cost, entry_time}}`
- 账户快照：总资产 = 现金 + 持仓市值

#### 实盘桥接架构（`bridge_broker.py` + `broker_bridge_server.py`）

东方财富客户端为 32 位程序，主程序为 64 位 Python，因此采用桥接方案：

```
64 位主程序  ←── HTTP ──→  32 位桥接服务  ←── GUI/DLL ──→  东方财富客户端
```

**桥接 HTTP 接口**:
- `GET  /health`：健康检查
- `POST /connect`：连接券商客户端
- `POST /buy` / `POST /sell`：下单
- `GET  /positions`：查持仓
- `GET  /balance`：查资金

#### 交易引擎（`engine.py`）

```
启动 → 定时循环（默认 60 秒）
  ├─ 遍历监控标的
  ├─ 获取历史 K 线 + 实时行情
  ├─ 计算技术指标
  ├─ 获取新闻情绪
  ├─ 调用 AI 决策
  ├─ 检查止损/止盈 → 强制平仓
  ├─ 风控检查 → 确定买入手数
  ├─ 执行下单（Broker）
  ├─ 记录到 DB + 发送邮件通知
  └─ 缓存最新信号（latest_signals）
每日 15:05 → 发送日报邮件
```

---

### 4.7 回测模块（`backtest/strategy.py`）

基于 Backtrader 框架的评分制策略。

**入场**（评分 ≥ 5 分触发买入）:

| 条件 | 得分 |
|------|------|
| MA5 > MA20 | +2 |
| MA20 > MA60 | +2 |
| MACD 正区（DIF > DEA） | +2 |
| RSI 30~70 | +2 |
| 量比 > 0.8 | +1 |
| 价格 > MA20 | +1 |

**出场**（任一满足）:
- 止损 5% / 止盈 15%
- MACD 死叉 + MA5 < MA20
- RSI > 78（超买）

**输出统计**: 总收益率、年化收益、最大回撤、夏普比率、胜率。

---

### 4.8 数据库模块（`database/db.py`）

基于 SQLite，主要数据表：

| 表名 | 说明 |
|------|------|
| `trades` | 交易记录（买卖流水） |
| `portfolio_snapshots` | 账户日快照 |
| `klines` | 日/周/月 K 线缓存 |
| `klines_min` | 分钟级 K 线缓存 |
| `watched_symbols` | 监控标的列表 |
| `favorites` | 收藏股票 |
| `holdings` | 当前持仓 |
| `stock_analysis_history` | AI 分析历史记录 |

---

### 4.9 通知模块（`notify/email_notify.py`）

| 类型 | 颜色 | 冷却 | 说明 |
|------|------|------|------|
| BUY 信号 | 绿色 | 60 分钟/股 | 多股合并一封，副收件人同收 |
| SELL 信号 | 红色 | 24 小时/股 | 含浮盈亏% |
| AI 接口告警 | 橙色 | 120 分钟 | API 连续失败 10 次触发 |
| 每日日报 | 蓝色 | — | 15:05 自动发送，含扫描概要 + 组合快照 |

---

### 4.10 Web 应用（`app.py`）

基于 FastAPI + WebSocket。

**REST API**:

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 仪表板 HTML |
| `/api/status` | GET | 引擎状态 |
| `/api/signals` | GET | 最新交易信号 |
| `/api/engine/scan` | POST | 手动触发扫描 |
| `/api/symbols/add` | POST | 添加监控标的 |
| `/api/symbols/remove` | POST | 移除监控标的 |
| `/api/symbols` | GET | 标的列表（含名称） |
| `/api/favorites` | GET | 收藏股票列表 |

**WebSocket**：实时广播交易事件、持仓变动、信号更新。

---

## 五、CLI 使用说明

```bash
# 单股 AI 分析（快速验证）
python main.py analyze 000001 600036

# 历史回测
python main.py backtest 000001 --start 20200101 --end 20241231

# 启动模拟盘（每 60 秒扫描）
python main.py paper 000001 600036 300750 --interval 60

# 启动 Web 可视化面板
python main.py web --port 8888
# 浏览器访问: http://127.0.0.1:8888
```

---

## 六、技术栈

| 类别 | 库 / 服务 |
|------|---------|
| AI 决策 | yunwu.ai（OpenAI 兼容接口，GPT 系列模型） |
| 历史行情 | baostock |
| 实时行情 | 腾讯行情 API / 新浪行情 API |
| 新闻数据 | 东方财富 API / AkShare |
| 回测框架 | Backtrader |
| HTTP 客户端 | httpx（绕代理直连） |
| 数据处理 | pandas / numpy |
| Web 框架 | FastAPI + uvicorn |
| 数据库 | SQLite |
| 实盘对接 | easytrader（32 位桥接） |
| 通知 | SMTP（QQ / Gmail） |
| 配置 | python-dotenv |

---

## 七、关键设计决策

### 7.1 多源数据降级
单一数据源在国内网络环境下易失败，系统对实时行情、新闻、股票名称均实现了多级降级策略，确保高可用。

### 7.2 代理绕过
Clash 等系统代理会拦截交易相关 HTTP 请求，通过 `httpx.Client(proxy=None, trust_env=False)` 和 `urllib ProxyHandler({})` 强制直连。

### 7.3 实盘桥接
东方财富客户端为 32 位程序，与 64 位 Python 主程序架构不兼容。通过独立的 32 位桥接服务（HTTP API）解耦，主程序通过 HTTP 调用桥接服务控制客户端。

### 7.4 K 线增量更新
首次拉取全量历史数据（慢），后续仅增量拉取新数据（快）。除权等企业行为通过 `force_refresh` 触发全量重拉。

### 7.5 AI System Prompt 缓存
固定规则写入 System Prompt（约 700 字），利用模型的 Prompt Cache 能力减少重复 Token 消耗，降低 API 成本。

---

## 八、性能目标

| 指标 | 目标 |
|------|------|
| 年化收益率 | ≥ 20% |
| 交易胜率 | ≥ 55% |
| 最大回撤 | < 20% |
| AI 信号置信度阈值 | ≥ 60% |
| 扫描周期 | 60 秒 |
| AI API 超时 | < 10 秒 |

---

## 九、开发状态

| 功能 | 状态 |
|------|------|
| AI 决策模块 | ✅ 完成 |
| 多源行情获取 | ✅ 完成 |
| 技术指标计算 | ✅ 完成 |
| 风险管理体系 | ✅ 完成 |
| 模拟盘交易 | ✅ 完成 |
| 邮件通知系统 | ✅ 完成 |
| 回测框架 | ✅ 完成 |
| Web 可视化 | ✅ 完成 |
| SQLite 缓存 | ✅ 完成 |
| 实盘桥接（东方财富） | 🔄 进行中（依赖 32 位 Python 环境） |
| MiniQMT 集成 | 🔄 测试中 |
