from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Qt, QUrl, QObject, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .core import YukeTangAutomation
from .models import APP_NAME, APP_VERSION, AutomationConfig, LogEvent, RuntimeStatus, find_browser_path
from .styles import APP_STYLE


LEVEL_COLORS = {
    "INFO": "#365c9c",
    "SUCCESS": "#2c7a58",
    "WARNING": "#b27325",
    "ERROR": "#b14a48",
}
STAGE_LABELS = {
    "idle": "空闲",
    "launching": "启动中",
    "loading": "加载中",
    "running": "运行中",
    "waiting_login": "等待登录",
    "waiting_captcha": "等待验证",
    "error": "错误",
    "stopped": "已停止",
}
PAGE_LABELS = {
    "unknown": "未识别",
    "video": "视频页",
    "exercise": "习题页",
    "login": "登录页",
    "captcha": "验证页",
}


class SectionCard(QFrame):
    def __init__(self, title_text: str, hint_text: str = "", eyebrow_text: str = "") -> None:
        super().__init__()
        self.setObjectName("SectionCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        if eyebrow_text:
            eyebrow = QLabel(eyebrow_text)
            eyebrow.setObjectName("SectionEyebrow")
            layout.addWidget(eyebrow)

        title = QLabel(title_text)
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        if hint_text:
            hint = QLabel(hint_text)
            hint.setObjectName("SectionHint")
            hint.setWordWrap(True)
            layout.addWidget(hint)

        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        layout.addLayout(self.body_layout)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self.body_layout.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.body_layout.addLayout(layout, stretch)


class StatTile(QFrame):
    def __init__(self, label_text: str, value_text: str = "-", hint_text: str = "") -> None:
        super().__init__()
        self.setObjectName("StatTile")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(104)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        self.label = QLabel(label_text)
        self.label.setObjectName("StatLabel")
        self.value = QLabel(value_text)
        self.value.setObjectName("StatValue")
        self.value.setWordWrap(True)
        self.hint = QLabel(hint_text)
        self.hint.setObjectName("StatHint")
        self.hint.setWordWrap(True)

        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.hint)

    def set_content(self, value_text: str, hint_text: str = "") -> None:
        self.value.setText(value_text)
        self.hint.setText(hint_text)


class AutomationWorker(QObject):
    event_emitted = Signal(object)
    status_changed = Signal(object)
    finished = Signal(bool, str)

    def __init__(self, config: AutomationConfig) -> None:
        super().__init__()
        self.config = config
        self.runner: YukeTangAutomation | None = None

    @Slot()
    def run(self) -> None:
        try:
            self.runner = YukeTangAutomation(
                self.config,
                on_event=self.event_emitted.emit,
                on_status=self.status_changed.emit,
            )
            self.runner.run()
            self.finished.emit(True, "")
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc))

    @Slot()
    def stop(self) -> None:
        if self.runner is not None:
            self.runner.stop()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1520, 980)
        self.setMinimumSize(1260, 820)

        self.settings = QSettings("Codex", "YKTBrowser")
        self.events: list[LogEvent] = []
        self.filtered_events: list[LogEvent] = []
        self.status = RuntimeStatus()
        self.thread: QThread | None = None
        self.worker: AutomationWorker | None = None

        self._build_ui()
        self._load_settings()
        self._apply_status(RuntimeStatus())

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(18)

        root_layout.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([430, 1020])
        root_layout.addWidget(splitter, 1)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("HeroPanel")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(20)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)

        eyebrow = QLabel("RAIN CLASSROOM DESKTOP")
        eyebrow.setObjectName("HeroEyebrow")
        title = QLabel("雨课堂自动化控制台")
        title.setObjectName("HeroTitle")
        subtitle = QLabel("真实浏览器控制、结构化日志、错误诊断与会话归档整合在一个桌面工具里。")
        subtitle.setObjectName("HeroSubtitle")
        subtitle.setWordWrap(True)

        text_layout.addWidget(eyebrow)
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        action_column = QVBoxLayout()
        action_column.setSpacing(10)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.start_button = QPushButton("开始运行")
        self.stop_button = QPushButton("停止任务")
        self.stop_button.setEnabled(False)
        self.stop_button.setProperty("variant", "secondary")
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.stop_button)

        self.status_badge = QLabel("空闲")
        self.status_badge.setObjectName("StatusBadge")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setMinimumWidth(124)

        self.hero_message = QLabel("等待启动")
        self.hero_message.setObjectName("HeroStatusText")
        self.hero_message.setWordWrap(True)

        action_column.addLayout(action_row)
        action_column.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignRight)
        action_column.addWidget(self.hero_message, 0, Qt.AlignmentFlag.AlignRight)

        layout.addLayout(text_layout, 1)
        layout.addLayout(action_column)

        self.start_button.clicked.connect(self._start_automation)
        self.stop_button.clicked.connect(self._stop_automation)
        return header

    def _build_left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(14)

        target_card = SectionCard("目标与目录", "把课程页、浏览器和会话目录配置在这里。", "WORKSPACE")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        self.url_input = QLineEdit()
        self.browser_input = QLineEdit()
        self.profile_input = QLineEdit()
        self.logs_input = QLineEdit()

        form.addRow("课程链接", self.url_input)
        form.addRow("浏览器路径", self._path_row(self.browser_input, self._browse_browser, self._detect_browser))
        form.addRow("用户目录", self._path_row(self.profile_input, self._browse_profile))
        form.addRow("日志目录", self._path_row(self.logs_input, self._browse_logs))
        target_card.add_layout(form)

        rule_card = SectionCard("运行规则", "统一控制轮询、等待、运行时长和页面超时。", "AUTOMATION")
        rule_grid = QGridLayout()
        rule_grid.setHorizontalSpacing(12)
        rule_grid.setVerticalSpacing(12)

        self.poll_spin = self._make_double_spin(0.2, 30.0, 1.0, 1)
        self.video_wait_spin = self._make_spin(0, 300, 10, " s")
        self.exercise_wait_spin = self._make_spin(0, 300, 10, " s")
        self.retry_spin = self._make_spin(1, 300, 5, " s")
        self.status_interval_spin = self._make_spin(1, 300, 5, " s")
        self.page_timeout_spin = self._make_spin(3000, 300000, 60000, " ms")
        self.max_runtime_spin = self._make_spin(1, 86400, 60, " s")
        self.infinite_runtime_checkbox = QCheckBox("无限时间")
        self.infinite_runtime_checkbox.setChecked(True)

        runtime_box = QWidget()
        runtime_layout = QHBoxLayout(runtime_box)
        runtime_layout.setContentsMargins(0, 0, 0, 0)
        runtime_layout.setSpacing(10)
        runtime_layout.addWidget(self.infinite_runtime_checkbox, 0)
        runtime_layout.addWidget(self.max_runtime_spin, 1)

        rule_grid.addWidget(self._field_block("轮询间隔", self.poll_spin), 0, 0)
        rule_grid.addWidget(self._field_block("视频完成等待", self.video_wait_spin), 0, 1)
        rule_grid.addWidget(self._field_block("非视频页等待", self.exercise_wait_spin), 1, 0)
        rule_grid.addWidget(self._field_block("点击重试间隔", self.retry_spin), 1, 1)
        rule_grid.addWidget(self._field_block("状态日志间隔", self.status_interval_spin), 2, 0)
        rule_grid.addWidget(self._field_block("页面超时", self.page_timeout_spin), 2, 1)
        rule_grid.addWidget(self._field_block("运行时长", runtime_box), 3, 0, 1, 2)
        rule_card.add_layout(rule_grid)

        self.infinite_runtime_checkbox.toggled.connect(self._toggle_runtime_limit)

        extra_card = SectionCard("高级选项", "登录回跳、无头模式和测试参数集中管理。", "ADVANCED")
        extra_grid = QGridLayout()
        extra_grid.setHorizontalSpacing(12)
        extra_grid.setVerticalSpacing(12)

        self.test_seek_spin = self._make_spin(0, 3600, 0, " s")
        self.test_force_spin = self._make_spin(0, 3600, 0, " s")
        self.headless_checkbox = QCheckBox("无头模式")
        self.auto_return_checkbox = QCheckBox("登录后自动回到课程页")
        self.auto_return_checkbox.setChecked(True)

        extra_grid.addWidget(self._field_block("测试快进到结尾", self.test_seek_spin), 0, 0)
        extra_grid.addWidget(self._field_block("测试模拟已播放完", self.test_force_spin), 0, 1)
        extra_grid.addWidget(self.headless_checkbox, 1, 0)
        extra_grid.addWidget(self.auto_return_checkbox, 1, 1)
        extra_card.add_layout(extra_grid)

        tools_card = SectionCard("快捷入口", "会话目录和浏览器用户目录都可以一键打开。", "TOOLS")
        tool_row = QHBoxLayout()
        tool_row.setSpacing(10)
        self.open_logs_button = QPushButton("打开日志目录")
        self.open_logs_button.setProperty("variant", "secondary")
        self.open_profile_button = QPushButton("打开用户目录")
        self.open_profile_button.setProperty("variant", "secondary")
        tool_row.addWidget(self.open_logs_button)
        tool_row.addWidget(self.open_profile_button)
        tools_card.add_layout(tool_row)

        self.open_logs_button.clicked.connect(self._open_logs_dir)
        self.open_profile_button.clicked.connect(self._open_profile_dir)

        layout.addWidget(target_card)
        layout.addWidget(rule_card)
        layout.addWidget(extra_card)
        layout.addWidget(tools_card)
        layout.addStretch(1)

        scroll.setWidget(content)
        return scroll

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        summary_card = SectionCard("运行概览", "关键状态、页面类型与风险信息会实时汇总在这里。", "SUMMARY")
        summary_grid = QGridLayout()
        summary_grid.setHorizontalSpacing(12)
        summary_grid.setVerticalSpacing(12)

        self.stage_tile = StatTile("运行阶段", "空闲", "等待任务启动")
        self.page_tile = StatTile("页面识别", "未识别", "等待页面进入目标状态")
        self.runtime_tile = StatTile("已运行", "0s", "默认无限时间")
        self.click_tile = StatTile("自动跳转", "0 次", "尚未触发下一单元")
        self.risk_tile = StatTile("告警 / 错误", "0 / 0", "暂无异常")
        self.session_tile = StatTile("会话目录", "-", "启动后自动生成")

        tiles = [
            self.stage_tile,
            self.page_tile,
            self.runtime_tile,
            self.click_tile,
            self.risk_tile,
            self.session_tile,
        ]
        for index, tile in enumerate(tiles):
            summary_grid.addWidget(tile, index // 3, index % 3)
        summary_card.add_layout(summary_grid)
        layout.addWidget(summary_card)

        live_card = SectionCard("实时状态", "播放进度、保活状态、倒计时和最后提示都会在这里更新。", "LIVE")
        live_top = QHBoxLayout()
        live_top.setSpacing(10)

        self.live_badge = QLabel("空闲")
        self.live_badge.setObjectName("StatusBadge")
        self.live_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.live_badge.setMinimumWidth(110)

        self.live_message = QLabel("等待任务启动")
        self.live_message.setObjectName("TimelineHeadline")
        self.live_message.setWordWrap(True)

        live_top.addWidget(self.live_badge, 0)
        live_top.addWidget(self.live_message, 1)
        live_card.add_layout(live_top)

        self.video_progress = QProgressBar()
        self.video_progress.setRange(0, 100)
        self.video_progress.setValue(0)
        self.video_progress.setFormat("暂无视频")

        self.video_meta_primary = QLabel("等待页面就绪")
        self.video_meta_primary.setObjectName("TimelineSubline")
        self.video_meta_primary.setWordWrap(True)

        self.video_meta_secondary = QLabel("会话启动后将显示 keepalive、paused、ended 和 countdown。")
        self.video_meta_secondary.setObjectName("TimelineSubline")
        self.video_meta_secondary.setWordWrap(True)

        live_card.add_widget(self.video_progress)
        live_card.add_widget(self.video_meta_primary)
        live_card.add_widget(self.video_meta_secondary)
        layout.addWidget(live_card)

        logs_card = SectionCard("日志与诊断", "结构化日志支持筛选、检索、详情查看和会话信息回看。", "LOGS")

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        self.level_filter = QComboBox()
        self.level_filter.addItems(["全部", "INFO", "SUCCESS", "WARNING", "ERROR"])
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索代码、消息、建议、URL 或诊断字段")
        filter_row.addWidget(self.level_filter, 0)
        filter_row.addWidget(self.search_input, 1)
        logs_card.add_layout(filter_row)

        tabs = QTabWidget()
        tabs.addTab(self._build_structured_logs_tab(), "结构化日志")
        tabs.addTab(self._build_raw_logs_tab(), "原始日志")
        tabs.addTab(self._build_session_tab(), "会话信息")
        logs_card.add_widget(tabs, 1)
        layout.addWidget(logs_card, 1)

        self.level_filter.currentIndexChanged.connect(self._refresh_log_table)
        self.search_input.textChanged.connect(self._refresh_log_table)
        return panel

    def _build_structured_logs_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        self.log_table = QTableWidget(0, 5)
        self.log_table.setHorizontalHeaderLabels(["时间", "级别", "分类", "代码", "消息"])
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.log_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.log_table)

        self.log_detail = QPlainTextEdit()
        self.log_detail.setReadOnly(True)
        splitter.addWidget(self.log_detail)
        splitter.setSizes([420, 230])

        layout.addWidget(splitter, 1)
        self.log_table.itemSelectionChanged.connect(self._update_log_detail)
        return panel

    def _build_raw_logs_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.raw_log = QPlainTextEdit()
        self.raw_log.setReadOnly(True)
        layout.addWidget(self.raw_log)
        return panel

    def _build_session_tab(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.session_info = QPlainTextEdit()
        self.session_info.setReadOnly(True)
        layout.addWidget(self.session_info)
        return panel

    def _field_block(self, label_text: str, widget: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")
        layout.addWidget(label)
        layout.addWidget(widget)
        return wrapper

    def _path_row(self, line_edit: QLineEdit, browse_handler, detect_handler=None) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        browse_button = QPushButton("浏览")
        browse_button.setProperty("variant", "secondary")
        browse_button.clicked.connect(browse_handler)

        layout.addWidget(line_edit, 1)
        layout.addWidget(browse_button, 0)

        if detect_handler is not None:
            detect_button = QPushButton("识别")
            detect_button.setProperty("variant", "secondary")
            detect_button.clicked.connect(detect_handler)
            layout.addWidget(detect_button, 0)
        return row

    def _make_spin(self, minimum: int, maximum: int, value: int, suffix: str = "") -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def _make_double_spin(self, minimum: float, maximum: float, value: float, decimals: int) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setDecimals(decimals)
        spin.setSingleStep(0.2)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        return spin

    def _toggle_runtime_limit(self, checked: bool) -> None:
        self.max_runtime_spin.setEnabled(not checked)

    def _build_config(self) -> AutomationConfig:
        return AutomationConfig(
            url=self.url_input.text().strip(),
            browser_path=self.browser_input.text().strip(),
            user_data_dir=self.profile_input.text().strip(),
            logs_dir=self.logs_input.text().strip(),
            poll_seconds=self.poll_spin.value(),
            video_end_wait_seconds=self.video_wait_spin.value(),
            exercise_wait_seconds=self.exercise_wait_spin.value(),
            page_load_timeout_ms=self.page_timeout_spin.value(),
            next_retry_seconds=self.retry_spin.value(),
            status_log_interval_seconds=self.status_interval_spin.value(),
            headless=self.headless_checkbox.isChecked(),
            auto_return_to_target_after_login=self.auto_return_checkbox.isChecked(),
            infinite_runtime=self.infinite_runtime_checkbox.isChecked(),
            max_runtime_seconds=self.max_runtime_spin.value(),
            test_seek_to_end_after_seconds=self.test_seek_spin.value(),
            test_force_ended_after_seconds=self.test_force_spin.value(),
        )

    def _start_automation(self) -> None:
        if self.thread is not None:
            return
        self._save_settings()
        config = self._build_config()

        self.events.clear()
        self.filtered_events.clear()
        self.log_table.setRowCount(0)
        self.raw_log.clear()
        self.log_detail.clear()
        self.session_info.clear()

        self.thread = QThread(self)
        self.worker = AutomationWorker(config)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.event_emitted.connect(self._append_event)
        self.worker.status_changed.connect(self._apply_status)
        self.worker.finished.connect(self._worker_finished)
        self.thread.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.hero_message.setText("任务已启动，正在连接浏览器与页面。")

    def _stop_automation(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self.stop_button.setEnabled(False)

    def _worker_finished(self, success: bool, error_text: str) -> None:
        if not success and error_text:
            self.raw_log.appendPlainText(f"[GUI] Worker finished with error: {error_text}")
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(5000)
            self.thread.deleteLater()
            self.thread = None
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _append_event(self, event: LogEvent) -> None:
        self.events.append(event)
        self.raw_log.appendPlainText(event.to_console_line())
        self._refresh_log_table()
        self._update_session_info()

    def _refresh_log_table(self) -> None:
        level = self.level_filter.currentText()
        keyword = self.search_input.text().strip().lower()

        self.filtered_events = []
        for event in self.events:
            if level != "全部" and event.level != level:
                continue
            haystack_parts = [
                event.level,
                event.category,
                event.code,
                event.message,
                event.details,
                event.suggestion,
                json.dumps(event.data, ensure_ascii=False) if event.data else "",
            ]
            haystack = " ".join(haystack_parts).lower()
            if keyword and keyword not in haystack:
                continue
            self.filtered_events.append(event)

        self.log_table.setRowCount(len(self.filtered_events))
        for row, event in enumerate(self.filtered_events):
            values = [
                event.timestamp.strftime("%H:%M:%S"),
                event.level,
                event.category,
                event.code,
                event.message,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setForeground(QColor(LEVEL_COLORS.get(event.level, "#365c9c")))
                self.log_table.setItem(row, column, item)

        if self.filtered_events and self.log_table.currentRow() < 0:
            self.log_table.selectRow(0)
        self._update_log_detail()

    def _update_log_detail(self) -> None:
        row = self.log_table.currentRow()
        if row < 0 or row >= len(self.filtered_events):
            self.log_detail.clear()
            return

        event = self.filtered_events[row]
        lines = [
            f"时间: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"级别: {event.level}",
            f"分类: {event.category}",
            f"代码: {event.code}",
            f"消息: {event.message}",
            "",
            "详情:",
            event.details or "-",
            "",
            "建议:",
            event.suggestion or "-",
        ]
        if event.data:
            lines.extend(
                [
                    "",
                    "数据:",
                    json.dumps(event.data, ensure_ascii=False, indent=2),
                ]
            )
        self.log_detail.setPlainText("\n".join(lines))

    def _apply_status(self, status: RuntimeStatus) -> None:
        self.status = status

        stage_text = STAGE_LABELS.get(status.stage, status.stage)
        page_text = PAGE_LABELS.get(status.page_kind, status.page_kind)
        runtime_mode_text = "无限时间" if self.infinite_runtime_checkbox.isChecked() else f"限制 {self.max_runtime_spin.value()} s"

        self.status_badge.setText(stage_text)
        self.status_badge.setStyleSheet(self._status_badge_style(status.stage))
        self.live_badge.setText(stage_text)
        self.live_badge.setStyleSheet(self._status_badge_style(status.stage))

        self.hero_message.setText(status.last_message or "等待任务启动")
        self.live_message.setText(status.last_message or "等待任务启动")

        self.stage_tile.set_content(stage_text, status.last_message or "等待状态更新")
        self.page_tile.set_content(page_text, status.page_url or "等待页面识别")
        self.runtime_tile.set_content(self._format_duration(status.elapsed_seconds), runtime_mode_text)
        self.click_tile.set_content(
            f"{status.next_clicks} 次",
            f"倒计时: {status.countdown_seconds if status.countdown_seconds >= 0 else '-'}",
        )
        self.risk_tile.set_content(
            f"{status.warnings} / {status.errors}",
            status.last_error_hint or "暂无错误建议",
        )
        self.session_tile.set_content(status.session_id or "-", status.session_dir or "会话启动后自动生成")

        if status.video_duration > 0:
            percent = min(100, max(0, int((status.video_current / status.video_duration) * 100)))
            self.video_progress.setValue(percent)
            self.video_progress.setFormat(f"{percent}%")
            self.video_meta_primary.setText(
                f"视频进度: {status.video_current:.1f}s / {status.video_duration:.1f}s"
            )
            self.video_meta_secondary.setText(
                f"keepalive={status.keepalive_state} | paused={status.video_paused} | "
                f"ended={status.video_ended} | countdown={status.countdown_seconds if status.countdown_seconds >= 0 else '-'}"
            )
        else:
            self.video_progress.setValue(0)
            self.video_progress.setFormat("暂无视频")
            self.video_meta_primary.setText(status.page_url or "等待页面进入视频或习题状态")
            self.video_meta_secondary.setText(
                f"keepalive={status.keepalive_state} | page={page_text} | "
                f"countdown={status.countdown_seconds if status.countdown_seconds >= 0 else '-'}"
            )

        self._update_session_info()

    def _update_session_info(self) -> None:
        self.session_info.setPlainText(
            "\n".join(
                [
                    f"会话 ID: {self.status.session_id or '-'}",
                    f"阶段: {STAGE_LABELS.get(self.status.stage, self.status.stage)}",
                    f"页面类型: {PAGE_LABELS.get(self.status.page_kind, self.status.page_kind)}",
                    f"页面 URL: {self.status.page_url or '-'}",
                    f"页面标题: {self.status.page_title or '-'}",
                    f"最后消息: {self.status.last_message or '-'}",
                    f"最后事件码: {self.status.last_event_code or '-'}",
                    f"会话目录: {self.status.session_dir or self.logs_input.text().strip() or '-'}",
                    f"文本日志: {self.status.text_log_path or '-'}",
                    f"JSONL 日志: {self.status.jsonl_log_path or '-'}",
                    f"信息 / 告警 / 错误: {self.status.infos} / {self.status.warnings} / {self.status.errors}",
                ]
            )
        )

    def _status_badge_style(self, stage: str) -> str:
        colors = {
            "idle": "#6d7d91",
            "launching": "#4f6fa8",
            "loading": "#8b6a39",
            "running": "#2f7a58",
            "waiting_login": "#996235",
            "waiting_captcha": "#b2692d",
            "error": "#b14a48",
            "stopped": "#6d7d91",
        }
        return (
            "QLabel#StatusBadge {"
            "color: #ffffff;"
            "padding: 8px 14px;"
            "border-radius: 16px;"
            "font-weight: 700;"
            f"background-color: {colors.get(stage, '#4f6fa8')};"
            "}"
        )

    def _format_duration(self, seconds: float) -> str:
        total = int(max(0, seconds))
        minutes, sec = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes}m {sec}s"
        if minutes:
            return f"{minutes}m {sec}s"
        return f"{sec}s"

    def _browse_browser(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择浏览器", self.browser_input.text().strip(), "Executable (*.exe)")
        if path:
            self.browser_input.setText(path)

    def _browse_profile(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择用户目录", self.profile_input.text().strip())
        if path:
            self.profile_input.setText(path)

    def _browse_logs(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择日志目录", self.logs_input.text().strip())
        if path:
            self.logs_input.setText(path)

    def _detect_browser(self) -> None:
        self.browser_input.setText(find_browser_path())

    def _open_logs_dir(self) -> None:
        target = self.status.session_dir or self.logs_input.text().strip()
        if target:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(target).resolve())))

    def _open_profile_dir(self) -> None:
        target = self.profile_input.text().strip()
        if target:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(target).resolve())))

    def _load_settings(self) -> None:
        defaults = AutomationConfig()
        self.url_input.setText(self.settings.value("url", defaults.url))
        self.browser_input.setText(self.settings.value("browser_path", defaults.browser_path))
        self.profile_input.setText(self.settings.value("user_data_dir", defaults.user_data_dir))
        self.logs_input.setText(self.settings.value("logs_dir", defaults.logs_dir))
        self.poll_spin.setValue(float(self.settings.value("poll_seconds", defaults.poll_seconds)))
        self.video_wait_spin.setValue(int(self.settings.value("video_end_wait_seconds", defaults.video_end_wait_seconds)))
        self.exercise_wait_spin.setValue(int(self.settings.value("exercise_wait_seconds", defaults.exercise_wait_seconds)))
        self.retry_spin.setValue(int(self.settings.value("next_retry_seconds", defaults.next_retry_seconds)))
        self.status_interval_spin.setValue(int(self.settings.value("status_log_interval_seconds", defaults.status_log_interval_seconds)))
        self.page_timeout_spin.setValue(int(self.settings.value("page_load_timeout_ms", defaults.page_load_timeout_ms)))
        self.infinite_runtime_checkbox.setChecked(str(self.settings.value("infinite_runtime", str(defaults.infinite_runtime))).lower() == "true")
        self.max_runtime_spin.setValue(int(self.settings.value("max_runtime_seconds", defaults.max_runtime_seconds)))
        self.test_seek_spin.setValue(int(self.settings.value("test_seek_to_end_after_seconds", defaults.test_seek_to_end_after_seconds)))
        self.test_force_spin.setValue(int(self.settings.value("test_force_ended_after_seconds", defaults.test_force_ended_after_seconds)))
        self.headless_checkbox.setChecked(str(self.settings.value("headless", str(defaults.headless))).lower() == "true")
        self.auto_return_checkbox.setChecked(
            str(self.settings.value("auto_return_to_target_after_login", str(defaults.auto_return_to_target_after_login))).lower() == "true"
        )
        self._toggle_runtime_limit(self.infinite_runtime_checkbox.isChecked())

    def _save_settings(self) -> None:
        for key, value in self._build_config().to_dict().items():
            self.settings.setValue(key, value)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_settings()
        if self.worker is not None:
            self.worker.stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(3000)
        super().closeEvent(event)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
