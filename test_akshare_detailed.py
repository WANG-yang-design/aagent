#!/usr/bin/env python3
"""
详细的 AkShare 接口测试脚本
测试所有关键接口，找出真实的失败原因
"""
import sys
import os
import traceback
from datetime import datetime, timedelta

print("=" * 80)
print("  AkShare 接口详细诊断")
print("=" * 80)

# 第一步：检查网络连接
print("\n[第一步] 检查网络连接...")
try:
    import socket
    import urllib.request
    
    # 测试DNS解析
    print("  1.1 DNS解析测试...", end=" ", flush=True)
    socket.gethostbyname("push2his.eastmoney.com")
    print("✓ 成功")
    
    # 测试HTTP连接
    print("  1.2 HTTP连接测试...", end=" ", flush=True)
    try:
        urllib.request.urlopen("http://www.baidu.com", timeout=5)
        print("✓ 成功")
    except urllib.error.URLError as e:
        print(f"✗ 失败: {e}")
        print("    ⚠️  网络可能被代理阻断或断网")
    
except Exception as e:
    print(f"✗ 网络诊断失败: {e}")
    traceback.print_exc()

# 第二步：测试代理设置
print("\n[第二步] 检查代理环境变量...")
proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", 
              "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]
for var in proxy_vars:
    val = os.environ.get(var)
    if val:
        print(f"  ⚠️  {var}={val}")
if not any(os.environ.get(var) for var in proxy_vars):
    print("  ✓ 代理环境变量已清空")

# 第三步：导入必要的库
print("\n[第三步] 导入库...")
libraries = {
    "requests": None,
    "pandas": None,
    "akshare": None,
}

for lib_name in libraries:
    try:
        lib = __import__(lib_name)
        libraries[lib_name] = lib
        version = getattr(lib, "__version__", "unknown")
        print(f"  ✓ {lib_name} v{version}")
    except ImportError as e:
        print(f"  ✗ {lib_name}: {e}")
        print(f"\n❌ {lib_name} 未安装，无法继续测试")
        print(f"   安装命令: pip install {lib_name}")
        sys.exit(1)

# 第四步：测试requests库的代理设置
print("\n[第四步] 检查requests库的代理...")
requests = libraries["requests"]
session = requests.Session()
print(f"  - trust_env: {session.trust_env}")
print(f"  - proxies: {session.proxies}")

# 禁用代理
session.trust_env = False
session.proxies = {}
print(f"  ✓ 代理已禁用")

# 第五步：测试AkShare的各个接口
print("\n[第五步] 测试 AkShare 接口...")
ak = libraries["akshare"]

# 5.1 测试实时行情
print("\n  5.1 测试实时行情接口 (stock_zh_a_spot_em)")
print("      这个接口获取所有A股的实时价格...", end=" ", flush=True)
try:
    df = ak.stock_zh_a_spot_em()
    if df is not None and not df.empty:
        print(f"✓ 成功 ({len(df)} 条记录)")
        print(f"         列: {list(df.columns)[:5]}")
    else:
        print("⚠️  返回空数据")
except Exception as e:
    print(f"✗ 失败")
    print(f"       错误: {type(e).__name__}: {str(e)[:80]}")
    traceback.print_exc()

# 5.2 测试历史行情 (baostock方式)
print("\n  5.2 测试历史行情接口 (stock_zh_a_hist)")
print("      这个接口获取日线K线数据...", end=" ", flush=True)
test_symbols = ["000001", "600519"]
for symbol in test_symbols:
    try:
        print(f"\n        [测试 {symbol}]...", end=" ", flush=True)
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date="20260401",
            end_date="20260415",
            adjust="qfq"
        )
        if df is not None and not df.empty:
            print(f"✓ {len(df)} 条记录")
        else:
            print("⚠️  返回空数据")
    except Exception as e:
        print(f"✗ {type(e).__name__}: {str(e)[:60]}")

# 5.3 测试新闻接口
print("\n  5.3 测试新闻接口 (stock_news_em)")
print("      这个接口获取个股新闻...", end=" ", flush=True)
for symbol in test_symbols:
    try:
        print(f"\n        [测试 {symbol}]...", end=" ", flush=True)
        df = ak.stock_news_em(symbol=symbol)
        
        if df is None:
            print("返回 None")
        elif isinstance(df, str):
            print(f"返回字符串: {df[:60]}")
        elif hasattr(df, 'empty'):
            if df.empty:
                print("返回空 DataFrame")
            else:
                rows = len(df)
                cols = list(df.columns)[:3] if hasattr(df, 'columns') else []
                print(f"✓ {rows} 条记录, 列: {cols}")
        else:
            print(f"返回未知类型: {type(df)}")
            
    except Exception as e:
        print(f"✗ {type(e).__name__}: {str(e)[:60]}")

# 第六步：测试HTTP头信息
print("\n\n[第六步] 测试HTTP请求头...", end=" ", flush=True)
try:
    response = session.get("http://quote.eastmoney.com/center/",  timeout=5)
    print(f"\n  - 状态码: {response.status_code}")
    print(f"  - Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    if response.status_code == 200:
        print(f"  ✓ 连接成功")
    else:
        print(f"  ⚠️  返回异常状态码: {response.status_code}")
except Exception as e:
    print(f"\n  ✗ {type(e).__name__}: {str(e)[:80]}")

# 第七步：诊断总结
print("\n" + "=" * 80)
print("  诊断总结")
print("=" * 80)

print("""
🔍 AkShare 接口失败的可能原因：

1️⃣  东方财富网站主动限制
   - IP被限制（频繁访问导致黑名单）
   - User-Agent被屏蔽
   - 接口返回的是登录页而不是数据
   - 需要特定Cookie或Session

2️⃣  网络环境问题
   - ISP/防火墙阻止此接口
   - 代理设置错误
   - DNS解析异常
   - 运营商限流

3️⃣  接口本身问题
   - 东方财富网站更新，接口变更
   - 返回格式改变
   - 接口临时宕机
   - 需要登录或验证

4️⃣  AkShare库问题
   - 版本过旧（某些接口不再支持）
   - 库依赖的库版本冲突
   - 需要更新至最新版本

🎯 解决方案优先级：

1. 【高】检查 AkShare 版本
   pip install --upgrade akshare

2. 【高】添加延迟和User-Agent
   time.sleep(2)  # 访问间隔
   headers = {'User-Agent': 'Mozilla/5.0 ...'}

3. 【中】使用其他数据源替代
   - 改用 tushare（需要Token）
   - 改用 baostock（已有实现）
   - 改用 yfinance（国际数据）

4. 【低】使用代理或VPN
   - 但这不符合国情

========================= 当前已应用的修复 ==========================

✅ news_sentiment.py 中已应用：
   • 异常返回 None 时，优雅降级返回"中性"
   • 接口失败不再导致程序崩溃
   • 改用"中性"情绪继续运行

✅ 用户应该做的：
   1. 升级 AkShare: pip install --upgrade akshare
   2. 等待1-2分钟再重试（如果被限流）
   3. 如果一直失败，考虑改用 baostock（已实现）
   4. 将新闻获取设为可选功能

=========================================================================
""")

print("\n[总结] AkShare 失败不再是致命问题 ✓")
print("       程序会自动降级，使用'中性'情绪继续运行！")
print("=" * 80)
