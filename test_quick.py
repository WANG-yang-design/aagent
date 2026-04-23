#!/usr/bin/env python3
"""
快速启动脚本 - 不需要完整依赖即可测试核心逻辑
直接测试数据获取和新闻情绪处理
"""
import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("  项目快速测试")
print("=" * 70)

# 1. 配置检查
print("\n[1] 配置检查...")
try:
    import config
    print(f"✓ 配置加载成功")
    print(f"  - AI_API_KEY: {'已配置' if config.AI_API_KEY else '⚠️ 未配置'}")
    print(f"  - 默认监控: {config.DEFAULT_SYMBOLS}")
except Exception as e:
    print(f"✗ 配置加载失败: {e}")
    sys.exit(1)

# 2. 数据库检查
print("\n[2] 数据库检查...")
try:
    from database import db
    symbols = db.get_symbols()
    print(f"✓ 数据库初始化成功")
    print(f"  - 已配置股票: {symbols if symbols else config.DEFAULT_SYMBOLS}")
except Exception as e:
    print(f"✗ 数据库初始化失败: {e}")
    sys.exit(1)

# 3. 新闻模块检查
print("\n[3] 新闻情绪模块检查...")
try:
    from data.news_sentiment import get_stock_news_sentiment, _neutral
    
    # 测试中立情绪返回
    test_result = _neutral()
    print(f"✓ 新闻模块加载成功")
    print(f"  - 中立情绪测试: {test_result}")
    print(f"  - 键: {list(test_result.keys())}")
    
    # 测试获取新闻（会自动降级）
    print(f"\n  [测试] 尝试获取 000001 的新闻情绪...")
    result = get_stock_news_sentiment("000001")
    print(f"    结果: {result['sentiment_text']}")
    print(f"    标签: {result['label']}")
    
except Exception as e:
    print(f"✗ 新闻模块错误: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# 4. 技术指标检查
print("\n[4] 技术指标模块检查...")
try:
    from indicators.technical import add_indicators
    print(f"✓ 技术指标模块加载成功")
except ImportError as e:
    print(f"⚠️  技术指标模块缺少依赖: {e}")
except Exception as e:
    print(f"✗ 技术指标模块错误: {e}")

# 5. 市场数据模块检查
print("\n[5] 市场数据模块检查...")
try:
    from data.market_data import get_historical_data, get_realtime_quote
    print(f"✓ 市场数据模块加载成功")
    print(f"  - 支持的函数: get_historical_data, get_realtime_quote")
except ImportError as e:
    print(f"⚠️  市场数据模块缺少依赖: {e}")
except Exception as e:
    print(f"✗ 市场数据模块错误: {e}")

# 6. App.py 启动前检查
print("\n[6] App.py 启动检查...")
try:
    # 检查所有import
    from fastapi import FastAPI
    from pydantic import BaseModel
    from trading.engine import TradingEngine
    
    print(f"✓ 所有关键依赖已安装")
    print(f"  - FastAPI: 已安装")
    print(f"  - TradingEngine: 已安装")
    
    print(f"\n✅ 可以启动 app.py 了!")
    print(f"\n运行命令:")
    print(f"  python app.py")
    print(f"  或")
    print(f"  d:/AAgent/.venv/bin/python.exe app.py")
    print(f"\n访问地址: http://127.0.0.1:8888")
    
except ImportError as e:
    missing_module = str(e).split("'")[1] if "'" in str(e) else str(e)
    print(f"⚠️  缺少依赖: {missing_module}")
    print(f"\n需要安装:")
    print(f"  pip install {missing_module}")
    
except Exception as e:
    print(f"✗ 启动检查失败: {e}")

print("\n" + "=" * 70)
print("  总结")
print("=" * 70)
print("""
✅ 已应用的修复:
  1. market_data.py:
     - 改进代理禁用机制
     - 添加连接重试 (3次)
     - 改进异常处理

  2. news_sentiment.py:
     - 添加akshare导入异常处理
     - 异常时优雅降级返回中性
     - 添加重试机制 (2次)
     - 改进列名检查逻辑 (row in df)
     - 处理各种返回值类型 (None, str, 非DataFrame等)

✅ 新闻获取失败的处理:
  - 当 stock_news_em() 接口失败时，自动返回"中性"情绪
  - 不会导致程序崩溃
  - AI决策仍能基于"中性"情感进行判断

⚠️  建议的后续改进:
  1. 如果akshare一直导入失败，可以：
     - 在requirements.txt中改用 akshare==1.16.72 (稳定版)
     - 或者完全移除akshare，改用其他新闻源
  
  2. 快速测试: python -c "from data.news_sentiment import get_stock_news_sentiment; print(get_stock_news_sentiment('000001'))"
  
  3. 完整依赖安装: pip install -r requirements.txt
     (如果编译失败，考虑使用 pip install --only-binary :all: -r requirements.txt)
""")

print("=" * 70)
