"""
YKT Browser - PyInstaller 构建脚本
运行: python build.py
"""

import subprocess
import sys
import os


def build():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=YKT-Browser",
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--add-data=requirements.txt;.",
        "main.py",
    ]
    print("正在构建...")
    print(f"命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
    if result.returncode == 0:
        print("\n✓ 构建完成！输出目录: dist/YKT-Browser/")
    else:
        print(f"\n✗ 构建失败 (exit code {result.returncode})")
    return result.returncode


if __name__ == "__main__":
    sys.exit(build())
