"""
日志系统
- 系统日志：logs/system_YYYYMMDD.log  按天滚动
- 交易日志：logs/trades_YYYYMMDD.log  结构化 JSON，每行一条
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)


# ── 系统日志 Handler（按日期文件 + stdout）────────────────────────────────

class _DailyFileHandler(logging.FileHandler):
    """每天自动切换到新文件"""

    def __init__(self):
        self._current_date = datetime.now().strftime("%Y%m%d")
        super().__init__(self._log_path(), encoding="utf-8", delay=True)

    def _log_path(self) -> str:
        return str(LOGS_DIR / f"system_{self._current_date}.log")

    def emit(self, record):
        today = datetime.now().strftime("%Y%m%d")
        if today != self._current_date:
            self._current_date = today
            self.close()
            self.baseFilename = self._log_path()
            self.stream = None
        super().emit(record)


def setup_logging(level: int = logging.INFO):
    """全局日志初始化，只需调用一次"""
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    if root.handlers:
        return  # 已初始化，跳过

    root.setLevel(level)

    # stdout handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # daily file handler
    fh = _DailyFileHandler()
    fh.setFormatter(fmt)
    root.addHandler(fh)


# ── 交易日志（结构化 JSON）────────────────────────────────────────────────

class TradeLogger:
    """每行写入一条 JSON 记录，文件按日期命名"""

    def __init__(self):
        self._current_date = None
        self._file = None
        self._ensure_file()

    def _ensure_file(self):
        today = datetime.now().strftime("%Y%m%d")
        if today == self._current_date and self._file:
            return
        if self._file:
            self._file.close()
        self._current_date = today
        path = LOGS_DIR / f"trades_{today}.log"
        self._file = open(str(path), "a", encoding="utf-8")

    def log(self, record: dict):
        self._ensure_file()
        record.setdefault("timestamp", datetime.now().isoformat())
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._file.flush()

    def close(self):
        if self._file:
            self._file.close()


# 全局单例
trade_logger = TradeLogger()
