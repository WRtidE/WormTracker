"""python -m wormtracker 入口"""

import sys
from wormtracker.ui.window import WormCounterApp
from PyQt6.QtWidgets import QApplication


def main():
    app = QApplication(sys.argv)
    window = WormCounterApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
