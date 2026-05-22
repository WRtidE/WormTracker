#!/usr/bin/env python3
"""WormTracker 统一入口

用法:
    python main.py                          # 启动 GUI (使用默认配置)
    python main.py --config my_config.yaml  # 使用指定配置启动
"""

import sys
import argparse

from PyQt6.QtWidgets import QApplication

from wormtracker.config import WormTrackerConfig, load_config
from wormtracker.ui.window import WormCounterApp


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


def main():
    args = parse_args()

    if args.config:
        config = load_config(args.config)
    else:
        config = WormTrackerConfig()

    app = QApplication(sys.argv)
    window = WormCounterApp(config=config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
