from __future__ import annotations

import json
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import BrowserContext, Error, Frame, Page, TimeoutError, sync_playwright

from .models import AutomationConfig, LogEvent, RuntimeStatus
from .session_logging import SessionLogger


COMMENT_TEXT = "发表评论"
EXERCISE_TEXT = "习题"
SUBMIT_TEXT = "提交"
LOGIN_TEXT = "登录"
NEXT_UNIT_TEXT = "下一单元"
CAPTCHA_TEXT = "安全验证"
CAPTCHA_HINT_TEXT = "拖动下方滑块完成拼图"


def _js_string(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


KEEPALIVE_SCRIPT = """
() => {
    if (window.__yktKeepAliveTimer) {
        return "already-running";
    }
    window.__yktKeepAliveTimer = setInterval(function () {
        var currentVideo = document.getElementsByTagName("video")[0];
        if (currentVideo) {
            var result = currentVideo.play();
            if (result && typeof result.catch === "function") {
                result.catch(function () {});
            }
        }
    }, 100);
    return "started";
}
"""
STOP_KEEPALIVE_SCRIPT = """
() => {
    const video = document.querySelector("video");
    if (window.__yktKeepAliveTimer) {
        clearInterval(window.__yktKeepAliveTimer);
        window.__yktKeepAliveTimer = null;
        return video ? "stopped-with-video" : "stopped";
    }
    return video ? "video-only" : "not-running";
}
"""
NEXT_BUTTON_PROBE_SCRIPT = f"""
() => {{
    const targetText = {_js_string(NEXT_UNIT_TEXT)};
    const normalize = (text) => (text || "").replace(/\\s+/g, " ").trim();
    const isVisible = (element) => {{
        if (!element) return false;
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return (
            style.visibility !== "hidden" &&
            style.display !== "none" &&
            style.opacity !== "0" &&
            rect.width > 0 &&
            rect.height > 0 &&
            rect.bottom > 0 &&
            rect.right > 0 &&
            rect.top < window.innerHeight &&
            rect.left < window.innerWidth
        );
    }};
    const isDisabled = (element) => {{
        if (!element) return false;
        return element.disabled ||
            element.getAttribute("aria-disabled") === "true" ||
            element.classList.contains("disabled");
    }};
    const buildPath = (element) => {{
        if (!element) return "";
        const parts = [];
        let current = element;
        while (current && current !== document.body && parts.length < 4) {{
            const tag = (current.tagName || "").toLowerCase();
            const id = current.id ? `#${{current.id}}` : "";
            const classNames = Array.from(current.classList || []).slice(0, 3).map((item) => `.${{item}}`).join("");
            parts.unshift(`${{tag}}${{id}}${{classNames}}`);
            current = current.parentElement;
        }}
        return parts.join(" > ");
    }};
    const score = (item) => {{
        let value = 0;
        if (item.text === targetText || item.ownText === targetText) value += 120;
        if (item.text.includes(targetText)) value += 60;
        if ((item.className || "").includes("btn-next")) value += 80;
        if ((item.className || "").includes("pointer")) value += 20;
        if (item.tag === "BUTTON" || item.tag === "A") value += 15;
        if (item.visible) value += 10;
        value += Math.round(Math.max(0, item.rect.left || 0) / 10);
        return value;
    }};

    const elements = Array.from(document.querySelectorAll("button, a, [role='button'], span, div"));
    const candidates = elements
        .map((element) => {{
            const rect = element.getBoundingClientRect();
            const style = window.getComputedStyle(element);
            const item = {{
                tag: element.tagName || "",
                text: normalize(element.innerText || element.textContent || ""),
                ownText: normalize(
                    Array.from(element.childNodes)
                        .filter((node) => node.nodeType === Node.TEXT_NODE)
                        .map((node) => node.textContent || "")
                        .join(" ")
                ),
                className: element.className || "",
                visible: isVisible(element),
                disabled: isDisabled(element),
                cursor: style.cursor,
                pointerEvents: style.pointerEvents,
                rect: {{
                    left: rect.left,
                    top: rect.top,
                    width: rect.width,
                    height: rect.height
                }},
                path: buildPath(element)
            }};
            return {{
                ...item,
                score: score(item)
            }};
        }})
        .filter((item) => item.text.includes(targetText) || item.ownText === targetText || item.className.includes("btn-next"))
        .sort((left, right) => right.score - left.score);

    return {{
        count: candidates.length,
        candidates: candidates.slice(0, 6)
    }};
}}
"""
CLICK_NEXT_SCRIPT = f"""
() => {{
    const targetText = {_js_string(NEXT_UNIT_TEXT)};
    const normalize = (text) => (text || "").replace(/\\s+/g, " ").trim();
    const isVisible = (element) => {{
        if (!element) return false;
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.visibility !== "hidden" &&
            style.display !== "none" &&
            style.opacity !== "0" &&
            rect.bottom > 0 &&
            rect.right > 0 &&
            rect.top < window.innerHeight &&
            rect.left < window.innerWidth &&
            rect.width > 0 &&
            rect.height > 0;
    }};

    const isDisabled = (element) => {{
        if (!element) return false;
        return element.disabled ||
            element.getAttribute("aria-disabled") === "true" ||
            element.classList.contains("disabled");
    }};

    const clickableAncestor = (element) => {{
        let current = element;
        while (current && current !== document.body) {{
            if (
                current.tagName === "BUTTON" ||
                current.tagName === "A" ||
                current.getAttribute("role") === "button" ||
                current.classList.contains("btn-next") ||
                current.classList.contains("pointer") ||
                current.onclick ||
                current.tabIndex >= 0
            ) {{
                return current;
            }}
            current = current.parentElement;
        }}
        return element;
    }};
    const score = (item) => {{
        let value = 0;
        if (item.text === targetText || item.ownText === targetText) value += 120;
        if (item.text.includes(targetText)) value += 60;
        if ((item.className || "").includes("btn-next")) value += 80;
        if ((item.className || "").includes("pointer")) value += 20;
        value += Math.round(Math.max(0, item.rect.left || 0) / 10);
        return value;
    }};

    const elements = Array.from(document.querySelectorAll("button, a, [role='button'], span, div"));
    const exactMatches = elements
        .map((element) => {{
            const rect = element.getBoundingClientRect();
            return {{
                element,
                text: normalize(element.innerText || element.textContent || ""),
                ownText: normalize(
                    Array.from(element.childNodes)
                        .filter((node) => node.nodeType === Node.TEXT_NODE)
                        .map((node) => node.textContent || "")
                        .join(" ")
                ),
                className: element.className || "",
                rect: {{
                    left: rect.left,
                    top: rect.top,
                    width: rect.width,
                    height: rect.height
                }}
            }};
        }})
        .filter((item) => isVisible(item.element) && !isDisabled(item.element))
        .filter((item) => item.text === targetText || item.ownText === targetText)
        .sort((left, right) => score(right) - score(left));

    const fuzzyMatches = elements
        .map((element) => {{
            const rect = element.getBoundingClientRect();
            return {{
                element,
                text: normalize(element.innerText || element.textContent || ""),
                ownText: normalize(
                    Array.from(element.childNodes)
                        .filter((node) => node.nodeType === Node.TEXT_NODE)
                        .map((node) => node.textContent || "")
                        .join(" ")
                ),
                className: element.className || "",
                rect: {{
                    left: rect.left,
                    top: rect.top,
                    width: rect.width,
                    height: rect.height
                }}
            }};
        }})
        .filter((item) => isVisible(item.element) && !isDisabled(item.element))
        .filter((item) => item.text.includes(targetText))
        .sort((left, right) => score(right) - score(left));

    const target = (exactMatches[0] || fuzzyMatches[0] || {{}}).element;
    if (!target) {{
        return {{ clicked: false, reason: "not-found" }};
    }}

    const clickable = clickableAncestor(target);
    if (isDisabled(clickable)) {{
        return {{ clicked: false, reason: "disabled" }};
    }}

    clickable.scrollIntoView({{ block: "center", inline: "center", behavior: "auto" }});
    clickable.focus?.();
    const rect = clickable.getBoundingClientRect();
    const centerX = Math.min(window.innerWidth - 1, Math.max(1, rect.left + rect.width / 2));
    const centerY = Math.min(window.innerHeight - 1, Math.max(1, rect.top + rect.height / 2));
    const topmost = document.elementFromPoint(centerX, centerY);
    const dispatchTarget =
        topmost && (topmost === clickable || clickable.contains(topmost) || topmost.contains(clickable))
            ? topmost
            : clickable;

    dispatchTarget.dispatchEvent(new PointerEvent("pointerover", {{ bubbles: true, cancelable: true, composed: true, pointerType: "mouse", clientX: centerX, clientY: centerY }}));
    dispatchTarget.dispatchEvent(new MouseEvent("mouseover", {{ bubbles: true, cancelable: true, view: window, clientX: centerX, clientY: centerY }}));
    dispatchTarget.dispatchEvent(new PointerEvent("pointerdown", {{ bubbles: true, cancelable: true, composed: true, pointerType: "mouse", clientX: centerX, clientY: centerY }}));
    dispatchTarget.dispatchEvent(new MouseEvent("mousedown", {{ bubbles: true, cancelable: true, view: window, clientX: centerX, clientY: centerY }}));
    dispatchTarget.dispatchEvent(new PointerEvent("pointerup", {{ bubbles: true, cancelable: true, composed: true, pointerType: "mouse", clientX: centerX, clientY: centerY }}));
    dispatchTarget.dispatchEvent(new MouseEvent("mouseup", {{ bubbles: true, cancelable: true, view: window, clientX: centerX, clientY: centerY }}));
    dispatchTarget.click();
    dispatchTarget.dispatchEvent(new MouseEvent("click", {{ bubbles: true, cancelable: true, view: window, clientX: centerX, clientY: centerY }}));
    return {{
        clicked: true,
        reason: "clicked",
        text: normalize(clickable.innerText || clickable.textContent || ""),
        className: clickable.className || "",
        strategy: "dom-dispatch",
        dispatchTag: dispatchTarget.tagName || "",
        dispatchClassName: dispatchTarget.className || ""
    }};
}}
"""
FRAME_STATE_SCRIPT = f"""
() => {{
    const commentText = {_js_string(COMMENT_TEXT)};
    const exerciseText = {_js_string(EXERCISE_TEXT)};
    const submitText = {_js_string(SUBMIT_TEXT)};
    const captchaText = {_js_string(CAPTCHA_TEXT)};
    const captchaHintText = {_js_string(CAPTCHA_HINT_TEXT)};
    const nextText = {_js_string(NEXT_UNIT_TEXT)};
    const text = document.body ? document.body.innerText.replace(/\\s+/g, " ").trim() : "";
    const video = document.querySelector("video");
    const hasSubmitButton = Array.from(
        document.querySelectorAll("button, input[type='button'], input[type='submit'], span, div")
    ).some((element) => {{
        const content = (element.innerText || element.textContent || element.value || "").replace(/\\s+/g, " ").trim();
        return content === submitText;
    }});

    return {{
        url: location.href,
        title: document.title || "",
        textPreview: text.slice(0, 320),
        hasComment: text.includes(commentText),
        hasExercise: text.includes(exerciseText),
        hasSubmit: text.includes(submitText) || hasSubmitButton,
        hasPassword: !!document.querySelector("input[type='password']"),
        hasVideo: !!video,
        hasCaptcha: text.includes(captchaText) || text.includes(captchaHintText) || location.href.includes("captcha"),
        hasNextUnit: text.includes(nextText),
        video: video ? {{
            ended: video.ended,
            paused: video.paused,
            currentTime: Number.isFinite(video.currentTime) ? video.currentTime : 0,
            duration: Number.isFinite(video.duration) ? video.duration : 0
        }} : null
    }};
}}
"""


@dataclass(slots=True)
class FrameSnapshot:
    frame: Frame
    url: str
    title: str
    text_preview: str
    has_comment: bool
    has_exercise: bool
    has_submit: bool
    has_password: bool
    has_video: bool
    has_captcha: bool
    has_next_unit: bool
    is_visible: bool
    viewport_note: str
    video: dict[str, Any] | None


@dataclass(slots=True)
class PageState:
    kind: str
    reason: str
    snapshot: FrameSnapshot | None
    signature: str


class YukeTangAutomation:
    def __init__(
        self,
        config: AutomationConfig,
        on_event: Callable[[LogEvent], None] | None = None,
        on_status: Callable[[RuntimeStatus], None] | None = None,
    ) -> None:
        self.config = config.normalized()
        self.on_event = on_event
        self.on_status = on_status
        self.stop_requested = False
        self.started_monotonic = 0.0
        self.status = RuntimeStatus(stage="idle", last_message="等待启动")
        self.session_logger: SessionLogger | None = None

    def stop(self) -> None:
        self.stop_requested = True

    def run(self) -> None:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        if not self.config.browser_path:
            raise RuntimeError("未找到 Chrome/Edge，请在界面里手动指定浏览器路径。")

        session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.session_logger = SessionLogger(self.config.logs_dir, session_id)
        self.session_logger.write_config(self.config)
        self.started_monotonic = time.time()
        self._publish_status(
            session_id=session_id,
            is_running=True,
            stage="launching",
            last_message="准备启动浏览器",
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            session_dir=str(self.session_logger.session_dir),
            text_log_path=str(self.session_logger.text_log_path),
            jsonl_log_path=str(self.session_logger.jsonl_log_path),
        )
        self._emit("INFO", "SYSTEM", "SESSION_START", "自动化会话已启动", details=f"会话目录: {self.session_logger.session_dir}")

        context: BrowserContext | None = None
        try:
            with sync_playwright() as playwright:
                context = self._launch_context(playwright)
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(min(10000, self.config.page_load_timeout_ms))
                self._safe_goto(page, self.config.url)
                self._emit("INFO", "NAVIGATION", "PAGE_OPENED", "目标页面已打开", details=self.config.url)
                self._emit(
                    "INFO",
                    "SYSTEM",
                    "LOGIN_HINT",
                    "如果首次运行跳到登录页，请直接在浏览器中完成登录。",
                    suggestion="登录状态会自动保存在用户数据目录中，后续会复用。",
                )

                last_signature = ""
                state_entered_at = 0.0
                keepalive_signature = ""
                ended_at = 0.0
                previous_kind = ""
                login_logged_at = 0.0
                captcha_logged_at = 0.0
                unknown_logged_at = 0.0
                last_video_log_at = 0.0
                next_click_retry_at = 0.0
                test_seek_done_for_signature = ""
                test_force_ended_done_for_signature = ""
                pending_navigation_signature = ""
                pending_navigation_logged = False
                pending_navigation_checked_at = 0.0
                pending_navigation_details = ""
                last_video_signature = ""
                last_video_current = 0.0
                last_video_duration = 0.0

                while not self.stop_requested:
                    now = time.time()
                    self._publish_status(elapsed_seconds=now - self.started_monotonic)

                    if (
                        not self.config.infinite_runtime
                        and self.config.max_runtime_seconds
                        and now - self.started_monotonic >= self.config.max_runtime_seconds
                    ):
                        self._emit("INFO", "SYSTEM", "MAX_RUNTIME_REACHED", "达到设定的测试运行时长，自动结束本次会话。")
                        break
                    if page.is_closed():
                        self._emit("WARNING", "SYSTEM", "PAGE_CLOSED", "浏览器页面已被关闭，会话结束。")
                        break

                    page_state = self._inspect_page(page)
                    current_url = page.url

                    if page_state.signature != last_signature:
                        last_signature = page_state.signature
                        state_entered_at = now
                        ended_at = 0.0
                        next_click_retry_at = 0.0
                        pending_navigation_signature = ""
                        pending_navigation_logged = False
                        pending_navigation_details = ""
                        if page_state.kind != "video":
                            keepalive_signature = ""
                            last_video_signature = ""
                            last_video_current = 0.0
                            last_video_duration = 0.0
                        self._publish_status(
                            page_kind=page_state.kind,
                            page_url=page_state.snapshot.url if page_state.snapshot else current_url,
                            page_title=page_state.snapshot.title if page_state.snapshot else "",
                            countdown_seconds=-1,
                            last_message=page_state.reason,
                            stage=self._stage_from_kind(page_state.kind),
                        )
                        if page_state.snapshot:
                            self._emit(
                                "INFO",
                                "PAGE",
                                "PAGE_CLASSIFIED",
                                f"识别到页面类型: {page_state.kind}",
                                details=f"{page_state.reason} | {page_state.snapshot.url}",
                            )
                        else:
                            self._emit("INFO", "PAGE", "PAGE_CLASSIFIED", f"页面类型变化: {page_state.kind}", details=page_state.reason)

                    if (
                        previous_kind == "login"
                        and page_state.kind != "login"
                        and "portal/home" not in current_url
                        and self.config.auto_return_to_target_after_login
                    ):
                        self._emit("SUCCESS", "AUTH", "LOGIN_COMPLETED", "检测到登录流程结束，重新回到目标课程页面。")
                        self._safe_goto(page, self.config.url)
                        previous_kind = page_state.kind
                        self._interruptible_sleep(2.0)
                        continue

                    if pending_navigation_signature and now >= pending_navigation_checked_at and not pending_navigation_logged:
                        if page_state.signature == pending_navigation_signature:
                            current_probe = self._probe_next_unit(page)
                            self._emit(
                                "WARNING",
                                "NAVIGATION",
                                "NEXT_CLICK_NO_NAVIGATION",
                                "点击“下一单元”后页面没有发生切换。",
                                details=(
                                    "这通常表示平台尚未认定当前内容已完成，或按钮虽然可见但还未真正放行。"
                                    f" | {pending_navigation_details} | {self._format_next_probe(current_probe)}"
                                ),
                                suggestion="先观察页面是否真正播放完成，必要时手动确认是否有额外校验或弹窗。",
                                data={"next_probe": current_probe},
                            )
                        pending_navigation_logged = True

                    if page_state.kind == "captcha":
                        self._publish_status(stage="waiting_captcha", last_message="检测到安全验证，等待手动处理", countdown_seconds=-1)
                        if now - captcha_logged_at >= 12:
                            self._emit(
                                "WARNING",
                                "AUTH",
                                "CAPTCHA_REQUIRED",
                                "检测到安全验证或滑块验证码。",
                                suggestion="请在浏览器中手动完成验证，脚本会在验证通过后继续运行。",
                            )
                            captcha_logged_at = now

                    elif page_state.kind == "login":
                        self._publish_status(stage="waiting_login", last_message="停留在登录页，等待手动登录", countdown_seconds=-1)
                        if now - login_logged_at >= 12:
                            self._emit(
                                "WARNING",
                                "AUTH",
                                "LOGIN_REQUIRED",
                                "当前停留在登录页，需要先登录。",
                                suggestion="请在浏览器中完成账号登录，完成后脚本会自动继续。",
                            )
                            login_logged_at = now

                    elif page_state.kind == "video" and page_state.snapshot:
                        self._publish_status(stage="running", keepalive_state="active", last_message="视频页监控中")
                        if keepalive_signature != page_state.signature:
                            result = self._ensure_keepalive(page_state.snapshot)
                            keepalive_signature = page_state.signature
                            self._emit("SUCCESS", "VIDEO", "KEEPALIVE_INJECTED", "已向视频页注入保活脚本。", details=f"注入结果: {result}")

                        video_state = self._read_video_state(page_state.snapshot)
                        if not video_state:
                            if now - last_video_log_at >= self.config.status_log_interval_seconds:
                                self._emit("INFO", "VIDEO", "VIDEO_ELEMENT_WAITING", "已识别为视频页，但暂时还没拿到 video 元素。")
                                last_video_log_at = now
                            self._interruptible_sleep(self.config.poll_seconds)
                            previous_kind = page_state.kind
                            continue

                        current_time = float(video_state.get("currentTime", 0.0))
                        duration = float(video_state.get("duration", 0.0))
                        paused = bool(video_state.get("paused"))
                        is_ended = bool(video_state.get("ended"))
                        previous_ratio = 0.0
                        current_ratio = (current_time / duration) if duration > 0 else 0.0
                        loop_completed = False
                        if last_video_signature == page_state.signature and last_video_duration > 0:
                            previous_ratio = last_video_current / last_video_duration
                            if previous_ratio >= 0.9 and current_ratio <= 0.1 and current_time + 2 < last_video_current:
                                loop_completed = True

                        self._publish_status(
                            video_current=current_time,
                            video_duration=duration,
                            video_paused=paused,
                            video_ended=is_ended,
                        )
                        if now - last_video_log_at >= self.config.status_log_interval_seconds:
                            self._emit(
                                "INFO",
                                "VIDEO",
                                "VIDEO_PROGRESS",
                                "视频播放状态已更新。",
                                details=f"current={current_time:.1f}s, duration={duration:.1f}s, paused={paused}, ended={is_ended}",
                            )
                            last_video_log_at = now

                        if (
                            self.config.test_seek_to_end_after_seconds > 0
                            and test_seek_done_for_signature != page_state.signature
                            and now - state_entered_at >= self.config.test_seek_to_end_after_seconds
                        ):
                            if self._seek_video_to_end_for_test(page_state.snapshot):
                                test_seek_done_for_signature = page_state.signature
                                self._emit("WARNING", "TEST", "TEST_SEEK_TO_END", "测试模式已触发：视频已尝试快进到结尾附近。")

                        if (
                            self.config.test_force_ended_after_seconds > 0
                            and test_force_ended_done_for_signature != page_state.signature
                            and ended_at == 0.0
                            and now - state_entered_at >= self.config.test_force_ended_after_seconds
                        ):
                            ended_at = now
                            test_force_ended_done_for_signature = page_state.signature
                            self._emit(
                                "WARNING",
                                "TEST",
                                "TEST_FORCE_ENDED",
                                "测试模式已触发：脚本侧模拟视频播放完成。",
                                suggestion=f"{self.config.video_end_wait_seconds} 秒后会尝试点击“下一单元”。",
                            )

                        if is_ended and ended_at == 0.0:
                            ended_at = now
                            stop_result = self._stop_keepalive(page_state.snapshot)
                            self._publish_status(keepalive_state="inactive")
                            self._emit(
                                "SUCCESS",
                                "VIDEO",
                                "VIDEO_ENDED",
                                "检测到视频已播放完成。",
                                details=f"保活脚本状态: {stop_result}",
                                suggestion=f"{self.config.video_end_wait_seconds} 秒后会尝试点击“下一单元”。",
                            )

                        if loop_completed and ended_at == 0.0:
                            ended_at = now
                            stop_result = self._stop_keepalive(page_state.snapshot)
                            self._publish_status(keepalive_state="inactive")
                            self._emit(
                                "SUCCESS",
                                "VIDEO",
                                "VIDEO_LOOP_COMPLETED",
                                "检测到视频已完整播放一轮并重新回到开头。",
                                details=(
                                    f"previous_ratio={previous_ratio:.2%}, current_ratio={current_ratio:.2%}, "
                                    f"previous_time={last_video_current:.1f}s, current_time={current_time:.1f}s, "
                                    f"保活脚本状态: {stop_result}"
                                ),
                                suggestion=f"{self.config.video_end_wait_seconds} 秒后会尝试点击“下一单元”。",
                            )

                        if ended_at > 0.0:
                            remaining = max(0, int(self.config.video_end_wait_seconds - (now - ended_at)))
                            self._publish_status(countdown_seconds=remaining, last_message="等待视频结束后的自动跳转")
                            if now >= ended_at + self.config.video_end_wait_seconds and now >= next_click_retry_at:
                                click_result = self._click_next_unit(page)
                                if click_result.get("clicked"):
                                    probe_summary = self._format_next_probe(click_result.get("probe", {}))
                                    self._publish_status(next_clicks=self.status.next_clicks + 1, countdown_seconds=-1)
                                    self._emit(
                                        "SUCCESS",
                                        "NAVIGATION",
                                        "NEXT_CLICKED",
                                        "已点击“下一单元”。",
                                        details=(
                                            f"文本命中: {click_result.get('text', '未知')} | "
                                            f"策略: {click_result.get('strategy', '未知')} | "
                                            f"{probe_summary}"
                                        ),
                                        data={"click_result": click_result},
                                    )
                                    keepalive_signature = ""
                                    ended_at = 0.0
                                    pending_navigation_signature = page_state.signature
                                    pending_navigation_checked_at = now + 4.0
                                    pending_navigation_logged = False
                                    pending_navigation_details = f"触发策略: {click_result.get('strategy', '未知')} | {probe_summary}"
                                    next_click_retry_at = now + max(5.0, float(self.config.next_retry_seconds))
                                    self._interruptible_sleep(3.0)
                                else:
                                    next_click_retry_at = now + self.config.next_retry_seconds
                                    self._emit(
                                        "WARNING",
                                        "NAVIGATION",
                                        "NEXT_CLICK_BLOCKED",
                                        "尝试点击“下一单元”失败。",
                                        details=(
                                            f"失败原因: {click_result.get('reason', '未知')} | "
                                            f"策略: {click_result.get('strategy', '未知')} | "
                                            f"{self._format_next_probe(click_result.get('probe', {}))}"
                                        ),
                                        suggestion="页面可能还未真正放行下一单元，稍后会自动重试。",
                                        data={"click_result": click_result},
                                    )
                        else:
                            self._publish_status(countdown_seconds=-1)

                        last_video_signature = page_state.signature
                        last_video_current = current_time
                        last_video_duration = duration

                    elif page_state.kind == "exercise":
                        elapsed = now - state_entered_at
                        remaining = max(0, int(self.config.exercise_wait_seconds - elapsed))
                        self._publish_status(
                            stage="running",
                            countdown_seconds=remaining,
                            keepalive_state="inactive",
                            last_message="非视频页等待自动跳转",
                            video_current=0.0,
                            video_duration=0.0,
                            video_paused=False,
                            video_ended=False,
                        )
                        if remaining in {self.config.exercise_wait_seconds, 5, 1} and elapsed <= self.config.exercise_wait_seconds:
                            self._emit("INFO", "PAGE", "EXERCISE_COUNTDOWN", "当前为非视频页，等待倒计时后自动跳转。", details=f"剩余 {remaining} 秒。")
                        if elapsed >= self.config.exercise_wait_seconds and now >= next_click_retry_at:
                            click_result = self._click_next_unit(page)
                            if click_result.get("clicked"):
                                probe_summary = self._format_next_probe(click_result.get("probe", {}))
                                self._publish_status(next_clicks=self.status.next_clicks + 1, countdown_seconds=-1)
                                self._emit(
                                    "SUCCESS",
                                    "NAVIGATION",
                                    "NEXT_CLICKED",
                                    "已在非视频页点击“下一单元”。",
                                    details=(
                                        f"文本命中: {click_result.get('text', '未知')} | "
                                        f"策略: {click_result.get('strategy', '未知')} | "
                                        f"{probe_summary}"
                                    ),
                                    data={"click_result": click_result},
                                )
                                pending_navigation_signature = page_state.signature
                                pending_navigation_checked_at = now + 4.0
                                pending_navigation_logged = False
                                pending_navigation_details = f"触发策略: {click_result.get('strategy', '未知')} | {probe_summary}"
                                next_click_retry_at = now + max(5.0, float(self.config.next_retry_seconds))
                                self._interruptible_sleep(3.0)
                            else:
                                next_click_retry_at = now + self.config.next_retry_seconds
                                self._emit(
                                    "WARNING",
                                    "NAVIGATION",
                                    "NEXT_CLICK_BLOCKED",
                                    "非视频页自动点击“下一单元”失败。",
                                    details=(
                                        f"失败原因: {click_result.get('reason', '未知')} | "
                                        f"策略: {click_result.get('strategy', '未知')} | "
                                        f"{self._format_next_probe(click_result.get('probe', {}))}"
                                    ),
                                    data={"click_result": click_result},
                                )

                    else:
                        self._publish_status(
                            stage="loading",
                            countdown_seconds=-1,
                            keepalive_state="inactive",
                            last_message="等待页面出现可识别内容",
                        )
                        if now - unknown_logged_at >= 12:
                            self._emit(
                                "INFO",
                                "PAGE",
                                "PAGE_UNKNOWN",
                                "页面还没有出现可识别的关键信息。",
                                suggestion="如果长时间停留在这里，请检查是否有弹窗、验证码或网络加载问题。",
                            )
                            unknown_logged_at = now

                    previous_kind = page_state.kind
                    self._interruptible_sleep(self.config.poll_seconds)

            if self.stop_requested:
                self._emit("INFO", "SYSTEM", "STOP_REQUESTED", "收到停止请求，自动化已结束。")
        except Exception as exc:  # noqa: BLE001
            diagnosis = self._diagnose_exception(exc)
            self._publish_status(
                stage="error",
                is_running=False,
                last_message=diagnosis["message"],
                last_error_hint=diagnosis["suggestion"],
            )
            self._emit(
                "ERROR",
                diagnosis["category"],
                diagnosis["code"],
                diagnosis["message"],
                details=diagnosis["details"],
                suggestion=diagnosis["suggestion"],
            )
            raise
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            self._publish_status(
                is_running=False,
                stage="stopped" if self.stop_requested else self.status.stage,
                countdown_seconds=-1,
                keepalive_state="inactive",
            )
            self._emit("INFO", "SYSTEM", "SESSION_FINISHED", "自动化会话已结束。", details=f"日志目录: {self.status.session_dir}")

    def _launch_context(self, playwright: Any) -> BrowserContext:
        browser_path = Path(self.config.browser_path)
        if not browser_path.exists():
            raise FileNotFoundError(f"浏览器不存在: {browser_path}")
        profile_dir = Path(self.config.user_data_dir).resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._emit(
            "INFO",
            "SYSTEM",
            "BROWSER_LAUNCH",
            "正在启动浏览器。",
            details=f"浏览器: {browser_path} | 用户数据目录: {profile_dir}",
        )
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            executable_path=str(browser_path),
            headless=self.config.headless,
            no_viewport=True,
            args=["--start-maximized"],
        )

    def _safe_goto(self, page: Page, url: str) -> None:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.config.page_load_timeout_ms)
        except TimeoutError:
            self._emit(
                "WARNING",
                "NAVIGATION",
                "PAGE_LOAD_TIMEOUT",
                "页面加载超过设定超时时间，将继续在当前状态下监控。",
                details=f"URL: {url}",
                suggestion="如果页面一直不完整，可以检查网络或增大超时时间。",
            )

    def _ensure_keepalive(self, snapshot: FrameSnapshot) -> str:
        return str(snapshot.frame.evaluate(KEEPALIVE_SCRIPT))

    def _stop_keepalive(self, snapshot: FrameSnapshot) -> str:
        try:
            return str(snapshot.frame.evaluate(STOP_KEEPALIVE_SCRIPT))
        except Error:
            return "stop-error"
        except TimeoutError:
            return "stop-timeout"

    def _read_video_state(self, snapshot: FrameSnapshot) -> dict[str, Any] | None:
        try:
            raw = snapshot.frame.evaluate(
                """
                () => {
                    const video = document.querySelector("video");
                    if (!video) {
                        return null;
                    }
                    return {
                        ended: video.ended,
                        paused: video.paused,
                        currentTime: Number.isFinite(video.currentTime) ? video.currentTime : 0,
                        duration: Number.isFinite(video.duration) ? video.duration : 0
                    };
                }
                """
            )
        except Error:
            return None
        except TimeoutError:
            return None
        return raw

    def _seek_video_to_end_for_test(self, snapshot: FrameSnapshot) -> bool:
        try:
            return bool(
                snapshot.frame.evaluate(
                    """
                    () => {
                        const video = document.querySelector("video");
                        if (!video || !Number.isFinite(video.duration) || video.duration <= 5) {
                            return false;
                        }
                        video.currentTime = Math.max(0, video.duration - 1);
                        return true;
                    }
                    """
                )
            )
        except Error:
            return False
        except TimeoutError:
            return False

    def _probe_next_unit(self, page: Page) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for frame in page.frames:
            try:
                result = frame.evaluate(NEXT_BUTTON_PROBE_SCRIPT)
            except Error:
                continue
            except TimeoutError:
                continue
            for item in result.get("candidates", []):
                candidate = dict(item)
                candidate["frame_url"] = frame.url
                candidates.append(candidate)
        candidates.sort(key=lambda item: float(item.get("score", 0)), reverse=True)
        return {
            "count": len(candidates),
            "candidates": candidates[:6],
        }

    def _format_next_probe(self, probe: dict[str, Any]) -> str:
        candidates = probe.get("candidates") or []
        if not candidates:
            return "候选按钮: 0"
        best = candidates[0]
        rect = best.get("rect") or {}
        return (
            f"候选按钮: {probe.get('count', len(candidates))} | "
            f"best={best.get('tag', '?')} text={best.get('text', '')!r} "
            f"class={best.get('className', '')!r} visible={best.get('visible')} disabled={best.get('disabled')} "
            f"rect=({rect.get('left', 0):.0f},{rect.get('top', 0):.0f},{rect.get('width', 0):.0f},{rect.get('height', 0):.0f})"
        )

    def _click_next_unit(self, page: Page) -> dict[str, Any]:
        probe = self._probe_next_unit(page)
        last_result: dict[str, Any] = {"clicked": False, "reason": "not-found", "strategy": "none", "probe": probe}
        strategies = [
            self._click_next_by_locator,
            self._click_next_by_mouse,
            self._click_next_by_script,
        ]
        for strategy in strategies:
            result = strategy(page)
            if result:
                result.setdefault("probe", probe)
                last_result = result
            if result.get("clicked"):
                return result
        return last_result

    def _click_next_by_locator(self, page: Page) -> dict[str, Any]:
        selectors = [
            ".header-bar .btn-next",
            "span.btn-next.pointer",
            "span.btn-next",
            "div.btn-next",
            "button:has-text('下一单元')",
            "a:has-text('下一单元')",
            "[role='button']:has-text('下一单元')",
            "span:has-text('下一单元')",
        ]
        last_result: dict[str, Any] = {"clicked": False, "reason": "not-found", "strategy": "locator:none"}
        for frame in page.frames:
            for selector in selectors:
                try:
                    locator = frame.locator(selector)
                    count = locator.count()
                except Exception:
                    continue

                for index in range(min(count, 3)):
                    item = locator.nth(index)
                    try:
                        if not item.is_visible():
                            continue
                        text = item.inner_text().strip()
                        class_name = item.evaluate("(node) => node.className || ''")
                        item.scroll_into_view_if_needed()
                        item.hover(timeout=1500)
                        try:
                            item.click(timeout=2500)
                            strategy_name = f"locator:{selector}"
                        except Exception:
                            item.click(timeout=2500, force=True)
                            strategy_name = f"locator-force:{selector}"
                        return {
                            "clicked": True,
                            "reason": "clicked",
                            "strategy": strategy_name,
                            "text": text,
                            "className": class_name,
                        }
                    except Exception as exc:  # noqa: BLE001
                        last_result = {
                            "clicked": False,
                            "reason": str(exc),
                            "strategy": f"locator:{selector}",
                        }
        return last_result

    def _click_next_by_mouse(self, page: Page) -> dict[str, Any]:
        selectors = [
            ".header-bar .btn-next",
            "span.btn-next.pointer",
            "span.btn-next",
            "span:has-text('下一单元')",
            "button:has-text('下一单元')",
        ]
        last_result: dict[str, Any] = {"clicked": False, "reason": "not-found", "strategy": "mouse:none"}
        for frame in page.frames:
            for selector in selectors:
                try:
                    locator = frame.locator(selector).first
                    if not locator.is_visible():
                        continue
                    locator.scroll_into_view_if_needed()
                    locator.hover(timeout=1500)
                    box = locator.bounding_box()
                    if not box:
                        continue
                    center_x = box["x"] + box["width"] / 2
                    center_y = box["y"] + box["height"] / 2
                    text = locator.inner_text().strip()
                    class_name = locator.evaluate("(node) => node.className || ''")
                    page.mouse.move(center_x, center_y, steps=10)
                    page.mouse.click(center_x, center_y, delay=80)
                    return {
                        "clicked": True,
                        "reason": "clicked",
                        "strategy": f"mouse:{selector}",
                        "text": text,
                        "className": class_name,
                        "coordinates": {"x": round(center_x, 1), "y": round(center_y, 1)},
                    }
                except Exception as exc:  # noqa: BLE001
                    last_result = {
                        "clicked": False,
                        "reason": str(exc),
                        "strategy": f"mouse:{selector}",
                    }
        return last_result

    def _click_next_by_script(self, page: Page) -> dict[str, Any]:
        last_result: dict[str, Any] = {"clicked": False, "reason": "not-found", "strategy": "dom-dispatch"}
        for frame in page.frames:
            try:
                result = frame.evaluate(CLICK_NEXT_SCRIPT)
            except Error:
                continue
            except TimeoutError:
                continue
            if result:
                last_result = dict(result)
                if "strategy" not in last_result:
                    last_result["strategy"] = "dom-dispatch"
                if result.get("clicked"):
                    return last_result
        return last_result

    def _frame_visibility(self, page: Page, frame: Frame) -> tuple[bool, str]:
        if frame == page.main_frame:
            return True, "main-frame"

        try:
            element = frame.frame_element()
        except Exception:
            return False, "no-frame-element"

        try:
            metrics = element.evaluate(
                """
                (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const onScreen =
                        rect.width > 0 &&
                        rect.height > 0 &&
                        rect.bottom > 0 &&
                        rect.right > 0 &&
                        rect.top < window.innerHeight &&
                        rect.left < window.innerWidth &&
                        style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        style.opacity !== "0";
                    return {
                        onScreen,
                        top: rect.top,
                        left: rect.left,
                        width: rect.width,
                        height: rect.height,
                        display: style.display,
                        visibility: style.visibility,
                        opacity: style.opacity
                    };
                }
                """
            )
        except Exception:
            return False, "metrics-unavailable"

        note = (
            f"top={metrics.get('top')}, left={metrics.get('left')}, width={metrics.get('width')}, "
            f"height={metrics.get('height')}, display={metrics.get('display')}, "
            f"visibility={metrics.get('visibility')}, opacity={metrics.get('opacity')}"
        )
        return bool(metrics.get("onScreen")), note

    def _snapshot_frame(self, frame: Frame) -> FrameSnapshot | None:
        try:
            raw = frame.evaluate(FRAME_STATE_SCRIPT)
        except Error:
            return None
        except TimeoutError:
            return None
        page = frame.page
        is_visible, viewport_note = self._frame_visibility(page, frame)
        return FrameSnapshot(
            frame=frame,
            url=raw.get("url", ""),
            title=raw.get("title", ""),
            text_preview=raw.get("textPreview", ""),
            has_comment=bool(raw.get("hasComment")),
            has_exercise=bool(raw.get("hasExercise")),
            has_submit=bool(raw.get("hasSubmit")),
            has_password=bool(raw.get("hasPassword")),
            has_video=bool(raw.get("hasVideo")),
            has_captcha=bool(raw.get("hasCaptcha")),
            has_next_unit=bool(raw.get("hasNextUnit")),
            is_visible=is_visible,
            viewport_note=viewport_note,
            video=raw.get("video"),
        )

    def _inspect_page(self, page: Page) -> PageState:
        snapshots: list[FrameSnapshot] = []
        for frame in page.frames:
            snapshot = self._snapshot_frame(frame)
            if snapshot is not None:
                snapshots.append(snapshot)

        visible_snapshots = [snapshot for snapshot in snapshots if snapshot.is_visible]
        candidate_snapshots = visible_snapshots or snapshots

        captcha_snapshot = next((snapshot for snapshot in candidate_snapshots if snapshot.has_captcha), None)
        login_snapshot = next((snapshot for snapshot in candidate_snapshots if snapshot.has_password or LOGIN_TEXT in snapshot.text_preview), None)
        video_snapshot = next((snapshot for snapshot in candidate_snapshots if snapshot.has_comment or snapshot.has_video), None)
        exercise_snapshot = next((snapshot for snapshot in candidate_snapshots if snapshot.has_exercise or snapshot.has_submit), None)

        if captcha_snapshot:
            return PageState("captcha", "检测到安全验证或滑块验证码", captcha_snapshot, self._build_signature("captcha", captcha_snapshot))
        if login_snapshot:
            return PageState("login", "检测到登录表单或登录提示", login_snapshot, self._build_signature("login", login_snapshot))
        if video_snapshot:
            return PageState("video", "检测到“发表评论”或 video 元素", video_snapshot, self._build_signature("video", video_snapshot))
        if exercise_snapshot:
            return PageState("exercise", "检测到“习题”或“提交”", exercise_snapshot, self._build_signature("exercise", exercise_snapshot))
        return PageState("unknown", "暂未识别出视频页或习题页", None, "unknown")

    def _build_signature(self, kind: str, snapshot: FrameSnapshot) -> str:
        stable_text = "".join(character for character in snapshot.text_preview if not character.isdigit())
        stable_text = " ".join(stable_text.split())[:140]
        parts = [kind, snapshot.url or snapshot.title]
        if kind in {"exercise", "captcha", "unknown"}:
            parts.append(stable_text)
        return str(abs(hash("|".join(parts))))

    def _stage_from_kind(self, kind: str) -> str:
        mapping = {
            "video": "running",
            "exercise": "running",
            "login": "waiting_login",
            "captcha": "waiting_captcha",
            "unknown": "loading",
        }
        return mapping.get(kind, "running")

    def _interruptible_sleep(self, seconds: float) -> None:
        end_at = time.time() + max(0.0, seconds)
        while not self.stop_requested and time.time() < end_at:
            time.sleep(min(0.25, end_at - time.time()))

    def _publish_status(self, **changes: Any) -> None:
        self.status = self.status.copy_with(**changes)
        if self.on_status is not None:
            self.on_status(self.status)

    def _emit(
        self,
        level: str,
        category: str,
        code: str,
        message: str,
        details: str = "",
        suggestion: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        event = LogEvent(
            timestamp=datetime.now(),
            level=level,
            category=category,
            code=code,
            message=message,
            details=details,
            suggestion=suggestion,
            data=data or {},
        )
        if self.session_logger is not None:
            self.session_logger.append(event)
        if self.on_event is not None:
            self.on_event(event)

        infos = self.status.infos
        warnings = self.status.warnings
        errors = self.status.errors
        last_error_hint = self.status.last_error_hint
        if level == "ERROR":
            errors += 1
            last_error_hint = suggestion or message
        elif level == "WARNING":
            warnings += 1
        else:
            infos += 1
        self._publish_status(
            infos=infos,
            warnings=warnings,
            errors=errors,
            last_message=message,
            last_event_code=code,
            last_error_hint=last_error_hint,
        )

    def _diagnose_exception(self, exc: Exception) -> dict[str, str]:
        text = str(exc)
        traceback_text = traceback.format_exc()
        if isinstance(exc, TimeoutError):
            return {
                "category": "NAVIGATION",
                "code": "PLAYWRIGHT_TIMEOUT",
                "message": "Playwright 操作超时。",
                "details": traceback_text,
                "suggestion": "通常是网络较慢、页面结构变化或目标元素没有及时出现，可以适当提高超时设置。",
            }
        if isinstance(exc, FileNotFoundError) or "浏览器不存在" in text:
            return {
                "category": "SYSTEM",
                "code": "BROWSER_NOT_FOUND",
                "message": "浏览器路径无效，无法启动自动化。",
                "details": traceback_text,
                "suggestion": "请在界面里重新选择 Chrome 或 Edge 的可执行文件。",
            }
        if "Target page, context or browser has been closed" in text:
            return {
                "category": "SYSTEM",
                "code": "BROWSER_CLOSED",
                "message": "浏览器或页面被关闭，自动化中断。",
                "details": traceback_text,
                "suggestion": "重新启动任务即可；如果频繁发生，检查是否有系统策略关闭浏览器。",
            }
        if "net::ERR_" in text:
            return {
                "category": "NETWORK",
                "code": "NETWORK_ERROR",
                "message": "网络请求失败，页面可能未正常加载。",
                "details": traceback_text,
                "suggestion": "请检查当前网络、校园网认证或代理设置，然后重试。",
            }
        if "Execution context was destroyed" in text:
            return {
                "category": "PAGE",
                "code": "PAGE_RELOADED",
                "message": "页面在脚本执行时发生了刷新或跳转。",
                "details": traceback_text,
                "suggestion": "这是动态站点上常见现象，通常重新开始任务即可恢复。",
            }
        return {
            "category": "SYSTEM",
            "code": "UNHANDLED_EXCEPTION",
            "message": "发生了未预期的异常。",
            "details": traceback_text,
            "suggestion": "请把会话日志发出来，我可以继续帮你定位问题。",
        }
