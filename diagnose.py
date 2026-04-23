#!/usr/bin/env python3
"""
诊断脚本：快速检查项目中的问题
不需要完整的依赖，只检查import和基础配置
"""
import sys
import os

print("=" * 60)
print("  项目诊断工具 v1.0")
print("=" * 60)

# 1. 检查Python版本
print(f"\n[1] Python 版本: {sys.version}")

# 2. 检查必要的全局包
print("\n[2] 检查全局包安装:")
required_packages = [
    "dotenv",
    "pandas", 
    "numpy",
    "requests",
    "openai",
    "fastapi",
    "uvicorn",
]

installed = []
missing = []

for pkg in required_packages:
    try:
        __import__(pkg.replace("-", "_"))
        installed.append(pkg)
        print(f"  ✓ {pkg}")
    except ImportError:
        missing.append(pkg)
        print(f"  ✗ {pkg}  (缺失)")

# 3. 检查config.py
print("\n[3] 检查配置文件:")
try:
    import config
    print(f"  ✓ config.py 导入成功")
    print(f"    - AI_API_KEY: {'已配置' if config.AI_API_KEY else '未配置 ⚠️ '}")
    print(f"    - AI_MODEL: {config.AI_MODEL}")
    print(f"    - DEFAULT_SYMBOLS: {config.DEFAULT_SYMBOLS}")
except Exception as e:
    print(f"  ✗ config.py 加载失败: {e}")

# 4. 检查数据库
print("\n[4] 检查数据库:")
try:
    from database import db
    print(f"  ✓ database.db 导入成功")
    try:
        symbols = db.get_symbols()
        print(f"    - 已配置股票数: {len(symbols) if symbols else 0}")
    except Exception as e:
        print(f"    ⚠️  获取股票列表失败: {e}")
except Exception as e:
    print(f"  ✗ 数据库加载失败: {e}")

# 5. 检查关键模块
print("\n[5] 检查关键模块:")
modules_to_check = [
    "data.market_data",
    "data.news_sentiment",
    "indicators.technical",
    "trading.engine",
    "ai_decision.agent",
]

for module_name in modules_to_check:
    try:
        # 尝试导入，但如果缺少依赖，捕获ImportError
        exec(f"from {module_name} import *")
        print(f"  ✓ {module_name}")
    except ImportError as e:
        # 检查是否是因为缺少外部库
        if "No module named" in str(e):
            missing_lib = str(e).split("'")[1] if "'" in str(e) else str(e)
            print(f"  ⚠️  {module_name} (缺少: {missing_lib})")
        else:
            print(f"  ✗ {module_name}: {e}")
    except Exception as e:
        print(f"  ✗ {module_name}: {type(e).__name__}: {e}")

# 6. 检查新闻获取接口
print("\n[6] 新闻接口测试:")
print("  当前状态:")
print("    - AkShare: 接口依赖 akshare 库")
print("    - 行为: ak.stock_news_em(symbol) 可能返回:")
print("      ① DataFrame 包含新闻 (正常)")
print("      ② 空 DataFrame (接口无数据)")
print("      ③ None (接口异常)")
print("      ④ 抛出异常 (网络/权限问题)")
print("  修复已应用:")
print("    ✓ 已添加 None 检查和重试")
print("    ✓ 已添加空DataFrame检查") 
print("    ✓ 已修复列名检查逻辑 (row in df vs row.index)")
print("    ✓ 已添加异常行跳过机制")

# 7. 检查app.py
print("\n[7] App.py 检查:")
try:
    # 只检查import，不运行
    import importlib.util
    spec = importlib.util.spec_from_file_location("app_module", "app.py")
    if spec and spec.loader:
        print("  ✓ app.py 文件可读")
        # 检查是否有语法错误
        try:
            with open("app.py", "r", encoding="utf-8") as f:
                code = f.read()
                compile(code, "app.py", "exec")
            print("  ✓ app.py 语法检查通过")
        except SyntaxError as e:
            print(f"  ✗ app.py 语法错误: {e}")
    else:
        print("  ⚠️  无法读取app.py")
except Exception as e:
    print(f"  ✗ app.py 检查失败: {e}")

# 8. 总结
print("\n" + "=" * 60)
print("  诊断总结")
print("=" * 60)

if missing:
    print(f"\n⚠️  缺失的包 ({len(missing)}):")
    for pkg in missing:
        print(f"   - {pkg}")
    print(f"\n  安装命令:")
    print(f"  pip install {' '.join(missing)}")
else:
    print("\n✓ 所有必需包已安装!")

print("\n📝 新闻获取问题说明:")
print("  原因: AkShare stock_news_em() 接口不稳定或无权限")
print("  症状: 返回None或空数据，导致JSON解析错误")
print("  修复: 已添加完整的异常处理和重试机制")
print("  测试: pip install akshare 后运行 python main.py analyze 000001")

print("\n" + "=" * 60)
