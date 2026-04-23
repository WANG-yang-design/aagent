import os
from dotenv import load_dotenv

load_dotenv()

# ── AI API ─────────────────────────────────────────────────────────────────
AI_API_KEY  = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://yunwu.ai/v1")
AI_MODEL    = os.getenv("AI_MODEL", "gpt-5.4")

# ── 资金与仓位 ────────────────────────────────────────────────────────────
INITIAL_CAPITAL      = float(os.getenv("INITIAL_CAPITAL", 1_000_000))
MAX_POSITION_RATIO   = 0.5    # 单次仓位不超过总资金50%
MAX_DAILY_LOSS_RATIO = 0.10   # 单日最大亏损10%
MAX_DAILY_TRADES     = 100    # 单日最多交易次数
STOP_LOSS_RATIO      = 0.05   # 止损5%
TAKE_PROFIT_RATIO    = 0.15   # 止盈15%
MIN_CONFIDENCE       = 0.60   # AI置信度阈值


# ── 实盘券商配置 ──────────────────────────────────────────────────────────
BROKER_TYPE          = os.getenv("BROKER_TYPE",          "universal_client")
BROKER_ACCOUNT       = os.getenv("BROKER_ACCOUNT",       "")
BROKER_PASSWORD      = os.getenv("BROKER_PASSWORD",      "")
BROKER_EXE           = os.getenv("BROKER_EXE",           "")
BROKER_COMM_PASSWORD = os.getenv("BROKER_COMM_PASSWORD", "")

# ── 邮件推送通知 ─────────────────────────────────────────────────────────
# 配置说明：
#   QQ邮箱：host=smtp.qq.com port=465，password填QQ邮箱【授权码】（非QQ密码）
#          开启方式：QQ邮箱→设置→账户→开启SMTP→生成授权码
#   Gmail：host=smtp.gmail.com port=587，password填【应用专用密码】
#          开启方式：Google账号→安全→两步验证→应用密码
EMAIL_ENABLED       = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_SMTP_HOST     = os.getenv("EMAIL_SMTP_HOST",   "smtp.qq.com")
EMAIL_SMTP_PORT     = int(os.getenv("EMAIL_SMTP_PORT", "465"))
EMAIL_SENDER        = os.getenv("EMAIL_SENDER",       "")   # 发件人邮箱
EMAIL_SENDER_PASS   = os.getenv("EMAIL_SENDER_PASS",  "")   # 授权码/应用密码
EMAIL_RECEIVER      = os.getenv("EMAIL_RECEIVER",     "")   # 主收件人邮箱
EMAIL_RECEIVER1     = os.getenv("EMAIL_RECEIVER1",    "")   # 副收件人（只收BUY信号）
# 推送阈值：置信度低于此值不推送
NOTIFY_MIN_CONFIDENCE = float(os.getenv("NOTIFY_MIN_CONFIDENCE", "0.60"))
# 同一股票同方向推送冷却时间（分钟）
NOTIFY_COOLDOWN_MINUTES = int(os.getenv("NOTIFY_COOLDOWN_MINUTES", "60"))

# ── 默认监控标的 ─────────────────────────────────────────────────────────
DEFAULT_SYMBOLS = ["000001", "600036", "600519", "000858", "300750"]

# ── 交易成本 ─────────────────────────────────────────────────────────────
COMMISSION = float(os.getenv("COMMISSION", 5.0))   # 每笔固定手续费（元），买卖各一次

# ── 技术指标参数 ──────────────────────────────────────────────────────────
MA_SHORT     = 5
MA_MID       = 20
MA_LONG      = 60
RSI_PERIOD   = 14
MACD_FAST    = 12
MACD_SLOW    = 26
MACD_SIGNAL  = 9
VOL_MA_PERIOD = 20
