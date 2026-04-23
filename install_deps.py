#!/usr/bin/env python3
"""
轻量级依赖安装脚本
使用预编译wheel避免编译问题
"""
import subprocess
import sys

packages_to_install = [
    # Web框架 (已安装)
    # "fastapi",  # 已安装
    # "uvicorn",  # 已安装
    
    # 数据处理 (必需)
    "numpy>=1.24.0",
    "pandas>=2.0.0",
    
    # 网络和API
    "requests>=2.28.0",
    "openai>=1.0.0",
    
    # 数据源
    "baostock>=0.8.8",
    "akshare>=1.16.72",
    
    # 其他
    "backtrader>=1.9.76.123",
    "tabulate>=0.9.0",
    "rich>=13.0.0",
    "websockets>=11.0",
    "python-multipart>=0.0.6",
    "easytrader>=0.23.0",
]

print("=" * 70)
print("  智能依赖安装")
print("=" * 70)

# 尝试使用 --only-binary :all: 来强制使用预编译wheel
print("\n[1] 尝试使用预编译wheel安装依赖...")
print("    (如果这失败了，下一步会尝试普通安装)")

cmd = [
    sys.executable, "-m", "pip", "install",
    "--only-binary", ":all:",
    "--no-cache-dir",
] + packages_to_install

result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode != 0:
    print("\n⚠️  预编译wheel安装失败，尝试普通安装...")
    print(result.stderr[:500])
    
    print("\n[2] 尝试普通安装...")
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--no-cache-dir",
    ] + packages_to_install
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("\n❌ 安装失败!")
        print(result.stderr[:1000])
        print("\n💡 替代方案:")  
        print("   1. 使用Conda: conda install numpy pandas requests openai")
        print("   2. 使用外部编译: pip install --user scikit-build-core ninja")
        sys.exit(1)
else:
    print("\n✅ 预编译wheel安装成功!")

print("\n[3] 验证关键包是否安装...")
test_imports = {
    "pandas": "pandas",
    "numpy": "numpy",
    "requests": "requests",
    "openai": "openai",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
}

failed_imports = []
for name, module in test_imports.items():
    try:
        __import__(module)
        print(f"  ✓ {name}")
    except ImportError:
        print(f"  ✗ {name} - 缺失")
        failed_imports.append(name)

if failed_imports:
    print(f"\n⚠️  缺失 {len(failed_imports)} 个包: {', '.join(failed_imports)}")
else:
    print("\n✅ 所有关键包已安装!")

print("\n" + "=" * 70)
print("  现在可以运行:")
print("=" * 70)
print("\n分析命令:")
print("  python main.py analyze 000001 600519")
print("\n启动Web应用:")
print("  python app.py")
print("  访问: http://127.0.0.1:8888")
print("\n" + "=" * 70)
