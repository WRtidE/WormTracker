#!/usr/bin/env python3
"""WormTracker 统一入口

用法:
    python main.py                          # 启动 GUI (使用默认配置)
    python main.py --config my_config.yaml  # 使用指定配置启动
"""

import os
import sys
import argparse

from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt


def parse_args():
    parser = argparse.ArgumentParser(
        description="WormTracker — 自动化线虫计数系统"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="配置文件路径 (YAML)",
    )
    return parser.parse_args()


def _make_splash_pixmap() -> QPixmap:
    """生成启动画面 Pixmap"""
    pixmap = QPixmap(420, 220)
    pixmap.fill(QColor("#F0ECE5"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # 标题
    font_title = QFont("Arial", 18, QFont.Weight.Bold)
    painter.setFont(font_title)
    painter.setPen(QColor("#6B8BAE"))
    painter.drawText(pixmap.rect().adjusted(0, -20, 0, -20),
                     Qt.AlignmentFlag.AlignCenter, "WormTracker")
    # 副标题
    font_sub = QFont("Arial", 11)
    painter.setFont(font_sub)
    painter.setPen(QColor("#968B81"))
    painter.drawText(pixmap.rect().adjusted(0, 28, 0, 28),
                     Qt.AlignmentFlag.AlignCenter, "自动化线虫计数系统 — 正在加载模块...")
    painter.end()
    return pixmap


def main():
    args = parse_args()

    # ── 先创建 QApplication ──
    app = QApplication(sys.argv)

    # ── 立即显示启动画面 ──
    splash = QSplashScreen(_make_splash_pixmap())
    splash.show()
    app.processEvents()

    # ── 延迟加载重型模块 (cv2 / numpy / pandas / matplotlib 等) ──
    from wormtracker.config import WormTrackerConfig, load_config
    from wormtracker.ui.window import WormCounterApp

    if args.config:
        config = load_config(args.config)
        config_path = args.config
    else:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        config = WormTrackerConfig.from_yaml(config_path)

    window = WormCounterApp(config=config, config_path=config_path)
    window.show()
    splash.finish(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
