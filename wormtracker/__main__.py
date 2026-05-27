"""python -m wormtracker 入口"""

import sys

from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt


def _make_splash_pixmap() -> QPixmap:
    """生成启动画面 Pixmap"""
    pixmap = QPixmap(420, 220)
    pixmap.fill(QColor("#F0ECE5"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font_title = QFont("Arial", 18, QFont.Weight.Bold)
    painter.setFont(font_title)
    painter.setPen(QColor("#6B8BAE"))
    painter.drawText(pixmap.rect().adjusted(0, -20, 0, -20),
                     Qt.AlignmentFlag.AlignCenter, "WormTracker")
    font_sub = QFont("Arial", 11)
    painter.setFont(font_sub)
    painter.setPen(QColor("#968B81"))
    painter.drawText(pixmap.rect().adjusted(0, 28, 0, 28),
                     Qt.AlignmentFlag.AlignCenter, "自动化线虫计数系统 — 正在加载模块...")
    painter.end()
    return pixmap


def main():
    app = QApplication(sys.argv)

    splash = QSplashScreen(_make_splash_pixmap())
    splash.show()
    app.processEvents()

    # 延迟加载重型模块
    from wormtracker.ui.window import WormCounterApp

    window = WormCounterApp()
    window.show()
    splash.finish(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
