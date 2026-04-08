from __future__ import annotations

import argparse

from .core import YukeTangAutomation
from .models import AutomationConfig, find_browser_path


def build_parser() -> argparse.ArgumentParser:
    defaults = AutomationConfig()
    parser = argparse.ArgumentParser(description="雨课堂自动播放命令行版")
    parser.add_argument("--url", default=defaults.url, help="目标课程页面链接")
    parser.add_argument("--browser-path", default=find_browser_path(), help="Chrome/Edge 浏览器路径")
    parser.add_argument("--user-data-dir", default=defaults.user_data_dir, help="浏览器用户数据目录")
    parser.add_argument("--logs-dir", default=defaults.logs_dir, help="日志输出目录")
    parser.add_argument("--poll-seconds", type=float, default=defaults.poll_seconds, help="页面轮询间隔秒数")
    parser.add_argument("--video-end-wait-seconds", type=int, default=defaults.video_end_wait_seconds, help="视频结束后等待多少秒再点下一单元")
    parser.add_argument("--exercise-wait-seconds", type=int, default=defaults.exercise_wait_seconds, help="非视频页等待多少秒再点下一单元")
    parser.add_argument("--page-load-timeout-ms", type=int, default=defaults.page_load_timeout_ms, help="页面加载超时时间")
    parser.add_argument("--next-retry-seconds", type=int, default=defaults.next_retry_seconds, help="点击下一单元失败后的重试间隔")
    parser.add_argument("--status-log-interval-seconds", type=int, default=defaults.status_log_interval_seconds, help="视频进度日志输出间隔")
    parser.add_argument("--max-runtime-seconds", type=int, default=defaults.max_runtime_seconds, help="有限模式下的最大运行时间")
    parser.add_argument("--test-seek-to-end-after-seconds", type=int, default=defaults.test_seek_to_end_after_seconds, help="测试：多少秒后尝试快进到结尾")
    parser.add_argument("--test-force-ended-after-seconds", type=int, default=defaults.test_force_ended_after_seconds, help="测试：多少秒后模拟视频结束")
    parser.add_argument("--headless", action="store_true", help="无头模式运行")
    parser.add_argument("--disable-auto-return-after-login", action="store_true", help="登录成功后不自动回到原课程页")
    parser.set_defaults(infinite_runtime=defaults.infinite_runtime)
    parser.add_argument("--infinite-runtime", dest="infinite_runtime", action="store_true", help="无限运行时间")
    parser.add_argument("--finite-runtime", dest="infinite_runtime", action="store_false", help="启用最大运行时间限制")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = AutomationConfig(
        url=args.url,
        browser_path=args.browser_path,
        user_data_dir=args.user_data_dir,
        logs_dir=args.logs_dir,
        poll_seconds=args.poll_seconds,
        video_end_wait_seconds=args.video_end_wait_seconds,
        exercise_wait_seconds=args.exercise_wait_seconds,
        page_load_timeout_ms=args.page_load_timeout_ms,
        next_retry_seconds=args.next_retry_seconds,
        status_log_interval_seconds=args.status_log_interval_seconds,
        headless=args.headless,
        auto_return_to_target_after_login=not args.disable_auto_return_after_login,
        infinite_runtime=args.infinite_runtime,
        max_runtime_seconds=args.max_runtime_seconds,
        test_seek_to_end_after_seconds=args.test_seek_to_end_after_seconds,
        test_force_ended_after_seconds=args.test_force_ended_after_seconds,
    )
    runner = YukeTangAutomation(config, on_event=lambda event: print(event.to_console_line(), flush=True))
    runner.run()
    return 0
