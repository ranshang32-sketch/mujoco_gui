"""程序入口：运行这个文件即可启动 GUI。"""

import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MuJoCo Minimal GUI")
    _set_windows_chinese_font(app)

    window = MainWindow()
    window.show()
    return app.exec()


def _set_windows_chinese_font(app: QApplication) -> None:
    """显式加载微软雅黑，避免部分独立Python环境无法发现中文字体。"""
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if not font_path.is_file():
        return
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    families = QFontDatabase.applicationFontFamilies(font_id)
    if families:
        app.setFont(QFont(families[0], 9))


if __name__ == "__main__":
    raise SystemExit(main())
