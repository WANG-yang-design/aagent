"""
实盘桥接服务 —— 必须用 32 位 Python 运行
提供本地 HTTP 接口供主程序调用，底层用 easytrader 控制东方财富客户端

启动方式：
    D:\python38_32\python.exe D:\AAgent\trading\broker_bridge_server.py

依赖安装（32位Python环境）：
    D:\python38_32\python.exe -m pip install easytrader flask python-dotenv
"""
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", 8890))

_trader = None   # easytrader user 对象


def _kill_broker_process(exe_path: str):
    """关闭已运行的券商客户端进程（温和方式），让 easytrader 全新启动"""
    import os, time, subprocess
    
    # 要杀的进程列表
    targets = ["maintrade.exe", "xiadan.exe"]
    if exe_path and os.path.basename(exe_path).lower() not in targets:
        targets.append(os.path.basename(exe_path).lower())
    
    logger.info(f"[杀进程] 目标进程: {targets}")
    
    # 只使用 taskkill，/T 表示杀死进程树（包括子进程），/F 强制杀
    for proc_name in targets:
        try:
            # 先检查进程是否存在
            check_result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {proc_name}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if proc_name in check_result.stdout:
                logger.info(f"[杀进程] 发现进程 {proc_name}，准备终止...")
                kill_result = subprocess.run(
                    ["taskkill", "/IM", proc_name, "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if kill_result.returncode == 0:
                    logger.info(f"[杀进程] 成功终止 {proc_name}")
                else:
                    logger.info(f"[杀进程] {proc_name} 信息: {kill_result.stdout}")
            else:
                logger.debug(f"[杀进程] 进程不存在 {proc_name}")
                
        except subprocess.TimeoutExpired:
            logger.warning(f"[杀进程] 处理 {proc_name} 超时")
        except Exception as e:
            logger.warning(f"[杀进程] 处理 {proc_name} 异常: {e}")
    
    logger.info("[杀进程] 等待系统稳定...")
    time.sleep(3)
    logger.info("[杀进程] 完成")


def _dismiss_popups():
    """关闭弹窗：用 win32gui 直接发 BM_CLICK，不依赖中文文字匹配"""
    try:
        import win32gui, win32con, time

        clicked = []

        def _click_buttons(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if not (60 < w < 800 and 40 < h < 500):
                return

            def _child(child_hwnd, __):
                try:
                    if win32gui.GetClassName(child_hwnd) == "Button":
                        win32gui.SendMessage(child_hwnd, win32con.BM_CLICK, 0, 0)
                        clicked.append(child_hwnd)
                except Exception:
                    pass

            win32gui.EnumChildWindows(hwnd, _child, None)

        win32gui.EnumWindows(_click_buttons, None)
        if clicked:
            logger.info(f"关闭弹窗：点击了 {len(clicked)} 个按钮")
            time.sleep(0.8)
    except Exception as e:
        logger.debug(f"弹窗处理跳过: {e}")


def _resp(handler, code: int, data: dict):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", len(body))
    handler.end_headers()
    handler.wfile.write(body)


class BridgeHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass   # 关闭默认的 HTTP 请求日志（太吵）

    def do_GET(self):
        global _trader
        if self.path == "/health":
            _resp(self, 200, {"status": "ok", "connected": _trader is not None})

        elif self.path == "/positions":
            if _trader is None:
                _resp(self, 400, {"error": "未连接"})
                return
            try:
                raw = _trader.position
                _resp(self, 200, {"positions": raw})
            except Exception as e:
                _resp(self, 500, {"error": str(e)})

        elif self.path == "/balance":
            if _trader is None:
                _resp(self, 400, {"error": "未连接"})
                return
            try:
                b = _trader.balance
                if isinstance(b, list):
                    b = b[0] if b else {}
                _resp(self, 200, b)
            except Exception as e:
                _resp(self, 500, {"error": str(e)})

        elif self.path == "/orders":
            if _trader is None:
                _resp(self, 400, {"error": "未连接"})
                return
            try:
                raw = _trader.current_deal
                _resp(self, 200, {"orders": raw})
            except Exception as e:
                _resp(self, 500, {"error": str(e)})

        else:
            _resp(self, 404, {"error": "not found"})

    def do_POST(self):
        global _trader
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/connect":
            try:
                import easytrader
                broker_type   = body.get("broker_type",   os.getenv("BROKER_TYPE", "universal_client"))
                account       = body.get("account",       os.getenv("BROKER_ACCOUNT", ""))
                password      = body.get("password",      os.getenv("BROKER_PASSWORD", ""))
                exe_path      = body.get("exe_path",      os.getenv("BROKER_EXE", ""))
                comm_password = body.get("comm_password", os.getenv("BROKER_COMM_PASSWORD", ""))

                if not account or not password:
                    error_msg = "账号或密码为空"
                    logger.error(f"[/connect] {error_msg}")
                    _resp(self, 400, {"success": False, "error": error_msg})
                    return

                logger.info(f"[connect] 【步骤1】关闭已运行的客户端进程...")
                logger.info(f"  broker_type={broker_type}")
                logger.info(f"  account={account}")
                logger.info(f"  exe_path={exe_path}")
                
                # 关闭已运行的客户端实例
                _kill_broker_process(exe_path)

                import time
                logger.info(f"[connect] 【步骤2】等待旧进程清理（5秒）...")
                time.sleep(5)

                logger.info(f"[connect] 【步骤3】创建 easytrader 实例...")
                _trader = easytrader.use(broker_type)
                
                logger.info(f"[connect] 【步骤4】启动客户端并自动输入密码（这可能需要10-30秒）...")
                kwargs = dict(user=account, password=password, exe_path=exe_path or None)
                if comm_password:
                    kwargs["comm_password"] = comm_password
                    logger.info(f"  已设置通讯密码")
                
                _trader.prepare(**kwargs)
                logger.info(f"[connect] 【步骤5】prepare() 完成，等待UI稳定...")
                
                # 给UI充分时间完全加载
                time.sleep(5)
                
                logger.info(f"[connect] 【步骤6】处理可能的登录弹窗...")
                _dismiss_popups()
                
                time.sleep(2)
                logger.info(f"[connect] 【步骤7】验证连接...")
                
                # 尝试获取账户信息来验证连接是否成功
                try:
                    balance = _trader.balance
                    logger.info(f"[connect] ✓ 连接成功！账户余额: {balance}")
                except Exception as verify_err:
                    logger.warning(f"[connect] 验证时出现错误，但继续: {verify_err}")
                
                logger.info(f"[connect] 【完成】实盘连接成功！")
                _resp(self, 200, {"success": True})
                
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                logger.error(f"[connect] ✗ 连接失败: {error_msg}")
                import traceback
                logger.error(f"[connect] 详细错误:\n{traceback.format_exc()}")
                _trader = None
                _resp(self, 500, {"success": False, "error": error_msg})

        elif self.path == "/buy":
            if _trader is None:
                _resp(self, 400, {"success": False, "error": "未连接"})
                return
            try:
                result = _trader.buy(body["symbol"], price=body["price"], amount=body["amount"])
                logger.info(f"买入 {body['symbol']} {body['amount']}股 @ {body['price']}  回报={result}")
                _resp(self, 200, {"success": True, "result": str(result)})
            except Exception as e:
                logger.error(f"买入失败: {e}")
                _resp(self, 500, {"success": False, "error": str(e)})

        elif self.path == "/sell":
            if _trader is None:
                _resp(self, 400, {"success": False, "error": "未连接"})
                return
            try:
                result = _trader.sell(body["symbol"], price=body["price"], amount=body["amount"])
                logger.info(f"卖出 {body['symbol']} {body['amount']}股 @ {body['price']}  回报={result}")
                _resp(self, 200, {"success": True, "result": str(result)})
            except Exception as e:
                logger.error(f"卖出失败: {e}")
                _resp(self, 500, {"success": False, "error": str(e)})

        elif self.path == "/disconnect":
            _trader = None
            _resp(self, 200, {"success": True})

        else:
            _resp(self, 404, {"error": "not found"})


if __name__ == "__main__":
    import struct
    bits = 8 * struct.calcsize("P")
    if bits != 32:
        logger.error(f"必须用 32 位 Python 运行！当前是 {bits} 位。")
        logger.error("请执行：D:\\python38_32\\python.exe trading\\broker_bridge_server.py")
        sys.exit(1)

    server = HTTPServer(("127.0.0.1", BRIDGE_PORT), BridgeHandler)
    logger.info(f"实盘桥接服务启动  端口={BRIDGE_PORT}  等待主程序连接...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("桥接服务已停止")
