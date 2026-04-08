"""
YKT Browser - 雨课堂自动播放助手 GUI
现代化暗色主题界面
"""

import queue
import time
import sys
import customtkinter as ctk

from engine import (
    CLICK_STRATEGY_OPTIONS,
    DEFAULT_WAIT_FOR_CAPTCHA,
    EngineStatus,
    MsgType,
    YuketangEngine,
)


class YuketangApp(ctk.CTk):
    VERSION = "1.0.0"

    # Color palette
    C_BG_DARK = "#0f1117"
    C_CARD = "#1a1d28"
    C_CARD_HOVER = "#22263a"
    C_ACCENT = "#3b82f6"
    C_ACCENT_HOVER = "#2563eb"
    C_SUCCESS = "#22c55e"
    C_WARNING = "#f59e0b"
    C_ERROR = "#ef4444"
    C_TEXT = "#e2e8f0"
    C_TEXT_DIM = "#64748b"
    C_BORDER = "#2d3348"

    def __init__(self):
        super().__init__()

        # Window config
        self.title("YKT Browser - 雨课堂自动播放助手")
        self.geometry("860x860")
        self.minsize(760, 720)
        self.configure(fg_color=self.C_BG_DARK)

        # Theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # State
        self.msg_queue = queue.Queue()
        self.engine = None
        self.start_time = None
        self._is_paused = False
        self.strategy_vars = {}
        self.strategy_checkboxes = []
        self.strategy_toggle_btn = None
        self.advanced_strategy_frame = None
        self.advanced_strategies_visible = False
        self.wait_for_captcha_var = ctk.BooleanVar(value=DEFAULT_WAIT_FOR_CAPTCHA)

        # Build UI
        self._build_header()
        self._build_url_section()
        self._build_controls()
        self._build_strategy_section()
        self._build_status_section()
        self._build_log_section()

        # Grid weights
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)

        # Start polling
        self._poll_queue()
        self._update_timer()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Welcome message
        self._add_log("INFO", "YKT Browser v" + self.VERSION + " 就绪")
        self._add_log("INFO", "粘贴课程链接后点击「开始」启动自动播放")
        self._add_log("INFO", "首次使用需要在弹出的浏览器中登录雨课堂账号")
        self._add_log("INFO", "可在“切换方案”里勾选要尝试的点击/跳转策略")

    # ── UI Construction ──────────────────────────────────────────

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 4))

        ctk.CTkLabel(
            header,
            text="🎓  雨课堂自动播放助手",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.C_TEXT,
        ).pack(side="left")

        ver_frame = ctk.CTkFrame(header, fg_color=self.C_CARD, corner_radius=12)
        ver_frame.pack(side="right")
        ctk.CTkLabel(
            ver_frame,
            text=f"  v{self.VERSION}  ",
            font=ctk.CTkFont(size=11),
            text_color=self.C_TEXT_DIM,
        ).pack(padx=6, pady=2)

    def _build_url_section(self):
        card = ctk.CTkFrame(self, fg_color=self.C_CARD, corner_radius=12, border_width=1, border_color=self.C_BORDER)
        card.grid(row=1, column=0, sticky="ew", padx=24, pady=6)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text="课程地址",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.C_TEXT,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(12, 4))

        self.url_entry = ctk.CTkEntry(
            card,
            placeholder_text="粘贴雨课堂课程页面链接",
            height=40,
            font=ctk.CTkFont(size=13),
            fg_color="#151822",
            border_color=self.C_BORDER,
            text_color=self.C_TEXT,
        )
        self.url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(16, 4), pady=(0, 14))
        self.url_entry.insert(0, "https://buaa.yuketang.cn/pro/lms/CUJttg2ZDc3/31025069/video/79236580")

        paste_btn = ctk.CTkButton(
            card,
            text="📋 粘贴",
            width=70,
            height=40,
            font=ctk.CTkFont(size=12),
            fg_color="#252a3a",
            hover_color="#2d3348",
            border_width=1,
            border_color=self.C_BORDER,
            command=self._paste_url,
        )
        paste_btn.grid(row=1, column=2, padx=(0, 16), pady=(0, 14))

    def _build_controls(self):
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.grid(row=2, column=0, sticky="ew", padx=24, pady=4)

        btn_font = ctk.CTkFont(size=14, weight="bold")

        self.start_btn = ctk.CTkButton(
            ctrl, text="▶  开 始", width=140, height=42, font=btn_font,
            fg_color=self.C_ACCENT, hover_color=self.C_ACCENT_HOVER,
            corner_radius=10, command=self._on_start,
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.pause_btn = ctk.CTkButton(
            ctrl, text="⏸  暂 停", width=140, height=42,
            font=ctk.CTkFont(size=14),
            fg_color="#374151", hover_color="#4b5563",
            corner_radius=10, command=self._on_pause, state="disabled",
        )
        self.pause_btn.pack(side="left", padx=4)

        self.stop_btn = ctk.CTkButton(
            ctrl, text="⏹  停 止", width=140, height=42,
            font=ctk.CTkFont(size=14),
            fg_color="#7f1d1d", hover_color="#991b1b",
            corner_radius=10, command=self._on_stop, state="disabled",
        )
        self.stop_btn.pack(side="left", padx=8)

    def _build_strategy_section(self):
        card = ctk.CTkFrame(
            self,
            fg_color=self.C_CARD,
            corner_radius=12,
            border_width=1,
            border_color=self.C_BORDER,
        )
        card.grid(row=3, column=0, sticky="ew", padx=24, pady=6)
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text="切换方案",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.C_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 2))

        ctk.CTkLabel(
            card,
            text="默认只展示推荐方案；其他备用方案默认折叠，只有排查兼容性时再展开。",
            font=ctk.CTkFont(size=11),
            text_color=self.C_TEXT_DIM,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 10))

        primary_key, primary_label, primary_desc = CLICK_STRATEGY_OPTIONS[0]
        primary_frame = ctk.CTkFrame(card, fg_color="transparent")
        primary_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=4)
        self._build_strategy_option(
            primary_frame,
            primary_key,
            primary_label,
            primary_desc,
            default_value=True,
        )

        ctk.CTkLabel(
            primary_frame,
            text="推荐：这是当前默认方案，通过测试的方案：“第一次预热、第二次才真正切页”的页面行为。",
            font=ctk.CTkFont(size=11),
            text_color=self.C_TEXT_DIM,
        ).pack(anchor="w", padx=(30, 0), pady=(4, 0))

        self.strategy_toggle_btn = ctk.CTkButton(
            card,
            text="展开其他备用方案",
            width=128,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            hover_color="#252a3a",
            border_width=1,
            border_color=self.C_BORDER,
            text_color=self.C_TEXT_DIM,
            corner_radius=8,
            command=self._toggle_advanced_strategies,
        )
        self.strategy_toggle_btn.grid(row=3, column=0, sticky="w", padx=16, pady=(4, 6))

        self.advanced_strategy_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.advanced_strategy_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        self.advanced_strategy_frame.grid_columnconfigure(0, weight=1)
        self.advanced_strategy_frame.grid_columnconfigure(1, weight=1)
        self.advanced_strategy_frame.grid_remove()

        for index, (key, label, description) in enumerate(CLICK_STRATEGY_OPTIONS[1:]):
            row = index // 2
            column = index % 2
            option_frame = ctk.CTkFrame(self.advanced_strategy_frame, fg_color="transparent")
            option_frame.grid(row=row, column=column, sticky="ew", padx=16, pady=4)
            self._build_strategy_option(
                option_frame,
                key,
                label,
                description,
                default_value=False,
            )

        ctk.CTkLabel(
            self.advanced_strategy_frame,
            text="这些方案主要用于排查页面兼容性，默认都不会启用。",
            font=ctk.CTkFont(size=11),
            text_color=self.C_TEXT_DIM,
        ).grid(row=(len(CLICK_STRATEGY_OPTIONS) // 2) + 1, column=0, columnspan=2, sticky="w", padx=16, pady=(2, 6))

        captcha_row = 5
        captcha_checkbox = ctk.CTkCheckBox(
            card,
            text="检测到验证码时等待人工处理",
            variable=self.wait_for_captcha_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.C_TEXT,
            checkbox_width=18,
            checkbox_height=18,
            border_width=2,
            corner_radius=4,
        )
        captcha_checkbox.grid(row=captcha_row, column=0, sticky="w", padx=16, pady=(8, 12))
        self.strategy_checkboxes.append(captcha_checkbox)

        ctk.CTkLabel(
            card,
            text="开启后，如果页面弹出腾讯验证码/风控层，程序会先等待你手动完成验证，再继续切换。",
            font=ctk.CTkFont(size=11),
            text_color=self.C_TEXT_DIM,
        ).grid(row=captcha_row, column=1, sticky="w", padx=16, pady=(8, 12))

    def _build_strategy_option(self, parent, key, label, description, default_value):
        var = ctk.BooleanVar(value=default_value)
        checkbox = ctk.CTkCheckBox(
            parent,
            text=label,
            variable=var,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.C_TEXT,
            checkbox_width=18,
            checkbox_height=18,
            border_width=2,
            corner_radius=4,
        )
        checkbox.pack(anchor="w")

        ctk.CTkLabel(
            parent,
            text=description,
            font=ctk.CTkFont(size=11),
            text_color=self.C_TEXT_DIM,
        ).pack(anchor="w", padx=(30, 0), pady=(2, 0))

        self.strategy_vars[key] = var
        self.strategy_checkboxes.append(checkbox)

    def _toggle_advanced_strategies(self):
        if self.advanced_strategy_frame is None or self.strategy_toggle_btn is None:
            return

        self.advanced_strategies_visible = not self.advanced_strategies_visible
        if self.advanced_strategies_visible:
            self.advanced_strategy_frame.grid()
            self.strategy_toggle_btn.configure(text="收起其他备用方案")
        else:
            self.advanced_strategy_frame.grid_remove()
            self.strategy_toggle_btn.configure(text="展开其他备用方案")

    def _build_status_section(self):
        card = ctk.CTkFrame(self, fg_color=self.C_CARD, corner_radius=12, border_width=1, border_color=self.C_BORDER)
        card.grid(row=4, column=0, sticky="ew", padx=24, pady=6)
        card.grid_columnconfigure(0, weight=1)

        # Row 1: status + timer
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 2))

        self.status_dot = ctk.CTkLabel(
            row1, text="●", font=ctk.CTkFont(size=14),
            text_color=self.C_TEXT_DIM, width=16,
        )
        self.status_dot.pack(side="left")
        self.status_label = ctk.CTkLabel(
            row1, text="就绪",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.C_TEXT_DIM,
        )
        self.status_label.pack(side="left", padx=(4, 0))

        self.timer_label = ctk.CTkLabel(
            row1, text="⏱  00:00:00",
            font=ctk.CTkFont(size=13, family="Consolas"),
            text_color=self.C_TEXT_DIM,
        )
        self.timer_label.pack(side="right")

        # Row 2: stats
        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.grid(row=1, column=0, sticky="ew", padx=16, pady=2)

        self.stats_label = ctk.CTkLabel(
            row2,
            text="📊  视频: 0  ·  习题: 0  ·  切换: 0  ·  错误: 0",
            font=ctk.CTkFont(size=12),
            text_color=self.C_TEXT_DIM,
        )
        self.stats_label.pack(side="left")

        # Row 3: progress
        self.progress_bar = ctk.CTkProgressBar(
            card, height=8, corner_radius=4,
            fg_color="#1e2130", progress_color=self.C_ACCENT,
        )
        self.progress_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 2))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            card, text="",
            font=ctk.CTkFont(size=11),
            text_color=self.C_TEXT_DIM,
        )
        self.progress_label.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 10))

    def _build_log_section(self):
        # Log header
        log_header = ctk.CTkFrame(self, fg_color="transparent")
        log_header.grid(row=5, column=0, sticky="new", padx=24, pady=(6, 2))

        ctk.CTkLabel(
            log_header, text="📝  运行日志",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.C_TEXT,
        ).pack(side="left")

        ctk.CTkButton(
            log_header, text="清空", width=50, height=24,
            font=ctk.CTkFont(size=11),
            fg_color="transparent", hover_color="#252a3a",
            border_width=1, border_color=self.C_BORDER,
            text_color=self.C_TEXT_DIM,
            corner_radius=6, command=self._clear_log,
        ).pack(side="right")

        # Log textbox
        self.log_text = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(size=12, family="Consolas"),
            fg_color="#0c0e14",
            text_color=self.C_TEXT,
            corner_radius=10,
            border_width=1,
            border_color=self.C_BORDER,
            activate_scrollbars=True,
            wrap="word",
        )
        self.log_text.grid(row=6, column=0, sticky="nsew", padx=24, pady=(0, 18))
        self.grid_rowconfigure(6, weight=1)

        # Tag colors
        self.log_text.tag_config("ts", foreground="#475569")
        self.log_text.tag_config("info", foreground="#60a5fa")
        self.log_text.tag_config("success", foreground="#4ade80")
        self.log_text.tag_config("warning", foreground="#fbbf24")
        self.log_text.tag_config("error", foreground="#f87171")
        self.log_text.tag_config("badge_info", foreground="#1e293b", background="#3b82f6")
        self.log_text.tag_config("badge_ok", foreground="#052e16", background="#22c55e")
        self.log_text.tag_config("badge_warn", foreground="#1c1917", background="#f59e0b")
        self.log_text.tag_config("badge_err", foreground="#fff", background="#dc2626")

        self.log_text.configure(state="disabled")

    # ── Actions ──────────────────────────────────────────────────

    def _paste_url(self):
        try:
            text = self.clipboard_get()
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, text.strip())
        except Exception:
            pass

    def _collect_engine_options(self):
        click_strategies = [
            key for key, var in self.strategy_vars.items()
            if var.get()
        ]
        return {
            "click_strategies": click_strategies,
            "wait_for_captcha": self.wait_for_captcha_var.get(),
        }

    def _set_strategy_controls_state(self, state):
        for checkbox in self.strategy_checkboxes:
            checkbox.configure(state=state)
        if self.strategy_toggle_btn is not None:
            self.strategy_toggle_btn.configure(state=state)

    def _on_start(self):
        url = self.url_entry.get().strip()
        if not url:
            self._add_log("ERROR", "请输入课程链接")
            return
        if not url.startswith("http"):
            self._add_log("ERROR", "请输入有效的URL（以 http 开头）")
            return

        options = self._collect_engine_options()
        if not options["click_strategies"]:
            self._add_log("ERROR", "请至少勾选一种切换方案")
            return

        strategy_labels = [
            checkbox_label
            for key, checkbox_label, _ in CLICK_STRATEGY_OPTIONS
            if key in options["click_strategies"]
        ]

        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.url_entry.configure(state="disabled")
        self._set_strategy_controls_state("disabled")
        self._is_paused = False
        self.start_time = time.time()
        self.progress_bar.set(0)
        self.progress_label.configure(text="")

        self._add_log("INFO", "本次启用方案: " + "、".join(strategy_labels))
        self._add_log(
            "INFO",
            "验证码等待人工处理: " + ("开启" if options["wait_for_captcha"] else "关闭"),
        )

        self.engine = YuketangEngine(self.msg_queue, options=options)
        self.engine.start(url)

    def _on_pause(self):
        if not self.engine:
            return
        if self._is_paused:
            self.engine.resume()
            self.pause_btn.configure(text="⏸  暂 停", fg_color="#374151")
            self._is_paused = False
        else:
            self.engine.pause()
            self.pause_btn.configure(text="▶  继 续", fg_color="#065f46")
            self._is_paused = True

    def _on_stop(self):
        if self.engine:
            self.engine.stop()

    def _on_close(self):
        if self.engine and self.engine.is_running:
            self.engine.stop()
            self.after(500, self.destroy)
        else:
            self.destroy()

    def _reset_controls(self):
        self.start_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled", text="⏸  暂 停", fg_color="#374151")
        self.stop_btn.configure(state="disabled")
        self.url_entry.configure(state="normal")
        self._set_strategy_controls_state("normal")
        self._is_paused = False

    # ── Log / Status updates ─────────────────────────────────────

    def _add_log(self, level: str, message: str):
        ts = time.strftime("%H:%M:%S")
        self._add_log_entry(ts, level, message)

    def _add_log_entry(self, timestamp, level, message):
        badge_map = {
            "INFO":    ("INFO", "badge_info"),
            "SUCCESS": (" OK ", "badge_ok"),
            "WARNING": ("WARN", "badge_warn"),
            "ERROR":   ("ERR!", "badge_err"),
        }
        text_tag_map = {
            "INFO": "info", "SUCCESS": "success",
            "WARNING": "warning", "ERROR": "error",
        }

        badge_text, badge_tag = badge_map.get(level, ("INFO", "badge_info"))
        text_tag = text_tag_map.get(level, "info")

        self.log_text.configure(state="normal")
        self.log_text.insert("end", f" {timestamp} ", "ts")
        self.log_text.insert("end", f" {badge_text} ", badge_tag)
        self.log_text.insert("end", f"  {message}\n", text_tag)
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _update_status_display(self, status_text):
        color_map = {
            "运行中":   self.C_SUCCESS,
            "已暂停":   self.C_WARNING,
            "已停止":   self.C_TEXT_DIM,
            "启动中":   self.C_ACCENT,
            "停止中":   self.C_WARNING,
            "空闲":     self.C_TEXT_DIM,
            "等待登录": self.C_WARNING,
            "等待验证": self.C_WARNING,
        }
        color = color_map.get(status_text, self.C_TEXT_DIM)
        self.status_dot.configure(text_color=color)
        self.status_label.configure(text=status_text, text_color=color)

        if status_text == "已停止":
            self._reset_controls()

    def _update_stats_display(self, stats):
        self.stats_label.configure(
            text=(
                f"📊  视频: {stats['videos']}  ·  "
                f"习题: {stats['exercises']}  ·  "
                f"切换: {stats['units']}  ·  "
                f"错误: {stats['errors']}"
            )
        )

    def _update_progress_display(self, data):
        if data["duration"] > 0:
            self.progress_bar.set(data["percent"] / 100.0)
            cur = self._fmt_time(data["current"])
            tot = self._fmt_time(data["duration"])
            self.progress_label.configure(
                text=f"🎬  {cur} / {tot}  ({data['percent']:.0f}%)"
            )

    # ── Polling ──────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            for _ in range(50):  # process up to 50 msgs per tick
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == MsgType.LOG:
                    self._add_log_entry(*data)
                elif msg_type == MsgType.STATUS:
                    self._update_status_display(data)
                elif msg_type == MsgType.STATS:
                    self._update_stats_display(data)
                elif msg_type == MsgType.PROGRESS:
                    self._update_progress_display(data)
                elif msg_type == MsgType.FINISHED:
                    self._reset_controls()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _update_timer(self):
        if self.start_time and self.engine and self.engine.is_running:
            elapsed = int(time.time() - self.start_time)
            self.timer_label.configure(text=f"⏱  {self._fmt_time(elapsed)}")
        self.after(1000, self._update_timer)

    @staticmethod
    def _fmt_time(seconds):
        s = int(seconds)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
