# 🎓 YKT Browser - 雨课堂自动播放助手

基于 Playwright 的雨课堂课程自动播放工具，支持视频自动播放、习题页跳过、自动翻页。

## ✨ 功能

- **视频自动播放** — 检测到视频页面后注入播放脚本，确保视频不暂停
- **播放完成检测** — 通过进度回落检测视频播完（兼容自动循环播放场景）
- **习题页跳过** — 检测到习题/提交页面，等待后自动点击「下一单元」
- **自动翻页** — 视频播完或习题页等待后，自动进入下一单元
- **课程完成识别** — 无「下一单元」按钮时自动停止
- **登录状态保持** — 持久化浏览器数据，只需首次登录
- **现代化 GUI** — 暗色主题界面，实时彩色日志、视频进度条、运行统计

## 📦 安装

### 方式一：一键安装（推荐）

双击运行 `setup.bat`，自动安装 Python 依赖和 Chromium 浏览器。

### 方式二：手动安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## 🚀 使用

### 方式一：双击运行

运行 `run.bat`

### 方式二：命令行

```bash
python main.py
```

### 操作步骤

1. 启动程序，输入框已预填默认课程地址（可修改）
2. 点击「开始」，浏览器会自动打开
3. **首次使用**需在弹出的浏览器中登录雨课堂账号
4. 登录后程序自动检测页面内容并开始工作
5. 可随时「暂停」或「停止」

## 🏗️ 项目结构

```
YKT-Browser/
├── main.py           # 入口文件（含依赖检查）
├── app.py            # GUI 界面（CustomTkinter 暗色主题）
├── engine.py         # 自动化引擎（Playwright）
├── build.py          # PyInstaller 打包脚本
├── requirements.txt  # Python 依赖
├── setup.bat         # 一键安装脚本
├── run.bat           # 一键运行脚本
└── browser_data/     # 浏览器持久化数据（自动生成）
```

## 🔧 工作原理

| 页面类型 | 识别方式 | 动作 |
|---------|---------|------|
| 视频 | 页面含「发表评论」或 `<video>` 元素 | 注入 `setInterval(play())` → 等待播完 → 10秒后点「下一单元」 |
| 习题 | 页面含「习题」或「提交」 | 等待10秒 → 点「下一单元」 |
| 课程结束 | 无「下一单元」按钮 | 自动停止 |

**视频完成检测**：由于注入脚本会导致视频循环播放，通过监测进度百分比——当进度曾达到 90% 以上后回落到 10% 以下，判定视频已完整播放一次。

## 📋 依赖

- Python 3.10+
- [Playwright](https://playwright.dev/python/) — 浏览器自动化
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — 现代化 GUI

## 📄 License

MIT
