"""
YKT Browser - 雨课堂自动播放引擎
基于 Playwright 的浏览器自动化引擎
"""

import os
import time
import threading
import queue
from enum import Enum
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


class MsgType(Enum):
    LOG = "log"
    STATUS = "status"
    PROGRESS = "progress"
    STATS = "stats"
    FINISHED = "finished"


class PageType(Enum):
    VIDEO = "视频"
    EXERCISE = "习题"
    UNKNOWN = "未知"


class EngineStatus(Enum):
    IDLE = "空闲"
    STARTING = "启动中"
    RUNNING = "运行中"
    PAUSED = "已暂停"
    STOPPING = "停止中"
    STOPPED = "已停止"
    WAITING_LOGIN = "等待登录"


class YuketangEngine:
    """雨课堂自动播放引擎"""

    def __init__(self, msg_queue: queue.Queue):
        self.msg_queue = msg_queue
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self._thread = None
        self.browser = None
        self.page = None
        self.stats = {"videos": 0, "exercises": 0, "errors": 0, "units": 0}
        self.start_time = None
        self.status = EngineStatus.IDLE

    # ── Message helpers ──────────────────────────────────────────

    def _emit(self, msg_type: MsgType, data):
        self.msg_queue.put((msg_type, data))

    def _log(self, level: str, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._emit(MsgType.LOG, (ts, level, message))

    def _set_status(self, status: EngineStatus):
        self.status = status
        self._emit(MsgType.STATUS, status.value)

    def _update_stats(self):
        elapsed = int(time.time() - self.start_time) if self.start_time else 0
        self._emit(MsgType.STATS, {**self.stats, "elapsed": elapsed})

    # ── Control API ──────────────────────────────────────────────

    def start(self, url: str):
        if self._thread and self._thread.is_alive():
            self._log("WARNING", "引擎已在运行中")
            return
        self._stop_event.clear()
        self._pause_event.set()
        self.stats = {"videos": 0, "exercises": 0, "errors": 0, "units": 0}
        self.start_time = time.time()
        self._thread = threading.Thread(target=self._run, args=(url,), daemon=True)
        self._thread.start()

    def stop(self):
        self._log("INFO", "正在停止...")
        self._stop_event.set()
        self._pause_event.set()  # unblock pause so thread can exit
        self._set_status(EngineStatus.STOPPING)

    def pause(self):
        self._pause_event.clear()
        self._set_status(EngineStatus.PAUSED)
        self._log("INFO", "已暂停")

    def resume(self):
        self._pause_event.set()
        self._set_status(EngineStatus.RUNNING)
        self._log("INFO", "已恢复")

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    # ── Helpers ──────────────────────────────────────────────────

    def _sleep(self, seconds: float) -> bool:
        """Interruptible sleep. Returns False if stopped."""
        for _ in range(int(seconds * 10)):
            if self._stop_event.is_set():
                return False
            self._pause_event.wait()
            if self._stop_event.is_set():
                return False
            time.sleep(0.1)
        return True

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        s = int(seconds)
        if s >= 3600:
            return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
        return f"{s // 60:02d}:{s % 60:02d}"

    # ── Main automation loop ─────────────────────────────────────

    def _run(self, url: str):
        try:
            self._set_status(EngineStatus.STARTING)
            self._log("INFO", "正在启动浏览器...")

            user_data_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "browser_data"
            )

            with sync_playwright() as p:
                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=user_data_dir,
                        headless=False,
                        viewport={"width": 1366, "height": 768},
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--autoplay-policy=no-user-gesture-required",
                        ],
                    )
                except Exception as launch_err:
                    err_msg = str(launch_err)
                    if "Executable doesn't exist" in err_msg or "browserType.launch" in err_msg:
                        self._log("ERROR", "Chromium 浏览器未安装！")
                        self._log("ERROR", "请在命令行运行: playwright install chromium")
                    else:
                        self._log("ERROR", f"浏览器启动失败: {err_msg}")
                    return

                self.page = context.pages[0] if context.pages else context.new_page()
                self.page.set_default_timeout(15000)

                self._log("INFO", f"正在导航到: {url}")
                self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                self._set_status(EngineStatus.RUNNING)
                self._log("SUCCESS", "页面加载完成")

                # Wait for content / login
                if not self._wait_for_content():
                    return

                # Main loop
                while not self._stop_event.is_set():
                    self._pause_event.wait()
                    if self._stop_event.is_set():
                        break
                    self._process_page()
                    self._update_stats()

                context.close()

        except Exception as e:
            self._log("ERROR", f"引擎异常: {e}")
            self.stats["errors"] += 1
        finally:
            self._set_status(EngineStatus.STOPPED)
            self._emit(MsgType.FINISHED, None)
            self._log("INFO", "引擎已停止")

    # ── Content / login detection ────────────────────────────────

    def _wait_for_content(self) -> bool:
        self._log("INFO", "等待页面内容加载...")
        login_warned = False
        for attempt in range(120):  # up to 10 min
            if self._stop_event.is_set():
                return False
            try:
                # Detect login redirect
                current_url = self.page.url
                is_login_page = any(k in current_url for k in (
                    "portal/home", "login", "oauth", "auth",
                ))

                if is_login_page and not login_warned:
                    login_warned = True
                    self._set_status(EngineStatus.WAITING_LOGIN)
                    self._log("WARNING", "检测到登录页面，请在浏览器中完成登录")
                    self._log("INFO", "登录后将自动继续...")

                if self._has_known_content():
                    self._log("SUCCESS", "页面内容已就绪")
                    return True

                # After redirect back from login, re-navigate
                if login_warned and not is_login_page and not self._has_known_content():
                    self._log("INFO", "检测到页面变化，等待内容加载...")

                if attempt == 6 and not login_warned:
                    login_warned = True
                    self._set_status(EngineStatus.WAITING_LOGIN)
                    self._log("WARNING", "未检测到课程内容，请在浏览器中完成登录")
            except Exception:
                pass
            time.sleep(5)
        self._log("ERROR", "等待页面内容超时（10分钟）")
        return False

    def _has_known_content(self) -> bool:
        # Check text-based markers
        for text in ("发表评论", "习题", "提交"):
            try:
                if self.page.query_selector(f"text={text}"):
                    return True
            except Exception:
                pass
        # Check "下一单元" via CSS (it's inside span.btn-next)
        try:
            if self.page.query_selector("span.btn-next"):
                return True
        except Exception:
            pass
        # JS fallback
        try:
            return self.page.evaluate("""
                () => [...document.querySelectorAll('span')]
                    .some(s => s.textContent.includes('下一单元'))
            """)
        except Exception:
            return False

    # ── Page type detection ──────────────────────────────────────

    def _detect_page_type(self) -> PageType:
        try:
            time.sleep(2)
            # Video page: "发表评论" or a <video> element present
            has_comment = self.page.query_selector("text=发表评论")
            has_video = self.page.evaluate(
                "document.getElementsByTagName('video').length > 0"
            )
            if has_comment or has_video:
                return PageType.VIDEO
            # Exercise page: "习题" or "提交"
            if self.page.query_selector("text=习题") or self.page.query_selector("text=提交"):
                return PageType.EXERCISE
            return PageType.UNKNOWN
        except Exception as e:
            self._log("ERROR", f"页面类型检测失败: {e}")
            return PageType.UNKNOWN

    # ── Page processing ──────────────────────────────────────────

    def _process_page(self):
        try:
            if not self._sleep(3):
                return

            page_type = self._detect_page_type()

            if page_type == PageType.VIDEO:
                self._handle_video()
            elif page_type == PageType.EXERCISE:
                self._handle_exercise()
            else:
                self._log("WARNING", "未识别页面类型，等待5秒后重试...")
                if not self._sleep(5):
                    return
                page_type = self._detect_page_type()
                if page_type == PageType.VIDEO:
                    self._handle_video()
                elif page_type == PageType.EXERCISE:
                    self._handle_exercise()
                else:
                    self._log("WARNING", "仍无法识别页面类型，尝试点击下一单元")
                    self._click_next()

        except Exception as e:
            self._log("ERROR", f"处理页面出错: {e}")
            self.stats["errors"] += 1
            self._sleep(5)

    # ── Video handling ───────────────────────────────────────────

    def _handle_video(self):
        self._log("SUCCESS", "✓ 检测到视频页面")

        # Inject autoplay script (user-specified)
        try:
            self.page.evaluate("""
                setInterval(function () {
                    try {
                        var current_video = document.getElementsByTagName('video')[0]
                        if (current_video) current_video.play()
                    } catch(e) {}
                }, 100)
            """)
            self._log("INFO", "→ 已注入自动播放脚本")
        except Exception as e:
            self._log("ERROR", f"注入脚本失败: {e}")
            return

        # Poll video progress
        # Because the injected script keeps calling play(), the video loops.
        # Detect completion: progress was >=90% then drops below 10%.
        self._log("INFO", "⏳ 等待视频播放完毕...")
        last_progress_log = 0
        reached_high = False   # True once progress >= 90%

        while not self._stop_event.is_set():
            self._pause_event.wait()
            if self._stop_event.is_set():
                return
            try:
                result = self.page.evaluate("""
                    () => {
                        var v = document.getElementsByTagName('video')[0];
                        if (!v) return {current: 0, duration: 0};
                        return {
                            current: v.currentTime,
                            duration: v.duration || 0
                        };
                    }
                """)

                duration = result["duration"]
                current = result["current"]

                if duration > 0:
                    pct = current / duration * 100
                    cur_fmt = self._fmt_time(current)
                    tot_fmt = self._fmt_time(duration)
                    self._emit(MsgType.PROGRESS, {
                        "current": current,
                        "duration": duration,
                        "percent": pct,
                    })
                    if current - last_progress_log >= 30 or last_progress_log == 0:
                        self._log("INFO", f"  🎬 视频进度: {cur_fmt} / {tot_fmt} ({pct:.0f}%)")
                        last_progress_log = current

                    # Track high-water mark
                    if pct >= 90:
                        reached_high = True

                    # Detect loop-back: was at >=90%, now dropped below 10%
                    if reached_high and pct < 10:
                        self._log("INFO", "检测到视频回到开头 → 已完整播放一次")
                        break

            except Exception as e:
                self._log("WARNING", f"获取视频状态失败: {e}")

            time.sleep(2)

        if self._stop_event.is_set():
            return

        self._log("SUCCESS", "✓ 视频播放完毕")
        self.stats["videos"] += 1
        self._update_stats()

        self._log("INFO", "⏳ 等待10秒后切换下一单元...")
        if not self._sleep(10):
            return

        self._click_next()

    # ── Exercise handling ────────────────────────────────────────

    def _handle_exercise(self):
        self._log("SUCCESS", "✓ 检测到习题页面")
        self.stats["exercises"] += 1
        self._update_stats()

        self._log("INFO", "⏳ 等待10秒...")
        if not self._sleep(10):
            return

        self._click_next()

    # ── Navigation ───────────────────────────────────────────────

    def _click_next(self):
        try:
            # Try CSS selectors matching the actual DOM: span.btn-next
            next_btn = None
            for selector in (
                'span.btn-next',
                'span.btn-next span',
                ':text("下一单元")',
                'text=下一单元',
                'span:has-text("下一单元")',
            ):
                try:
                    next_btn = self.page.query_selector(selector)
                    if next_btn:
                        break
                except Exception:
                    continue

            # JS fallback: find any element whose textContent contains "下一单元"
            if not next_btn:
                found = self.page.evaluate("""
                    () => {
                        const spans = document.querySelectorAll('span');
                        for (const s of spans) {
                            if (s.textContent.trim() === '下一单元' ||
                                s.classList.contains('btn-next')) {
                                s.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                if found:
                    self._log("SUCCESS", "→ 已点击「下一单元」(JS)")
                    self.stats["units"] += 1
                    self._update_stats()
                    self._sleep(2)
                    try:
                        self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except PlaywrightTimeout:
                        self._log("WARNING", "页面加载超时，继续执行...")
                    self._sleep(3)
                    return

                self._log("WARNING", "未找到「下一单元」按钮")
                self._log("INFO", "🎉 课程可能已全部完成！")
                self._stop_event.set()
                return

            next_btn.click()
            self._log("SUCCESS", "→ 已点击「下一单元」")
            self.stats["units"] += 1
            self._update_stats()

            self._sleep(2)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            except PlaywrightTimeout:
                self._log("WARNING", "页面加载超时，继续执行...")
            self._sleep(3)

        except Exception as e:
            self._log("ERROR", f"点击下一单元失败: {e}")
            self.stats["errors"] += 1
