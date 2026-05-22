"""WormTracker 全局 QSS 样式表"""

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
"""
