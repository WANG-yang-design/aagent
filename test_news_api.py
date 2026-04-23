#!/usr/bin/env python3
"""
AkShare 新闻接口诊断脚本
直接测试接口，找出失败的真实原因
"""
import sys
import os

print("=" * 70)
print("  AkShare 新闻接口诊断")
print("=" * 70)

print("\n[步骤1] 安装akshare...")
import subprocess
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "akshare", "-q"],
    capture_output=True,
    text=True
)

if result.returncode != 0:
    print(f"❌ akshare 安装失败:")
    print(result.stderr)
    sys.exit(1)
else:
    print("✓ akshare 安装成功")

print("\n[步骤2] 测试 AkShare 基础功能...")
try:
    import akshare as ak
    print("✓ akshare 导入成功")
except Exception as e:
    print(f"❌ akshare 导入失败: {e}")
    sys.exit(1)

print("\n[步骤3] 测试不同的股票代码...")
test_symbols = ["000001", "600519", "600036"]
results = {}

for symbol in test_symbols:
    print(f"\n  测试 {symbol}:")
    try:
        print(f"    - 调用 ak.stock_news_em(symbol='{symbol}')...", end="", flush=True)
        df = ak.stock_news_em(symbol=symbol)
        
        print(f" 完成")
        
        if df is None:
            print(f"    ✗ 返回 None")
            results[symbol] = ("None", None, 0)
        elif df.empty:
            print(f"    ⚠️  返回空 DataFrame (列: {list(df.columns) if hasattr(df, 'columns') else 'N/A'})")
            results[symbol] = ("Empty", df, 0)
        else:
            rows = len(df)
            cols = len(df.columns) if hasattr(df, 'columns') else 0
            cols_list = list(df.columns) if hasattr(df, 'columns') else []
            print(f"    ✓ 返回有效数据 (行: {rows}, 列: {cols})")
            print(f"      列名: {cols_list}")
            if rows > 0:
                print(f"      首行数据:")
                first_row = df.iloc[0]
                for col in list(df.columns)[:3]:
                    print(f"        - {col}: {first_row[col]}")
            results[symbol] = ("Success", df, rows)
            
    except Exception as e:
        print(f" 失败")
        error_type = type(e).__name__
        error_msg = str(e)[:80]
        print(f"    ✗ {error_type}: {error_msg}")
        results[symbol] = ("Error", str(e), 0)

print("\n" + "=" * 70)
print("  诊断结果汇总")
print("=" * 70)

success_count = sum(1 for status, _, _ in results.values() if status == "Success")
total_count = len(results)

print(f"\n成功率: {success_count}/{total_count}")

for symbol, (status, data, count) in results.items():
    if status == "Success":
        print(f"  ✓ {symbol}: {count} 条新闻")
    elif status == "Empty":
        print(f"  ⚠️  {symbol}: 空数据")
    elif status == "None":
        print(f"  ✗ {symbol}: None")
    else:
        print(f"  ✗ {symbol}: {data}")

print("\n[步骤4] 问题分析...")
print("""
可能的原因:

1️⃣  AkShare API 变更或限制
   - 接口可能移到其他地址
   - 接口可能需要特殊的User-Agent或请求头
   - 接口可能有速率限制

2️⃣  网络问题
   - ISP阻断
   - 代理配置
   - DNS解析问题

3️⃣  接口本身的问题
   - 东方财富网站更新，接口失效
   - 需要登录或Cookie验证
   - 返回格式变更

4️⃣  中国地区的访问限制
   - 某些IP被限制
   - 需要特定的HTTP头信息
   
解决方案:
✓ 已修复: news_sentiment.py 现在会优雅处理 None 和空 DataFrame
✓ 已修复: 添加了重试机制（最多重试2次）
✓ 已添加: 异常时返回"中性"而不是崩溃
✓ 建议: 如果持续失败，可以改用其他新闻源
""")

print("\n[步骤5] 建议的替代方案...")
print("""
如果 ak.stock_news_em() 持续失败，可以考虑:

1. 使用 tushare 库的新闻接口
2. 使用 baostock 的市场数据（已有重试机制）
3. 使用硬编码的中性情绪 + 缓存机制
4. 定期检查接口状态，若失败则自动切换

当前修复的处理策略:
  - 返回 None → 重试2次，最后返回"中性"
  - 返回空 DataFrame → 返回"中性"
  - 单条新闻解析失败 → 跳过该条，继续处理其他
  - 无有效新闻 → 返回"中性"
""")

print("=" * 70)
