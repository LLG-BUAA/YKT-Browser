from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import AutomationConfig, LogEvent


class SessionLogger:
    def __init__(self, base_dir: str, session_id: str) -> None:
        self.session_id = session_id
        self.session_dir = Path(base_dir).resolve() / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.text_log_path = self.session_dir / "session.log"
        self.jsonl_log_path = self.session_dir / "events.jsonl"
        self.config_path = self.session_dir / "config.json"
        self.lock = threading.Lock()

    def write_config(self, config: AutomationConfig) -> None:
        self.config_path.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append(self, event: LogEvent) -> None:
        with self.lock:
            with self.text_log_path.open("a", encoding="utf-8") as text_file:
                text_file.write(event.to_console_line() + "\n")
            with self.jsonl_log_path.open("a", encoding="utf-8") as jsonl_file:
                jsonl_file.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
