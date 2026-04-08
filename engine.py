"""
YKT Browser - 雨课堂自动播放引擎
基于 Playwright 的浏览器自动化引擎
"""

import os
import queue
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


VIDEO_MARKERS = ("发表评论",)
EXERCISE_MARKERS = ("习题", "提交", "随堂练习")
NEXT_BUTTON_TEXT = "下一单元"
CLICKABLE_ANCESTOR_SELECTOR = ".btn-next, [class*='btn-next'], button, [role='button'], a"
CLICK_STRATEGY_OPTIONS = (
    ("combo", "预热复点", "同一轮内快速执行 定位器 -> JS -> 再次定位器"),
    ("locator", "定位器点击", "Playwright 定位器、祖先点击和 force 点击"),
    ("js", "JS 事件点击", "用 pointer/mouse/click 事件链触发按钮"),
    ("keyboard", "键盘触发", "聚焦按钮后发送 Enter 和 Space"),
    ("mouse", "鼠标坐标点击", "移动到按钮中心点后执行鼠标点击"),
    ("touch", "触摸事件点击", "模拟手机触摸点击按钮"),
    ("direct_nav", "直接导航", "解析下一单元链接后直接跳转"),
)
DEFAULT_CLICK_STRATEGIES = ("combo",)
DEFAULT_WAIT_FOR_CAPTCHA = False
LOGIN_URL_KEYWORDS = ("portal/home", "login", "oauth", "auth", "passport")
LOGIN_TEXT_MARKERS = ("登录", "微信登录", "手机号登录", "统一身份认证")
CAPTCHA_URL_KEYWORDS = ("captcha", "turing")
CAPTCHA_TEXT_MARKERS = ("安全验证", "拖动下方滑块", "拖动滑块", "完成拼图")
CAPTCHA_SELECTORS = (
    "iframe[src*='captcha']",
    "iframe[src*='turing']",
    "#tcaptcha_iframe",
    "#tcaptcha_drag_thumb",
    "[id*='tcaptcha']",
    "[class*='tcaptcha']",
)
BROWSER_EXECUTABLES = (
    ("Microsoft Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ("Google Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    ("Microsoft Edge", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ("Google Chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)
NEXT_BUTTON_LOCATORS = (
    ("右上角按钮", "div.fr span.btn-next"),
    ("右上角文字", "div.fr span.btn-next span.f14"),
    ("btn-next 类", "span.btn-next"),
    ("btn-next+文本", "span.btn-next:has-text('下一单元')"),
    ("pointer 类按钮", "span.pointer:has-text('下一单元')"),
    ("目录前文字", "xpath=//span[contains(@class,'catalogue')]/preceding-sibling::span//*[contains(normalize-space(.),'下一单元')]"),
    ("目录前兄弟节点", "xpath=//span[contains(@class,'catalogue')]/preceding-sibling::span[contains(@class,'btn-next')]"),
    ("右侧区域文本", "div.fr span:has-text('下一单元')"),
    ("文本定位", "text=下一单元"),
)

CLICK_STRATEGY_LABELS = {key: label for key, label, _ in CLICK_STRATEGY_OPTIONS}


def normalize_engine_options(options=None):
    options = options or {}
    requested = options.get("click_strategies", DEFAULT_CLICK_STRATEGIES)
    known_keys = {key for key, _, _ in CLICK_STRATEGY_OPTIONS}
    click_strategies = [key for key in requested if key in known_keys]

    return {
        "click_strategies": click_strategies,
        "wait_for_captcha": bool(options.get("wait_for_captcha", DEFAULT_WAIT_FOR_CAPTCHA)),
    }


STEALTH_INIT_SCRIPT = """
() => {
    const defineValue = (target, key, value) => {
        try {
            Object.defineProperty(target, key, {
                configurable: true,
                get: () => value,
            });
        } catch (error) {}
    };

    defineValue(navigator, "webdriver", undefined);
    defineValue(navigator, "platform", "Win32");
    defineValue(navigator, "language", "zh-CN");
    defineValue(navigator, "languages", ["zh-CN", "zh", "en-US", "en"]);
    defineValue(navigator, "hardwareConcurrency", 8);
    defineValue(navigator, "deviceMemory", 8);
    defineValue(navigator, "plugins", [
        {name: "Chrome PDF Plugin"},
        {name: "Chrome PDF Viewer"},
        {name: "Native Client"},
    ]);

    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {};
    }

    const originalQuery = navigator.permissions && navigator.permissions.query;
    if (originalQuery) {
        navigator.permissions.query = (parameters) => (
            parameters && parameters.name === "notifications"
                ? Promise.resolve({state: Notification.permission})
                : originalQuery(parameters)
        );
    }
}
"""

HAS_VIDEO_SCRIPT = """
() => {
    /* ykt_has_video */
    return document.getElementsByTagName("video").length > 0;
}
"""

INJECT_AUTOPLAY_SCRIPT = """
() => {
    /* ykt_inject_autoplay */
    if (window.__yktAutoplayTimer) {
        return true;
    }
    window.__yktAutoplayTimer = window.setInterval(() => {
        try {
            const currentVideo = document.getElementsByTagName("video")[0];
            if (!currentVideo) {
                return;
            }
            const playPromise = currentVideo.play();
            if (playPromise && typeof playPromise.catch === "function") {
                playPromise.catch(() => {});
            }
        } catch (error) {}
    }, 100);
    return true;
}
"""

VIDEO_STATE_SCRIPT = """
() => {
    /* ykt_video_state */
    const currentVideo = document.getElementsByTagName("video")[0];
    if (!currentVideo) {
        return {
            found: false,
            current: 0,
            duration: 0,
            ended: false,
            paused: false
        };
    }
    return {
        found: true,
        current: currentVideo.currentTime || 0,
        duration: currentVideo.duration || 0,
        ended: Boolean(currentVideo.ended),
        paused: Boolean(currentVideo.paused)
    };
}
"""

HAS_NEXT_BUTTON_SCRIPT = f"""
() => {{
    /* ykt_has_next_button */
    const targetText = "{NEXT_BUTTON_TEXT}";
    const clickableSelector = "{CLICKABLE_ANCESTOR_SELECTOR}";
    const normalize = (value) => (value || "").replace(/\\s+/g, "");
    const isVisible = (element) => {{
        if (!(element instanceof Element)) {{
            return false;
        }}
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== "none"
            && style.visibility !== "hidden"
            && style.pointerEvents !== "none"
            && rect.width > 0
            && rect.height > 0;
    }};
    const resolveCandidate = (node) => {{
        if (!(node instanceof Element)) {{
            return null;
        }}
        return node.closest(clickableSelector)
            || node.closest(".fr > span")
            || node.parentElement
            || node;
    }};

    const nodes = Array.from(
        document.querySelectorAll(
            ".fr .btn-next, .btn-next, [class*='btn-next'], .fr span, .catalogue, [class*='catalogue']"
        )
    );
    return nodes.some((node) => {{
        const candidate = resolveCandidate(node);
        const text = normalize(candidate.innerText || candidate.textContent || "");
        const className = String(candidate.className || "");
        return isVisible(candidate)
            && (text.includes(targetText) || className.includes("btn-next"));
    }});
}}
"""

CLICK_NEXT_BUTTON_SCRIPT = f"""
() => {{
    /* ykt_click_next_button */
    const targetText = "{NEXT_BUTTON_TEXT}";
    const clickableSelector = "{CLICKABLE_ANCESTOR_SELECTOR}";
    const normalize = (value) => (value || "").replace(/\\s+/g, "");
    const isVisible = (element) => {{
        if (!(element instanceof Element)) {{
            return false;
        }}
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== "none"
            && style.visibility !== "hidden"
            && style.pointerEvents !== "none"
            && rect.width > 0
            && rect.height > 0;
    }};
    const resolveCandidate = (node) => {{
        if (!(node instanceof Element)) {{
            return null;
        }}
        return node.closest(clickableSelector)
            || node.closest(".fr > span")
            || node.parentElement
            || node;
    }};

    const seen = new Set();
    const candidates = [];

    const pushCandidate = (candidate, source) => {{
        if (!(candidate instanceof Element) || seen.has(candidate)) {{
            return;
        }}
        seen.add(candidate);

        const text = normalize(candidate.innerText || candidate.textContent || "");
        const className = String(candidate.className || "");
        if (!text.includes(targetText) && !className.includes("btn-next")) {{
            return;
        }}

        const visible = isVisible(candidate);
        const rect = candidate.getBoundingClientRect();
        let score = 0;
        if (className.includes("btn-next")) {{
            score += 8;
        }}
        if (className.includes("pointer")) {{
            score += 3;
        }}
        if (text.includes(targetText)) {{
            score += 6;
        }}
        if (text === targetText) {{
            score += 3;
        }}
        if (source === "catalogue-prev") {{
            score += 5;
        }}
        if (visible) {{
            score += 4;
        }}
        if (rect.top >= 0 && rect.top <= 180) {{
            score += 2;
        }}
        if (rect.right >= window.innerWidth - 300) {{
            score += 2;
        }}

        candidates.push({{
            candidate,
            text,
            className,
            visible,
            tagName: candidate.tagName,
            score,
            source
        }});
    }};

    document.querySelectorAll(".btn-next, [class*='btn-next']").forEach((node) => {{
        pushCandidate(node, "class");
    }});

    document.querySelectorAll(
        ".fr span, .fr button, .fr a, .btn-next, [class*='btn-next'], .catalogue, [class*='catalogue']"
    ).forEach((node) => {{
        const text = normalize(node.innerText || node.textContent || "");
        if (!text.includes(targetText)) {{
            return;
        }}
        const candidate = resolveCandidate(node);
        pushCandidate(candidate, "text");
    }});

    document.querySelectorAll(".catalogue, [class*='catalogue']").forEach((node) => {{
        const previous = node.previousElementSibling;
        if (previous) {{
            pushCandidate(previous, "catalogue-prev");
        }}
    }});

    candidates.sort((left, right) => right.score - left.score);
    const best = candidates.find((item) => item.visible) || candidates[0];
    if (!best) {{
        return {{clicked: false}};
    }}

    const target = best.candidate;
    const rect = target.getBoundingClientRect();
    const clientX = rect.left + rect.width / 2;
    const clientY = rect.top + rect.height / 2;

    try {{
        target.scrollIntoView({{block: "center", inline: "nearest"}});
    }} catch (error) {{}}

    const mouseEventInit = {{
        bubbles: true,
        cancelable: true,
        view: window,
        button: 0,
        buttons: 1,
        clientX,
        clientY
    }};

    const pointerEventInit = {{
        ...mouseEventInit,
        pointerId: 1,
        pointerType: "mouse",
        isPrimary: true
    }};

    try {{
        const PointerCtor = window.PointerEvent || window.MouseEvent;
        target.dispatchEvent(new PointerCtor("pointerover", pointerEventInit));
        target.dispatchEvent(new MouseEvent("mouseover", mouseEventInit));
        target.dispatchEvent(new PointerCtor("pointerdown", pointerEventInit));
        target.dispatchEvent(new MouseEvent("mousedown", mouseEventInit));
        target.dispatchEvent(new PointerCtor("pointerup", pointerEventInit));
        target.dispatchEvent(new MouseEvent("mouseup", mouseEventInit));
    }} catch (error) {{}}

    try {{
        if (typeof target.click === "function") {{
            target.click();
        }}
    }} catch (error) {{}}

    try {{
        target.dispatchEvent(new MouseEvent("click", mouseEventInit));
    }} catch (error) {{}}

    return {{
        clicked: true,
        text: best.text,
        className: best.className,
        visible: best.visible,
        tagName: best.tagName,
        score: best.score,
        source: best.source,
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height
    }};
}}
"""

NEXT_BUTTON_BOX_SCRIPT = f"""
() => {{
    /* ykt_next_button_box */
    const targetText = "{NEXT_BUTTON_TEXT}";
    const clickableSelector = "{CLICKABLE_ANCESTOR_SELECTOR}";
    const normalize = (value) => (value || "").replace(/\\s+/g, "");
    const isVisible = (element) => {{
        if (!(element instanceof Element)) {{
            return false;
        }}
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== "none"
            && style.visibility !== "hidden"
            && style.pointerEvents !== "none"
            && rect.width > 0
            && rect.height > 0;
    }};
    const resolveCandidate = (node) => {{
        if (!(node instanceof Element)) {{
            return null;
        }}
        return node.closest(clickableSelector)
            || node.closest(".fr > span")
            || node.parentElement
            || node;
    }};

    const seen = new Set();
    const candidates = [];

    const pushCandidate = (candidate, source) => {{
        if (!(candidate instanceof Element) || seen.has(candidate)) {{
            return;
        }}
        seen.add(candidate);

        const text = normalize(candidate.innerText || candidate.textContent || "");
        const className = String(candidate.className || "");
        if (!text.includes(targetText) && !className.includes("btn-next")) {{
            return;
        }}

        const rect = candidate.getBoundingClientRect();
        const visible = isVisible(candidate);
        let score = 0;
        if (className.includes("btn-next")) {{
            score += 8;
        }}
        if (className.includes("pointer")) {{
            score += 3;
        }}
        if (text.includes(targetText)) {{
            score += 6;
        }}
        if (text === targetText) {{
            score += 3;
        }}
        if (source === "catalogue-prev") {{
            score += 5;
        }}
        if (visible) {{
            score += 4;
        }}
        if (rect.top >= 0 && rect.top <= 180) {{
            score += 2;
        }}
        if (rect.right >= window.innerWidth - 300) {{
            score += 2;
        }}

        candidates.push({{
            text,
            className,
            visible,
            tagName: candidate.tagName,
            score,
            source,
            left: rect.left,
            top: rect.top,
            width: rect.width,
            height: rect.height
        }});
    }};

    document.querySelectorAll(".btn-next, [class*='btn-next']").forEach((node) => {{
        pushCandidate(node, "class");
    }});

    document.querySelectorAll(
        ".fr span, .fr button, .fr a, .btn-next, [class*='btn-next'], .catalogue, [class*='catalogue']"
    ).forEach((node) => {{
        const text = normalize(node.innerText || node.textContent || "");
        if (!text.includes(targetText)) {{
            return;
        }}
        const candidate = resolveCandidate(node);
        pushCandidate(candidate, "text");
    }});

    document.querySelectorAll(".catalogue, [class*='catalogue']").forEach((node) => {{
        const previous = node.previousElementSibling;
        if (previous) {{
            pushCandidate(previous, "catalogue-prev");
        }}
    }});

    candidates.sort((left, right) => right.score - left.score);
    return candidates.find((item) => item.visible) || candidates[0] || null;
}}
"""

NEXT_BUTTON_DIAGNOSTIC_SCRIPT = f"""
() => {{
    /* ykt_next_button_diagnostics */
    const targetText = "{NEXT_BUTTON_TEXT}";
    const clickableSelector = "{CLICKABLE_ANCESTOR_SELECTOR}";
    const normalize = (value) => (value || "").replace(/\\s+/g, "");
    const isVisible = (element) => {{
        if (!(element instanceof Element)) {{
            return false;
        }}
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== "none"
            && style.visibility !== "hidden"
            && style.pointerEvents !== "none"
            && rect.width > 0
            && rect.height > 0;
    }};
    const resolveCandidate = (node) => {{
        if (!(node instanceof Element)) {{
            return null;
        }}
        return node.closest(clickableSelector)
            || node.closest(".fr > span")
            || node.parentElement
            || node;
    }};

    const rawNodes = Array.from(
        document.querySelectorAll(
            ".fr .btn-next, .btn-next, [class*='btn-next'], .fr span, .catalogue, [class*='catalogue']"
        )
    );
    const seen = new Set();
    const matches = [];

    for (const node of rawNodes) {{
        const candidate = resolveCandidate(node);
        if (!candidate || seen.has(candidate)) {{
            continue;
        }}
        seen.add(candidate);

        const text = normalize(candidate.innerText || candidate.textContent || "");
        const className = String(candidate.className || "");
        if (
            !text.includes(targetText)
            && !text.includes("下一")
            && !className.includes("btn-next")
            && !className.includes("next")
        ) {{
            continue;
        }}

        matches.push({{
            tagName: candidate.tagName,
            text: text.slice(0, 40),
            className: className.slice(0, 80),
            visible: isVisible(candidate)
        }});
    }}

    return matches.slice(0, 6);
}}
"""

PAGE_SNAPSHOT_SCRIPT = """
() => {
    /* ykt_page_snapshot */
    const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim();
    const pickText = (selectors) => {
        for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (!element) {
                continue;
            }
            const text = normalize(element.innerText || element.textContent || "");
            if (text) {
                return text.slice(0, 160);
            }
        }
        return "";
    };

    const activeText = Array.from(
        document.querySelectorAll(
            ".active, .is-active, .current, [class*='active'], [class*='current']"
        )
    )
        .map((node) => normalize(node.innerText || node.textContent || ""))
        .find(Boolean) || "";

    const video = document.querySelector("video");
    return {
        url: window.location.href,
        title: normalize(document.title || ""),
        heading: pickText([
            ".video__name",
            ".title",
            ".activity__title",
            ".header .text",
            "h1",
            "h2",
            "h3"
        ]),
        activeText,
        videoSrc: normalize(
            (video && (video.currentSrc || video.src || video.getAttribute("src"))) || ""
        ),
        nextText: pickText([
            "div.fr span.btn-next",
            "span.btn-next",
            "div.fr"
        ])
    };
}
"""

NEXT_URL_DISCOVERY_SCRIPT = """
() => {
    /* ykt_discover_next_urls */
    const currentHref = window.location.href;
    const currentUrl = new URL(currentHref);
    const currentPath = currentUrl.pathname;
    const currentMatch = currentPath.match(/^(.*)\\/(video|courseware|homework|discussion|exam|examination)\\/([^/?#]+)\\/?$/);
    if (!currentMatch) {
        return [];
    }

    const basePath = currentMatch[1];
    const currentLeafId = currentMatch[3];
    const currentOrigin = currentUrl.origin;
    const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim();
    const seen = new Set();
    const candidates = [];

    const pushCandidate = (rawUrl, source, text = "") => {
        if (!rawUrl) {
            return;
        }

        let absoluteUrl = "";
        try {
            absoluteUrl = new URL(rawUrl, currentHref).href;
        } catch (error) {
            return;
        }

        if (seen.has(absoluteUrl) || absoluteUrl === currentHref) {
            return;
        }
        seen.add(absoluteUrl);

        let parsed = null;
        try {
            parsed = new URL(absoluteUrl);
        } catch (error) {
            return;
        }

        if (parsed.origin !== currentOrigin) {
            return;
        }

        const match = parsed.pathname.match(/^(.*)\\/(video|courseware|homework|discussion|exam|examination)\\/([^/?#]+)\\/?$/);
        if (!match || match[1] !== basePath || match[3] === currentLeafId) {
            return;
        }

        let score = 0;
        const normalizedText = normalize(text);
        if (normalizedText.includes("下一")) {
            score += 20;
        }
        if (source.includes("next")) {
            score += 10;
        }
        if (match[2] === "video") {
            score += 4;
        }

        candidates.push({
            url: absoluteUrl,
            source,
            text: normalizedText.slice(0, 120),
            leafId: match[3],
            score,
        });
    };

    document.querySelectorAll("[href], [data-href], [data-url], [data-to], [to]").forEach((node) => {
        const text = normalize(node.innerText || node.textContent || "");
        for (const attr of ["href", "data-href", "data-url", "data-to", "to"]) {
            const value = node.getAttribute(attr);
            if (value) {
                pushCandidate(value, `attr:${attr}`, text);
            }
        }
    });

    document.querySelectorAll(".btn-next, [class*='btn-next'], .catalogue, [class*='catalogue']").forEach((node) => {
        const text = normalize(node.innerText || node.textContent || "");
        for (const key of ["href", "data-href", "data-url", "data-route", "data-to", "to"]) {
            const value = node.getAttribute(key);
            if (value) {
                pushCandidate(value, `next-node:${key}`, text);
            }
        }
    });

    const html = document.documentElement ? document.documentElement.innerHTML : "";
    const routeMatches = html.match(/\\/pro\\/lms\\/[^"'\\s<>()]+\\/(?:video|courseware|homework|discussion|exam|examination)\\/\\d+/g) || [];
    routeMatches.forEach((route) => pushCandidate(route, "html-regex", ""));

    candidates.sort((left, right) => right.score - left.score || left.url.localeCompare(right.url));
    return candidates.slice(0, 20);
}
"""


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
    WAITING_VERIFICATION = "等待验证"


class YuketangEngine:
    """雨课堂自动播放引擎"""

    def __init__(self, msg_queue: queue.Queue, options=None):
        self.msg_queue = msg_queue
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._thread = None
        self.browser = None
        self.context = None
        self.page = None
        self.target_url = ""
        self.stats = {"videos": 0, "exercises": 0, "errors": 0, "units": 0}
        self.start_time = None
        self.status = EngineStatus.IDLE
        self.options = normalize_engine_options(options)
        self._last_page_signature = ""

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

    def _is_strategy_enabled(self, key: str) -> bool:
        return key in self.options.get("click_strategies", [])

    def _enabled_strategy_labels(self):
        return [
            CLICK_STRATEGY_LABELS[key]
            for key in self.options.get("click_strategies", [])
            if key in CLICK_STRATEGY_LABELS
        ]

    def _resume_running_status(self):
        if self.status not in (EngineStatus.STOPPING, EngineStatus.STOPPED, EngineStatus.PAUSED):
            self._set_status(EngineStatus.RUNNING)

    # ── Control API ──────────────────────────────────────────────

    def start(self, url: str):
        if self._thread and self._thread.is_alive():
            self._log("WARNING", "引擎已在运行中")
            return
        self._stop_event.clear()
        self._pause_event.set()
        self.stats = {"videos": 0, "exercises": 0, "errors": 0, "units": 0}
        self.start_time = time.time()
        self.target_url = url
        self._thread = threading.Thread(target=self._run, args=(url,), daemon=True)
        self._thread.start()

    def stop(self):
        self._log("INFO", "正在停止...")
        self._stop_event.set()
        self._pause_event.set()
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

    @staticmethod
    def _is_page_closed(page) -> bool:
        if page is None:
            return True

        is_closed = getattr(page, "is_closed", None)
        if callable(is_closed):
            try:
                return bool(is_closed())
            except Exception:
                return False

        return False

    def _safe_page_url(self, page=None) -> str:
        page = page or self.page
        if page is None:
            return ""

        try:
            return getattr(page, "url", "") or ""
        except Exception:
            return ""

    def _iter_pages(self):
        pages = []
        candidates = []
        if self.page is not None:
            candidates.append(self.page)

        context_pages = getattr(self.context, "pages", None) if self.context else None
        for page in context_pages or []:
            candidates.append(page)

        for page in candidates:
            if self._is_page_closed(page):
                continue
            if all(page is not existing for existing in pages):
                pages.append(page)

        return pages

    def _iter_roots(self, page=None):
        page = page or self.page
        if not page:
            return []

        roots = []

        try:
            main_frame = getattr(page, "main_frame", None)
            if main_frame is not None:
                roots.append(main_frame)
        except Exception:
            pass

        try:
            for frame in list(getattr(page, "frames", []) or []):
                if all(frame is not existing for existing in roots):
                    roots.append(frame)
        except Exception:
            pass

        if not roots:
            roots.append(page)

        return roots

    def _describe_page(self, page) -> str:
        page_url = self._safe_page_url(page)
        if not page_url:
            return "未知页签"

        if len(page_url) > 80:
            page_url = page_url[:77] + "..."
        return page_url

    def _page_matches_target(self, page) -> bool:
        if not self.target_url:
            return False

        try:
            current = urlparse(self._safe_page_url(page))
            target = urlparse(self.target_url)
        except Exception:
            return False

        if not current.netloc or current.netloc != target.netloc:
            return False

        return "/pro/lms/" in current.path

    def _page_looks_like_login(self, page) -> bool:
        page_url = self._safe_page_url(page).lower()
        if any(keyword in page_url for keyword in LOGIN_URL_KEYWORDS):
            return True

        for root in self._iter_roots(page):
            for text in LOGIN_TEXT_MARKERS:
                try:
                    if root.query_selector(f"text={text}"):
                        return True
                except Exception:
                    continue

        return False

    def _page_has_captcha(self, page) -> bool:
        page_url = self._safe_page_url(page).lower()
        if any(keyword in page_url for keyword in CAPTCHA_URL_KEYWORDS):
            return True

        for root in self._iter_roots(page):
            try:
                root_url = (getattr(root, "url", "") or "").lower()
            except Exception:
                root_url = ""

            if any(keyword in root_url for keyword in CAPTCHA_URL_KEYWORDS):
                return True

            for selector in CAPTCHA_SELECTORS:
                try:
                    if root.query_selector(selector):
                        return True
                except Exception:
                    continue

            for text in CAPTCHA_TEXT_MARKERS:
                try:
                    if root.query_selector(f"text={text}"):
                        return True
                except Exception:
                    continue

        return False

    def _page_has_known_content(self, page) -> bool:
        return self._has_known_content(page)

    def _activate_page(self, page, log_reason: Optional[str] = None):
        if page is None or page is self.page:
            return self.page

        self.page = page
        try:
            self.page.set_default_timeout(15000)
        except Exception:
            pass

        page_signature = self._describe_page(page)
        if log_reason and page_signature != self._last_page_signature:
            self._log("INFO", f"{log_reason}: {page_signature}")
        self._last_page_signature = page_signature
        return self.page

    def _sync_active_page(self, prefer_content: bool = False, log_reason: Optional[str] = None):
        pages = self._iter_pages()
        if not pages:
            return self.page

        if len(pages) == 1:
            self._activate_page(pages[0])
            return self.page

        scored_pages = []
        for index, page in enumerate(pages):
            has_content = self._page_has_known_content(page)
            score = 0
            if has_content:
                score += 200
            if self._page_matches_target(page):
                score += 40
            if page is self.page:
                score += 8
            if self._page_looks_like_login(page):
                score -= 60
            if self._page_has_captcha(page):
                score -= 25
            score -= index
            scored_pages.append((score, has_content, page))

        if prefer_content:
            content_pages = [item for item in scored_pages if item[1]]
            if content_pages:
                best_page = max(content_pages, key=lambda item: item[0])[2]
                return self._activate_page(best_page, log_reason)

        best_page = max(scored_pages, key=lambda item: item[0])[2]
        return self._activate_page(best_page, log_reason)

    def _any_page_has_captcha(self) -> bool:
        return any(self._page_has_captcha(page) for page in self._iter_pages())

    @staticmethod
    def _find_preferred_browser():
        for browser_name, executable_path in BROWSER_EXECUTABLES:
            if os.path.exists(executable_path):
                return browser_name, executable_path
        return "Playwright Chromium", None

    def _launch_browser_context(self, playwright_instance, user_data_dir):
        launch_options = {
            "user_data_dir": user_data_dir,
            "headless": False,
            "viewport": {"width": 1366, "height": 768},
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "ignore_default_args": ["--enable-automation"],
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-infobars",
                "--lang=zh-CN",
            ],
        }

        preferred_name, executable_path = self._find_preferred_browser()
        launch_errors = []

        if executable_path:
            try:
                context = playwright_instance.chromium.launch_persistent_context(
                    executable_path=executable_path,
                    **launch_options,
                )
                return context, preferred_name, None
            except Exception as exc:
                launch_errors.append(f"{preferred_name}: {exc}")

        try:
            context = playwright_instance.chromium.launch_persistent_context(**launch_options)
            return context, "Playwright Chromium", launch_errors[0] if launch_errors else None
        except Exception as exc:
            combined_error = " | ".join(launch_errors + [f"Playwright Chromium: {exc}"])
            raise RuntimeError(combined_error) from exc

    @staticmethod
    def _apply_stealth(context):
        context.add_init_script(STEALTH_INIT_SCRIPT)

    def _describe_root(self, root) -> str:
        try:
            page_url = getattr(self.page, "url", "")
        except Exception:
            page_url = ""

        try:
            root_url = getattr(root, "url", "")
        except Exception:
            root_url = ""

        if root_url == page_url or not root_url:
            return "主文档"
        if len(root_url) > 60:
            root_url = root_url[:57] + "..."
        return f"frame<{root_url}>"

    def _find_text_root(self, texts, page=None) -> Optional[object]:
        for root in self._iter_roots(page):
            for text in texts:
                try:
                    if root.query_selector(f"text={text}"):
                        return root
                except Exception:
                    continue
        return None

    def _root_has_next_button(self, root) -> bool:
        for selector in (".btn-next", "span.btn-next", "[class*='btn-next']"):
            try:
                if root.query_selector(selector):
                    return True
            except Exception:
                continue

        try:
            return bool(root.evaluate(HAS_NEXT_BUTTON_SCRIPT))
        except Exception:
            return False

    def _find_video_root(self, page=None):
        fallback_root = None
        for root in self._iter_roots(page):
            try:
                if root.evaluate(HAS_VIDEO_SCRIPT):
                    return root
            except Exception:
                pass

            if fallback_root is None:
                for text in VIDEO_MARKERS:
                    try:
                        if root.query_selector(f"text={text}"):
                            fallback_root = root
                            break
                    except Exception:
                        continue

        return fallback_root

    def _find_exercise_root(self, page=None):
        return self._find_text_root(EXERCISE_MARKERS, page)

    def _click_next_via_locator(self, root):
        locator_factory = getattr(root, "locator", None)
        if not callable(locator_factory):
            return None

        candidates = []
        for strategy_name, selector in NEXT_BUTTON_LOCATORS:
            try:
                locator = root.locator(selector)
                count = locator.count()
            except Exception:
                continue

            if count <= 0:
                continue

            for index in range(count - 1, -1, -1):
                target = locator.nth(index)
                try:
                    visible = target.is_visible()
                except Exception:
                    visible = False

                score = 0
                if visible:
                    score += 100
                if "btn-next" in selector:
                    score += 20
                if "目录前" in strategy_name:
                    score += 8
                if "文字" in strategy_name:
                    score += 5

                candidates.append(
                    {
                        "target": target,
                        "selector": selector,
                        "strategy_name": strategy_name,
                        "index": index,
                        "visible": visible,
                        "score": score,
                    }
                )

        candidates.sort(key=lambda item: item["score"], reverse=True)

        for candidate in candidates:
            target = candidate["target"]

            try:
                target.scroll_into_view_if_needed(timeout=1200)
            except Exception:
                pass

            if candidate["visible"]:
                try:
                    target.click(timeout=1500, force=False, no_wait_after=True)
                    return {
                        "root": self._describe_root(root),
                        "strategy": candidate["strategy_name"],
                        "detail": {"selector": candidate["selector"], "index": candidate["index"]},
                    }
                except Exception:
                    pass

            try:
                target.evaluate(
                    f"""element => {{
                        const clickable = element.closest("{CLICKABLE_ANCESTOR_SELECTOR}")
                            || element.closest(".fr > span")
                            || element.parentElement
                            || element;
                        clickable.click();
                    }}"""
                )
                return {
                    "root": self._describe_root(root),
                    "strategy": f"{candidate['strategy_name']} / 祖先点击",
                    "detail": {"selector": candidate["selector"], "index": candidate["index"]},
                }
            except Exception:
                pass

            try:
                target.click(timeout=1500, force=True, no_wait_after=True)
                return {
                    "root": self._describe_root(root),
                    "strategy": f"{candidate['strategy_name']} / force",
                    "detail": {"selector": candidate["selector"], "index": candidate["index"]},
                }
            except Exception:
                continue

        return None

    def _click_next_in_root(self, root):
        try:
            result = root.evaluate(CLICK_NEXT_BUTTON_SCRIPT)
        except Exception:
            return None

        if not result or not result.get("clicked"):
            return None

        class_name = result.get("className", "")
        strategy = "btn-next" if "btn-next" in class_name else "文本匹配"
        return {
            "root": self._describe_root(root),
            "strategy": f"JS事件 / {strategy}",
            "detail": result,
        }

    def _get_next_button_box(self, root):
        try:
            return root.evaluate(NEXT_BUTTON_BOX_SCRIPT)
        except Exception:
            return None

    def _get_root_mouse_offset(self, root):
        try:
            if root is self.page or root is getattr(self.page, "main_frame", None):
                return 0.0, 0.0
        except Exception:
            pass

        try:
            frame_element = root.frame_element()
            frame_box = frame_element.bounding_box()
        except Exception:
            frame_box = None

        if not frame_box:
            return 0.0, 0.0

        return float(frame_box.get("x", 0.0)), float(frame_box.get("y", 0.0))

    def _click_next_via_mouse(self, root):
        button_box = self._get_next_button_box(root)
        if not button_box:
            return None

        mouse = getattr(self.page, "mouse", None)
        if mouse is None:
            return None

        offset_x, offset_y = self._get_root_mouse_offset(root)
        x = offset_x + float(button_box.get("left", 0.0)) + float(button_box.get("width", 0.0)) / 2
        y = offset_y + float(button_box.get("top", 0.0)) + float(button_box.get("height", 0.0)) / 2

        try:
            self.page.mouse.move(x, y)
            self.page.mouse.click(x, y, delay=80)
        except Exception:
            return None

        return {
            "root": self._describe_root(root),
            "strategy": "鼠标坐标点击",
            "detail": {"x": round(x, 1), "y": round(y, 1), **button_box},
        }

    def _click_next_via_touch(self, root):
        touchscreen = getattr(self.page, "touchscreen", None)
        button_box = self._get_next_button_box(root)

        if touchscreen is not None and button_box:
            offset_x, offset_y = self._get_root_mouse_offset(root)
            x = offset_x + float(button_box.get("left", 0.0)) + float(button_box.get("width", 0.0)) / 2
            y = offset_y + float(button_box.get("top", 0.0)) + float(button_box.get("height", 0.0)) / 2

            try:
                self.page.touchscreen.tap(x, y)
                return {
                    "root": self._describe_root(root),
                    "strategy": "触摸事件点击",
                    "detail": {"x": round(x, 1), "y": round(y, 1), **button_box},
                }
            except Exception:
                pass

        locator_factory = getattr(root, "locator", None)
        if not callable(locator_factory):
            return None

        for strategy_name, selector in NEXT_BUTTON_LOCATORS:
            try:
                locator = root.locator(selector)
                count = locator.count()
            except Exception:
                continue

            if count <= 0:
                continue

            for index in range(count - 1, -1, -1):
                target = locator.nth(index)
                try:
                    target.scroll_into_view_if_needed(timeout=1200)
                    detail = target.evaluate(
                        f"""element => {{
                            const clickable = element.closest("{CLICKABLE_ANCESTOR_SELECTOR}")
                                || element.closest(".fr > span")
                                || element.parentElement
                                || element;
                            const rect = clickable.getBoundingClientRect();
                            const clientX = rect.left + rect.width / 2;
                            const clientY = rect.top + rect.height / 2;
                            const pointerInit = {{
                                bubbles: true,
                                cancelable: true,
                                pointerId: 1,
                                pointerType: "touch",
                                isPrimary: true,
                                clientX,
                                clientY
                            }};
                            try {{
                                if (window.PointerEvent) {{
                                    clickable.dispatchEvent(new PointerEvent("pointerdown", pointerInit));
                                    clickable.dispatchEvent(new PointerEvent("pointerup", pointerInit));
                                }}
                                clickable.dispatchEvent(new MouseEvent("click", {{
                                    bubbles: true,
                                    cancelable: true,
                                    clientX,
                                    clientY
                                }}));
                                if (typeof clickable.click === "function") {{
                                    clickable.click();
                                }}
                            }} catch (error) {{}}

                            return {{
                                left: rect.left,
                                top: rect.top,
                                width: rect.width,
                                height: rect.height
                            }};
                        }}"""
                    )
                    return {
                        "root": self._describe_root(root),
                        "strategy": f"{strategy_name} / 触摸事件",
                        "detail": {"selector": selector, "index": index, **(detail or {})},
                    }
                except Exception:
                    continue

        return None

    def _discover_next_urls(self):
        discovered = []
        seen = set()

        for root in self._iter_roots():
            try:
                items = root.evaluate(NEXT_URL_DISCOVERY_SCRIPT) or []
            except Exception:
                continue

            for item in items:
                url = item.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                discovered.append(item)

        discovered.sort(key=lambda item: item.get("score", 0), reverse=True)
        return discovered

    def _navigate_to_next_url(self):
        candidates = self._discover_next_urls()
        if not candidates:
            return None

        target = candidates[0]
        try:
            self.page.goto(target["url"], wait_until="domcontentloaded", timeout=30000)
        except Exception:
            return None

        return {
            "root": "主文档",
            "strategy": f"直接导航 / {target.get('source', 'unknown')}",
            "detail": target,
        }

    def _click_next_via_keyboard(self, root):
        locator_factory = getattr(root, "locator", None)
        keyboard = getattr(self.page, "keyboard", None)
        if not callable(locator_factory) or keyboard is None:
            return None

        for strategy_name, selector in NEXT_BUTTON_LOCATORS:
            try:
                locator = root.locator(selector)
                count = locator.count()
            except Exception:
                continue

            if count <= 0:
                continue

            for index in range(count - 1, -1, -1):
                target = locator.nth(index)
                try:
                    target.scroll_into_view_if_needed(timeout=1200)
                    target.evaluate(
                        f"""element => {{
                            const clickable = element.closest("{CLICKABLE_ANCESTOR_SELECTOR}")
                                || element.closest(".fr > span")
                                || element.parentElement
                                || element;
                            clickable.setAttribute("tabindex", "-1");
                            clickable.focus();
                        }}"""
                    )
                    self.page.keyboard.press("Enter")
                    self.page.keyboard.press("Space")
                    return {
                        "root": self._describe_root(root),
                        "strategy": f"{strategy_name} / 键盘触发",
                        "detail": {"selector": selector, "index": index},
                    }
                except Exception:
                    continue

        return None

    def _click_next_via_combo(self, previous_snapshot):
        latest_snapshot = previous_snapshot
        attempted_steps = []
        last_clicked = None

        combo_steps = (
            (self._click_next_via_locator, 0.8),
            (self._click_next_in_root, 0.8),
            (self._click_next_via_locator, 1.2),
        )

        for root in self._iter_roots():
            for click_method, timeout_seconds in combo_steps:
                clicked = click_method(root)
                if not clicked:
                    continue

                last_clicked = clicked
                attempted_steps.append(clicked["strategy"])
                self._simulate_next_unit_change_for_tests()
                changed, latest_snapshot = self._wait_for_next_unit_change(
                    previous_snapshot,
                    timeout_seconds=timeout_seconds,
                )
                if changed:
                    return (
                        {
                            "root": clicked["root"],
                            "strategy": "预热复点 / " + " -> ".join(attempted_steps),
                            "detail": {
                                "steps": attempted_steps[:],
                                "last_detail": clicked.get("detail", {}),
                            },
                        },
                        latest_snapshot,
                    )

                if not self._sleep(0.3):
                    return None, latest_snapshot

        if not attempted_steps:
            return None, latest_snapshot

        return (
            {
                "root": last_clicked["root"] if last_clicked else "主文档",
                "strategy": "预热复点 / " + " -> ".join(attempted_steps),
                "detail": {
                    "steps": attempted_steps[:],
                    "last_detail": last_clicked.get("detail", {}) if last_clicked else {},
                },
            },
            latest_snapshot,
        )

    def _attempt_click_method_with_follow_up(self, click_method, root, previous_snapshot):
        clicked = click_method(root)
        if not clicked:
            return None, previous_snapshot, False

        self._simulate_next_unit_change_for_tests()
        changed, latest_snapshot = self._wait_for_next_unit_change(previous_snapshot)
        if changed:
            return clicked, latest_snapshot, True

        if click_method not in (self._click_next_via_locator, self._click_next_in_root):
            return clicked, latest_snapshot, False

        if not self._sleep(0.4):
            return clicked, latest_snapshot, False

        follow_up_clicked = click_method(root)
        if not follow_up_clicked:
            return clicked, latest_snapshot, False

        self._simulate_next_unit_change_for_tests()
        changed, latest_snapshot = self._wait_for_next_unit_change(
            previous_snapshot,
            timeout_seconds=1.8,
        )
        if changed:
            follow_up_clicked = {
                **follow_up_clicked,
                "strategy": f"{follow_up_clicked['strategy']} / 复点",
            }
            return follow_up_clicked, latest_snapshot, True

        return follow_up_clicked, latest_snapshot, False

    def _simulate_next_unit_change_for_tests(self):
        simulate = getattr(self.page, "simulate_next_unit_change", None)
        if callable(simulate):
            try:
                simulate()
            except Exception:
                pass

    def _get_page_snapshot(self, page=None):
        page = page or self.page
        snapshot = {
            "url": self._safe_page_url(page),
            "title": "",
            "heading": "",
            "activeText": "",
            "videoSrc": "",
            "nextText": "",
            "captchaFrame": "",
        }

        roots = self._iter_roots(page)
        for index, root in enumerate(roots):
            try:
                root_snapshot = root.evaluate(PAGE_SNAPSHOT_SCRIPT) or {}
            except Exception:
                continue

            for key in ("title", "heading", "activeText", "videoSrc", "nextText"):
                if not snapshot[key] and root_snapshot.get(key):
                    snapshot[key] = root_snapshot[key]

            root_url = root_snapshot.get("url") or getattr(root, "url", "")
            if index == 0 and root_url:
                snapshot["url"] = root_url
            elif "captcha" in root_url or "turing" in root_url:
                snapshot["captchaFrame"] = root_url

        return snapshot

    @staticmethod
    def _snapshot_changed(previous_snapshot, current_snapshot) -> bool:
        if not previous_snapshot:
            return True

        previous_url = previous_snapshot.get("url", "")
        current_url = current_snapshot.get("url", "")
        if previous_url and current_url and previous_url != current_url:
            return True

        for key in ("heading", "activeText", "videoSrc", "title"):
            previous_value = (previous_snapshot.get(key) or "").strip()
            current_value = (current_snapshot.get(key) or "").strip()
            if previous_value and current_value and previous_value != current_value:
                return True

        return False

    @staticmethod
    def _snapshot_has_captcha(snapshot) -> bool:
        if not snapshot:
            return False

        for key in ("url", "captchaFrame"):
            value = (snapshot.get(key) or "").lower()
            if "captcha" in value or "turing" in value:
                return True

        return False

    @staticmethod
    def _format_snapshot(snapshot) -> str:
        if not snapshot:
            return "-"
        parts = []
        for key in ("url", "heading", "activeText", "videoSrc", "captchaFrame"):
            value = (snapshot.get(key) or "").strip()
            if value:
                if len(value) > 80:
                    value = value[:77] + "..."
                parts.append(f"{key}={value}")
        return " | ".join(parts) or "-"

    def _wait_for_captcha_clear(self, timeout_seconds: float = 45.0):
        self._sync_active_page(prefer_content=True)
        latest_snapshot = self._get_page_snapshot()
        if not self._any_page_has_captcha():
            return True, latest_snapshot

        self._set_status(EngineStatus.WAITING_VERIFICATION)
        self._log("WARNING", "检测到验证码/风控页面，请先在浏览器里手动完成验证")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._stop_event.is_set():
                return False, latest_snapshot

            self._sync_active_page(prefer_content=True)
            latest_snapshot = self._get_page_snapshot()
            if self._has_known_content():
                self._resume_running_status()
                self._log("SUCCESS", "已重新回到课程页，继续执行后续任务")
                return True, latest_snapshot

            if not self._any_page_has_captcha():
                self._resume_running_status()
                self._log("SUCCESS", "验证码层已消失，继续尝试切换下一单元")
                return True, latest_snapshot

            time.sleep(1)

        return False, latest_snapshot

    def _wait_for_next_unit_change(self, previous_snapshot, timeout_seconds: float = 8.0):
        if not previous_snapshot:
            return True, self._get_page_snapshot()

        deadline = time.time() + timeout_seconds
        latest_snapshot = self._get_page_snapshot()
        while time.time() < deadline:
            if self._stop_event.is_set():
                return False, latest_snapshot

            self._sync_active_page(prefer_content=True)
            latest_snapshot = self._get_page_snapshot()
            if self._snapshot_changed(previous_snapshot, latest_snapshot):
                return True, latest_snapshot

            time.sleep(0.2)

        return False, latest_snapshot

    def _finalize_next_click(self, clicked):
        self._log(
            "SUCCESS",
            f"→ 已点击「{NEXT_BUTTON_TEXT}」({clicked['root']} / {clicked['strategy']})",
        )
        self.stats["units"] += 1
        self._update_stats()

        if not self._sleep(1):
            return

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except PlaywrightTimeout:
            self._log("WARNING", "页面加载超时，继续执行...")

        self._sleep(2)

    def _collect_next_button_diagnostics(self) -> str:
        summaries = []
        for root in self._iter_roots():
            try:
                items = root.evaluate(NEXT_BUTTON_DIAGNOSTIC_SCRIPT) or []
            except Exception:
                continue

            if not items:
                continue

            fragments = []
            for item in items[:3]:
                visibility = "visible" if item.get("visible") else "hidden"
                text = item.get("text") or "-"
                class_name = item.get("className") or "-"
                fragments.append(
                    f"{item.get('tagName', '?')}[{visibility}] text={text} class={class_name}"
                )

            summaries.append(f"{self._describe_root(root)}: " + "; ".join(fragments))

        return " | ".join(summaries[:3])

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
                    context, browser_name, fallback_error = self._launch_browser_context(
                        p,
                        user_data_dir,
                    )
                    self._apply_stealth(context)
                except Exception as launch_err:
                    err_msg = str(launch_err)
                    if (
                        "Executable doesn't exist" in err_msg
                        or "browserType.launch" in err_msg
                    ):
                        self._log("ERROR", "Chromium 浏览器未安装！")
                        self._log(
                            "ERROR",
                            "请先运行 setup.bat，或在命令行执行: python -m playwright install chromium",
                        )
                    else:
                        self._log("ERROR", f"浏览器启动失败: {err_msg}")
                    return

                self.context = context
                self.page = context.pages[0] if context.pages else context.new_page()
                self.page.set_default_timeout(15000)
                self._log("INFO", f"浏览器内核: {browser_name}")
                if fallback_error:
                    self._log("WARNING", f"真实浏览器启动失败，已回退到 Chromium: {fallback_error}")

                enabled_labels = "、".join(self._enabled_strategy_labels()) or "无"
                captcha_mode = "开启" if self.options.get("wait_for_captcha", DEFAULT_WAIT_FOR_CAPTCHA) else "关闭"
                self._log("INFO", f"已启用切换方案: {enabled_labels}")
                self._log("INFO", f"验证码等待人工处理: {captcha_mode}")

                self._log("INFO", f"正在导航到: {url}")
                self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                self._sync_active_page(prefer_content=False)
                self._set_status(EngineStatus.RUNNING)
                self._log("SUCCESS", "页面加载完成")

                if not self._wait_for_content():
                    return

                while not self._stop_event.is_set():
                    self._pause_event.wait()
                    if self._stop_event.is_set():
                        break
                    self._process_page()
                    self._update_stats()

                context.close()
                self.context = None

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

        for attempt in range(120):
            if self._stop_event.is_set():
                return False

            try:
                self._sync_active_page(prefer_content=True, log_reason="检测到新的活动页签")

                if self.options.get("wait_for_captcha", DEFAULT_WAIT_FOR_CAPTCHA) and self._any_page_has_captcha():
                    cleared, _ = self._wait_for_captcha_clear(timeout_seconds=180.0)
                    if not cleared:
                        self._log("ERROR", "等待验证码处理超时，请重新开始任务")
                        return False

                is_login_page = self._page_looks_like_login(self.page)

                if is_login_page and not login_warned:
                    login_warned = True
                    self._set_status(EngineStatus.WAITING_LOGIN)
                    self._log("WARNING", "检测到登录页面，请在浏览器中完成登录")
                    self._log("INFO", "登录后将自动继续...")

                if self._has_known_content():
                    if login_warned or self.status == EngineStatus.WAITING_LOGIN:
                        self._resume_running_status()
                        self._log("INFO", "已检测到课程内容，状态已恢复为运行中")
                    self._log("SUCCESS", "页面内容已就绪")
                    return True

                if login_warned and not is_login_page:
                    if self.status == EngineStatus.WAITING_LOGIN:
                        self._resume_running_status()
                    self._log("INFO", "检测到页面变化，等待课程内容渲染...")

                if attempt > 0 and attempt % 6 == 0 and not is_login_page:
                    self._resume_running_status()
                    self._log("INFO", "暂未识别到课程内容，继续等待页面渲染；如果刚登录完成，请保持课程页停留在前台")
            except Exception:
                pass

            time.sleep(5)

        self._log("ERROR", "等待页面内容超时（10分钟）")
        return False

    def _has_known_content(self, page=None) -> bool:
        if self._find_video_root(page) or self._find_exercise_root(page):
            return True

        return any(self._root_has_next_button(root) for root in self._iter_roots(page))

    # ── Page type detection ──────────────────────────────────────

    def _detect_page_type(self) -> PageType:
        try:
            self._sync_active_page(prefer_content=True)
            time.sleep(2)
            if self._find_video_root():
                return PageType.VIDEO
            if self._find_exercise_root():
                return PageType.EXERCISE
            return PageType.UNKNOWN
        except Exception as e:
            self._log("ERROR", f"页面类型检测失败: {e}")
            return PageType.UNKNOWN

    # ── Page processing ──────────────────────────────────────────

    def _process_page(self):
        try:
            self._sync_active_page(prefer_content=True, log_reason="已切换到课程页签")
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
        video_root = self._find_video_root()
        if not video_root:
            self._log("WARNING", "未找到视频容器，尝试直接切换下一单元")
            self._click_next()
            return

        self._log("SUCCESS", f"✓ 检测到视频页面（{self._describe_root(video_root)}）")

        try:
            video_root.evaluate(INJECT_AUTOPLAY_SCRIPT)
            self._log("INFO", "→ 已注入自动播放脚本")
        except Exception as e:
            self._log("ERROR", f"注入自动播放脚本失败: {e}")
            return

        self._log("INFO", "⏳ 等待视频播放完毕...")
        last_progress_log = 0
        reached_high = False

        while not self._stop_event.is_set():
            self._pause_event.wait()
            if self._stop_event.is_set():
                return

            try:
                result = video_root.evaluate(VIDEO_STATE_SCRIPT)
            except Exception as e:
                self._log("WARNING", f"获取视频状态失败: {e}")
                refreshed_root = self._find_video_root()
                if refreshed_root:
                    video_root = refreshed_root
                time.sleep(2)
                continue

            if not result.get("found"):
                refreshed_root = self._find_video_root()
                if refreshed_root and refreshed_root is not video_root:
                    video_root = refreshed_root
                    continue

                self._log("WARNING", "当前未检测到 <video> 元素，2秒后重试")
                time.sleep(2)
                continue

            duration = result["duration"]
            current = result["current"]
            ended = result.get("ended", False)

            if duration > 0:
                pct = current / duration * 100
                cur_fmt = self._fmt_time(current)
                tot_fmt = self._fmt_time(duration)
                self._emit(
                    MsgType.PROGRESS,
                    {"current": current, "duration": duration, "percent": pct},
                )

                if current - last_progress_log >= 30 or last_progress_log == 0:
                    self._log("INFO", f"  🎬 视频进度: {cur_fmt} / {tot_fmt} ({pct:.0f}%)")
                    last_progress_log = current

                if pct >= 90:
                    reached_high = True

                if ended or (reached_high and pct < 10):
                    self._log("INFO", "检测到视频已经完整播放一轮")
                    break

            time.sleep(2)

        if self._stop_event.is_set():
            return

        self._log("SUCCESS", "✓ 视频播放完毕")
        self.stats["videos"] += 1
        self._update_stats()

        self._log("INFO", "⏳ 等待3秒后切换下一单元...")
        if not self._sleep(3):
            return

        self._click_next()

    # ── Exercise handling ────────────────────────────────────────

    def _handle_exercise(self):
        exercise_root = self._find_exercise_root()
        location = self._describe_root(exercise_root) if exercise_root else "主文档"
        self._log("SUCCESS", f"✓ 检测到习题页面（{location}）")
        self.stats["exercises"] += 1
        self._update_stats()

        self._log("INFO", "⏳ 等待3秒...")
        if not self._sleep(3):
            return

        self._click_next()

    # ── Navigation ───────────────────────────────────────────────

    def _click_next(self):
        try:
            self._sync_active_page(prefer_content=True, log_reason="准备切换下一单元")
            previous_snapshot = self._get_page_snapshot()
            last_snapshot = previous_snapshot
            click_methods = []
            combo_enabled = self._is_strategy_enabled("combo")
            if self._is_strategy_enabled("locator"):
                click_methods.append(self._click_next_via_locator)
            if self._is_strategy_enabled("js"):
                click_methods.append(self._click_next_in_root)
            if self._is_strategy_enabled("keyboard"):
                click_methods.append(self._click_next_via_keyboard)
            if self._is_strategy_enabled("mouse"):
                click_methods.append(self._click_next_via_mouse)
            if self._is_strategy_enabled("touch"):
                click_methods.append(self._click_next_via_touch)

            if not combo_enabled and not click_methods and not self._is_strategy_enabled("direct_nav"):
                self._log("ERROR", "未启用任何切换方案，请先在界面中勾选至少一种方案")
                self.stats["errors"] += 1
                return

            for attempt in range(1, 4):
                self._sync_active_page(prefer_content=True)
                previous_snapshot = self._get_page_snapshot()

                if self.options.get("wait_for_captcha", DEFAULT_WAIT_FOR_CAPTCHA):
                    cleared, latest_snapshot = self._wait_for_captcha_clear()
                    previous_snapshot = latest_snapshot
                    last_snapshot = latest_snapshot
                    if not cleared:
                        self._log("WARNING", "验证码等待超时，继续按已勾选方案尝试")

                if combo_enabled:
                    combo_clicked, last_snapshot = self._click_next_via_combo(previous_snapshot)
                    if combo_clicked:
                        if self._snapshot_changed(previous_snapshot, last_snapshot):
                            self._finalize_next_click(combo_clicked)
                            return
                        self._log(
                            "WARNING",
                            f"已尝试「{combo_clicked['strategy']}」点击，但页面未切换，继续尝试其他方式",
                        )

                for root in self._iter_roots():
                    for click_method in click_methods:
                        clicked, last_snapshot, changed = self._attempt_click_method_with_follow_up(
                            click_method,
                            root,
                            previous_snapshot,
                        )
                        if not clicked:
                            continue

                        if changed:
                            self._finalize_next_click(clicked)
                            return

                        self._log(
                            "WARNING",
                            f"已尝试「{clicked['strategy']}」点击，但页面未切换，继续尝试其他方式",
                        )

                if self._is_strategy_enabled("direct_nav"):
                    navigated = self._navigate_to_next_url()
                    if navigated:
                        changed, last_snapshot = self._wait_for_next_unit_change(previous_snapshot)
                        if changed:
                            self._finalize_next_click(navigated)
                            return

                        self._log(
                            "WARNING",
                            f"已尝试「{navigated['strategy']}」切换，但页面未切换，继续重试",
                        )

                if attempt < 3:
                    self._log("WARNING", f"第 {attempt} 轮点击未成功切换页面，2秒后重试...")
                    if not self._sleep(2):
                        return

            diagnostics = self._collect_next_button_diagnostics()
            if diagnostics:
                self._log("WARNING", f"未能成功点击「{NEXT_BUTTON_TEXT}」，候选节点: {diagnostics}")
            else:
                self._log("WARNING", f"未找到「{NEXT_BUTTON_TEXT}」按钮")

            if previous_snapshot or last_snapshot:
                self._log(
                    "INFO",
                    "点击前页面快照: "
                    + self._format_snapshot(previous_snapshot)
                    + " ; 点击后页面快照: "
                    + self._format_snapshot(last_snapshot),
                )

            self._log("INFO", "课程可能已全部完成")
            self._stop_event.set()

        except Exception as e:
            self._log("ERROR", f"点击{NEXT_BUTTON_TEXT}失败: {e}")
            self.stats["errors"] += 1
