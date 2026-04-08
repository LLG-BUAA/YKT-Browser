from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


APP_NAME = "YKT Browser"
APP_VERSION = "0.3.0"
DEFAULT_URL = "https://buaa.yuketang.cn/pro/lms/CUJttg2ZDc3/31025069/video/79236580"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_profile_dir() -> str:
    return str(project_root() / "browser-profile")


def default_logs_dir() -> str:
    return str(project_root() / "logs")


def find_browser_path() -> str:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return ""


@dataclass(slots=True)
class AutomationConfig:
    url: str = DEFAULT_URL
    browser_path: str = field(default_factory=find_browser_path)
    user_data_dir: str = field(default_factory=default_profile_dir)
    logs_dir: str = field(default_factory=default_logs_dir)
    poll_seconds: float = 1.0
    video_end_wait_seconds: int = 10
    exercise_wait_seconds: int = 10
    page_load_timeout_ms: int = 60000
    next_retry_seconds: int = 5
    status_log_interval_seconds: int = 5
    headless: bool = False
    auto_return_to_target_after_login: bool = True
    infinite_runtime: bool = True
    max_runtime_seconds: int = 60
    test_seek_to_end_after_seconds: int = 0
    test_force_ended_after_seconds: int = 0

    def normalized(self) -> "AutomationConfig":
        return AutomationConfig(
            url=self.url.strip() or DEFAULT_URL,
            browser_path=(self.browser_path or find_browser_path()).strip(),
            user_data_dir=str(Path(self.user_data_dir).expanduser()),
            logs_dir=str(Path(self.logs_dir).expanduser()),
            poll_seconds=max(0.2, float(self.poll_seconds)),
            video_end_wait_seconds=max(0, int(self.video_end_wait_seconds)),
            exercise_wait_seconds=max(0, int(self.exercise_wait_seconds)),
            page_load_timeout_ms=max(3000, int(self.page_load_timeout_ms)),
            next_retry_seconds=max(1, int(self.next_retry_seconds)),
            status_log_interval_seconds=max(1, int(self.status_log_interval_seconds)),
            headless=bool(self.headless),
            auto_return_to_target_after_login=bool(self.auto_return_to_target_after_login),
            infinite_runtime=bool(self.infinite_runtime),
            max_runtime_seconds=max(0, int(self.max_runtime_seconds)),
            test_seek_to_end_after_seconds=max(0, int(self.test_seek_to_end_after_seconds)),
            test_force_ended_after_seconds=max(0, int(self.test_force_ended_after_seconds)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "browser_path": self.browser_path,
            "user_data_dir": self.user_data_dir,
            "logs_dir": self.logs_dir,
            "poll_seconds": self.poll_seconds,
            "video_end_wait_seconds": self.video_end_wait_seconds,
            "exercise_wait_seconds": self.exercise_wait_seconds,
            "page_load_timeout_ms": self.page_load_timeout_ms,
            "next_retry_seconds": self.next_retry_seconds,
            "status_log_interval_seconds": self.status_log_interval_seconds,
            "headless": self.headless,
            "auto_return_to_target_after_login": self.auto_return_to_target_after_login,
            "infinite_runtime": self.infinite_runtime,
            "max_runtime_seconds": self.max_runtime_seconds,
            "test_seek_to_end_after_seconds": self.test_seek_to_end_after_seconds,
            "test_force_ended_after_seconds": self.test_force_ended_after_seconds,
        }


@dataclass(slots=True)
class LogEvent:
    timestamp: datetime
    level: str
    category: str
    code: str
    message: str
    details: str = ""
    suggestion: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_console_line(self) -> str:
        prefix = f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] [{self.level}] [{self.category}/{self.code}]"
        detail_parts = [part for part in [self.message, self.details, self.suggestion] if part]
        return f"{prefix} {' | '.join(detail_parts)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(timespec="seconds"),
            "level": self.level,
            "category": self.category,
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "suggestion": self.suggestion,
            "data": self.data,
        }


@dataclass(slots=True)
class RuntimeStatus:
    session_id: str = ""
    is_running: bool = False
    stage: str = "idle"
    page_kind: str = "unknown"
    page_url: str = ""
    page_title: str = ""
    last_message: str = "等待启动"
    last_event_code: str = ""
    started_at: str = ""
    elapsed_seconds: float = 0.0
    countdown_seconds: int = -1
    keepalive_state: str = "inactive"
    video_current: float = 0.0
    video_duration: float = 0.0
    video_paused: bool = False
    video_ended: bool = False
    next_clicks: int = 0
    warnings: int = 0
    errors: int = 0
    infos: int = 0
    session_dir: str = ""
    text_log_path: str = ""
    jsonl_log_path: str = ""
    last_error_hint: str = ""

    def copy_with(self, **changes: Any) -> "RuntimeStatus":
        values = {
            "session_id": self.session_id,
            "is_running": self.is_running,
            "stage": self.stage,
            "page_kind": self.page_kind,
            "page_url": self.page_url,
            "page_title": self.page_title,
            "last_message": self.last_message,
            "last_event_code": self.last_event_code,
            "started_at": self.started_at,
            "elapsed_seconds": self.elapsed_seconds,
            "countdown_seconds": self.countdown_seconds,
            "keepalive_state": self.keepalive_state,
            "video_current": self.video_current,
            "video_duration": self.video_duration,
            "video_paused": self.video_paused,
            "video_ended": self.video_ended,
            "next_clicks": self.next_clicks,
            "warnings": self.warnings,
            "errors": self.errors,
            "infos": self.infos,
            "session_dir": self.session_dir,
            "text_log_path": self.text_log_path,
            "jsonl_log_path": self.jsonl_log_path,
            "last_error_hint": self.last_error_hint,
        }
        values.update(changes)
        return RuntimeStatus(**values)
