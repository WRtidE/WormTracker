"""WormTracker 全局 QSS 样式表 — 暗色 & 浅色主题"""

APP_STYLESHEET = """
QMainWindow { background-color: #1e1e2e; }
QLabel { color: #cdd6f4; font-family: -apple-system, 'Segoe UI', Arial, sans-serif; }
QGroupBox {
    border: 2px solid #313244; border-radius: 8px;
    margin-top: 15px; font-size: 14px; font-weight: bold; color: #a6adc8;
}
QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 5px; }
QPushButton {
    background-color: #313244; color: #cdd6f4;
    border: none; border-radius: 6px; padding: 10px;
    font-weight: bold; font-size: 14px; outline: none;
}
QPushButton:hover { background-color: #45475a; }
QPushButton:pressed { background-color: #585b70; }
QPushButton:disabled {
    background-color: #181825; color: #585b70; border: 1px solid #313244;
}
QSpinBox, QDoubleSpinBox {
    background-color: #11111b; color: #a6e3a1; font-weight: bold;
    border: 1px solid #45475a; border-radius: 4px; padding: 4px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #313244; width: 20px;
}
QComboBox {
    background-color: #11111b; color: #a6e3a1; font-weight: bold;
    border: 1px solid #45475a; border-radius: 4px; padding: 4px 8px;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #11111b; color: #cdd6f4;
    selection-background-color: #45475a; border: 1px solid #45475a;
}
QTableWidget {
    background-color: #181825; color: #cdd6f4;
    gridline-color: #313244; border: 1px solid #313244;
    border-radius: 6px; selection-background-color: #45475a;
}
QHeaderView::section {
    background-color: #1e1e2e; color: #a6adc8;
    padding: 5px; border: 1px solid #313244; font-weight: bold;
}
QStatusBar { background-color: #11111b; color: #a6adc8; font-weight: bold; }
QTabWidget::pane {
    border: 2px solid #313244; border-radius: 8px; background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #11111b; color: #585b70;
    padding: 10px 20px; font-weight: bold; font-size: 14px;
    border-top-left-radius: 8px; border-top-right-radius: 8px;
    margin-right: 4px; border: 2px solid transparent;
}
QTabBar::tab:selected {
    background-color: #313244; color: #a6e3a1;
    border-top: 2px solid #a6e3a1;
    border-left: 2px solid #313244; border-right: 2px solid #313244;
}
QTabBar::tab:hover:!selected { background-color: #181825; color: #cdd6f4; }
QMessageBox {
    background-color: #ffffff; border: 2px solid #d1d5db;
}
QMessageBox QLabel { color: #000000; font-size: 14px; font-weight: bold; }
QMessageBox QPushButton {
    background-color: #f3f4f6; color: #000000;
    border: 1px solid #d1d5db; border-radius: 6px;
    padding: 6px 20px; font-weight: bold; min-width: 60px;
}
QMessageBox QPushButton:hover { background-color: #e5e7eb; }
QMessageBox QPushButton:pressed { background-color: #d1d5db; }
QSlider::groove:horizontal {
    border: 1px solid #45475a; border-radius: 4px;
    background-color: #11111b; height: 8px;
}
QSlider::sub-page:horizontal {
    background-color: #a6e3a1; border-radius: 4px;
}
QSlider::add-page:horizontal {
    background-color: #313244; border-radius: 4px;
}
QSlider::handle:horizontal {
    background-color: #a6e3a1; border: 2px solid #585b70;
    width: 16px; margin: -5px 0; border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background-color: #94e2d5; border-color: #a6e3a1;
}
QSlider::handle:horizontal:disabled {
    background-color: #585b70; border-color: #313244;
}
"""

APP_STYLESHEET_LIGHT = """
QMainWindow { background-color: #F0ECE5; }
QLabel { color: #5C534A; font-family: -apple-system, 'Segoe UI', Arial, sans-serif; }
QGroupBox {
    border: 2px solid #D9D1C5; border-radius: 8px;
    margin-top: 15px; font-size: 14px; font-weight: bold; color: #968B81;
}
QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 5px; }
QPushButton {
    background-color: #D9D1C5; color: #5C534A;
    border: none; border-radius: 6px; padding: 10px;
    font-weight: bold; font-size: 14px; outline: none;
}
QPushButton:hover { background-color: #CCC3B5; }
QPushButton:pressed { background-color: #BEB4A5; }
QPushButton:disabled {
    background-color: #EDE8E0; color: #B8AFA6; border: 1px solid #D9D1C5;
}
QSpinBox, QDoubleSpinBox {
    background-color: #E8E3DA; color: #6B9F6E; font-weight: bold;
    border: 1px solid #CCC3B5; border-radius: 4px; padding: 4px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #D9D1C5; width: 20px;
}
QComboBox {
    background-color: #E8E3DA; color: #6B9F6E; font-weight: bold;
    border: 1px solid #CCC3B5; border-radius: 4px; padding: 4px 8px;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #E8E3DA; color: #5C534A;
    selection-background-color: #CCC3B5; border: 1px solid #CCC3B5;
}
QTableWidget {
    background-color: #EDE8E0; color: #5C534A;
    gridline-color: #D9D1C5; border: 1px solid #D9D1C5;
    border-radius: 6px; selection-background-color: #CCC3B5;
}
QHeaderView::section {
    background-color: #F0ECE5; color: #968B81;
    padding: 5px; border: 1px solid #D9D1C5; font-weight: bold;
}
QStatusBar { background-color: #E8E3DA; color: #968B81; font-weight: bold; }
QTabWidget::pane {
    border: 2px solid #D9D1C5; border-radius: 8px; background-color: #F0ECE5;
}
QTabBar::tab {
    background-color: #E8E3DA; color: #B8AFA6;
    padding: 10px 20px; font-weight: bold; font-size: 14px;
    border-top-left-radius: 8px; border-top-right-radius: 8px;
    margin-right: 4px; border: 2px solid transparent;
}
QTabBar::tab:selected {
    background-color: #D9D1C5; color: #6B9F6E;
    border-top: 2px solid #6B9F6E;
    border-left: 2px solid #D9D1C5; border-right: 2px solid #D9D1C5;
}
QTabBar::tab:hover:!selected { background-color: #EDE8E0; color: #5C534A; }
QMessageBox {
    background-color: #ffffff; border: 2px solid #d1d5db;
}
QMessageBox QLabel { color: #000000; font-size: 14px; font-weight: bold; }
QMessageBox QPushButton {
    background-color: #f3f4f6; color: #000000;
    border: 1px solid #d1d5db; border-radius: 6px;
    padding: 6px 20px; font-weight: bold; min-width: 60px;
}
QMessageBox QPushButton:hover { background-color: #e5e7eb; }
QMessageBox QPushButton:pressed { background-color: #d1d5db; }
QSlider::groove:horizontal {
    border: 1px solid #CCC3B5; border-radius: 4px;
    background-color: #E8E3DA; height: 8px;
}
QSlider::sub-page:horizontal {
    background-color: #6B9F6E; border-radius: 4px;
}
QSlider::add-page:horizontal {
    background-color: #D9D1C5; border-radius: 4px;
}
QSlider::handle:horizontal {
    background-color: #6B9F6E; border: 2px solid #BEB4A5;
    width: 16px; margin: -5px 0; border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background-color: #5A8F5E; border-color: #6B9F6E;
}
QSlider::handle:horizontal:disabled {
    background-color: #B8AFA6; border-color: #D9D1C5;
}
"""
