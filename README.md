# YKT Browser

雨课堂自动化桌面版，包含：

- 真实可见浏览器控制
- 视频页自动保活播放
- 视频播放完成后自动点击 `下一单元`
- 支持识别视频从 90%+ 回到 10% 以下的回播场景
- 习题页 / 提交页延时自动跳转
- `下一单元` 多策略点击与结构化诊断
- 结构化日志与错误诊断
- 会话日志归档
- PySide6 图形界面
- PyInstaller 打包脚本

## 目录说明

- `yuketang_gui.py`：桌面版入口
- `yuketang_auto.py`：命令行入口
- `ykt_browser/`：核心逻辑、Qt 界面、样式与日志模块
- `build.ps1`：标准打包脚本
- `YKTBrowser.spec`：PyInstaller 规范文件

## 安装依赖

```powershell
pip install -r requirements.txt
```

## 运行桌面版

```powershell
python yuketang_gui.py
```

## 运行命令行版

```powershell
python yuketang_auto.py
```

## 桌面版功能

- 配置课程链接、浏览器路径、用户数据目录、日志目录
- 设置轮询间隔、视频页/非视频页等待时间、超时和重试间隔
- 默认勾选 `无限时间`，有限运行模式默认上限为 `60s`
- 实时显示运行阶段、页面类型、视频进度、跳转次数、告警与错误数
- 按等级、分类、代码、关键字筛选结构化日志
- 查看错误建议、日志详情、事件数据和会话文件路径
- 自动保存上次输入的配置

## 登录与日志

- 首次运行如果跳转到登录页，直接在弹出的浏览器里完成登录
- 登录状态会保存在 `browser-profile/`
- 每次会话会在 `logs/<session-id>/` 下生成：
  - `config.json`
  - `session.log`
  - `events.jsonl`

## 打包

```powershell
.\build.ps1
```

打包完成后，产物会放在：

```text
release/YKTBrowser
```

## 测试参数

桌面版和命令行版都支持：

- `测试快进`：进入视频页若干秒后尝试跳到结尾附近
- `测试模拟完播`：只在脚本侧模拟视频已结束，用于验证倒计时和点击链路

说明：

- 正式使用时建议这两个值都保持为 `0`
- 某些雨课堂播放器会拦截直接拖到结尾的行为，因此快进测试不一定生效
