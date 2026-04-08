APP_STYLE = """
QWidget {
    color: #172336;
    font-family: "Segoe UI", "Microsoft YaHei UI";
    font-size: 13px;
}
QMainWindow, QWidget#AppRoot {
    background: #edf2f7;
}
QLabel {
    background: transparent;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QFrame#HeroPanel {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #17324b, stop:1 #274a70);
    border: 1px solid #17324b;
    border-radius: 22px;
}
QFrame#SectionCard, QFrame#StatTile {
    background: #ffffff;
    border: 1px solid #d7dee9;
    border-radius: 18px;
}
QFrame#StatTile {
    background: #fbfcfe;
}
QLabel#HeroEyebrow {
    color: #a9bfd5;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#HeroTitle {
    color: #f7fbff;
    font-size: 28px;
    font-weight: 700;
}
QLabel#HeroSubtitle, QLabel#HeroStatusText {
    color: #d5e0eb;
    font-size: 13px;
}
QLabel#SectionEyebrow {
    color: #59708b;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#SectionTitle {
    color: #172336;
    font-size: 16px;
    font-weight: 700;
}
QLabel#SectionHint {
    color: #68778b;
    font-size: 12px;
}
QLabel#FieldLabel {
    color: #4e6178;
    font-size: 12px;
    font-weight: 600;
}
QLabel#StatLabel {
    color: #66788e;
    font-size: 12px;
    font-weight: 600;
}
QLabel#StatValue {
    color: #172336;
    font-size: 24px;
    font-weight: 700;
}
QLabel#StatHint, QLabel#TimelineSubline {
    color: #68778b;
    font-size: 12px;
}
QLabel#TimelineHeadline {
    color: #1e2d42;
    font-size: 14px;
    font-weight: 600;
}
QLabel#StatusBadge {
    color: #ffffff;
    padding: 8px 14px;
    border-radius: 16px;
    font-weight: 700;
    background: #4f6fa8;
}
QPushButton {
    background: #2c5cc8;
    color: #ffffff;
    border: none;
    border-radius: 12px;
    padding: 10px 16px;
    font-weight: 700;
}
QPushButton:hover {
    background: #234fb4;
}
QPushButton:pressed {
    background: #1b4299;
}
QPushButton:disabled {
    background: #c8d1de;
    color: #f7f9fb;
}
QPushButton[variant="secondary"] {
    background: #eef3f9;
    color: #234c91;
    border: 1px solid #d5deea;
}
QPushButton[variant="secondary"]:hover {
    background: #e6edf7;
}
QPushButton[variant="secondary"]:pressed {
    background: #dce6f4;
}
QLineEdit,
QSpinBox,
QDoubleSpinBox,
QComboBox,
QPlainTextEdit,
QTableWidget,
QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #d7dee9;
    border-radius: 12px;
}
QLineEdit,
QSpinBox,
QDoubleSpinBox,
QComboBox,
QPlainTextEdit {
    padding: 9px 11px;
}
QLineEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QComboBox:focus,
QPlainTextEdit:focus {
    border: 1px solid #2c5cc8;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    width: 10px;
    height: 10px;
}
QCheckBox {
    color: #213246;
    spacing: 8px;
    font-weight: 600;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 6px;
    border: 1px solid #b9c6d7;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    border: 1px solid #2c5cc8;
    background: #2c5cc8;
}
QHeaderView::section {
    background: #f4f7fb;
    color: #445770;
    border: none;
    border-bottom: 1px solid #d7dee9;
    padding: 10px;
    font-weight: 700;
}
QTableWidget {
    gridline-color: #edf2f7;
    selection-background-color: #dfe8f8;
    selection-color: #172336;
}
QTableWidget::item {
    padding: 6px;
}
QTabBar::tab {
    background: #e9eef5;
    color: #5a6d84;
    border: none;
    padding: 10px 16px;
    margin-right: 6px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-weight: 700;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #1e2d42;
}
QProgressBar {
    border: none;
    border-radius: 10px;
    background: #e6ebf3;
    height: 18px;
    text-align: center;
    color: #172336;
}
QProgressBar::chunk {
    border-radius: 10px;
    background: #2c5cc8;
}
QSplitter::handle {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px 0;
}
QScrollBar::handle:vertical {
    background: #c5cfdd;
    border-radius: 5px;
    min-height: 28px;
}
"""
