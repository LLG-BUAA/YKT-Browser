"""
YKT Browser - 雨课堂自动播放助手
入口文件
"""

import sys
import os

# Ensure the script directory is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_dependencies():
    """Check that required packages are installed and give helpful errors."""
    missing = []
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        missing.append("customtkinter")
    try:
        import playwright  # noqa: F401
    except ImportError:
        missing.append("playwright")

    if missing:
        print("=" * 50)
        print("  缺少必要依赖，请先运行安装：")
        print(f"  pip install {' '.join(missing)}")
        if "playwright" in missing:
            print("  playwright install chromium")
        print("  或直接运行 setup.bat")
        print("=" * 50)
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "YKT Browser - 缺少依赖",
                f"缺少以下依赖包:\n{', '.join(missing)}\n\n"
                f"请运行以下命令安装:\n"
                f"pip install {' '.join(missing)}\n"
                + ("playwright install chromium\n" if "playwright" in missing else "")
                + "\n或直接运行 setup.bat",
            )
        except Exception:
            pass
        sys.exit(1)


def main():
    check_dependencies()
    from app import YuketangApp
    app = YuketangApp()
    app.mainloop()


if __name__ == "__main__":
    main()
