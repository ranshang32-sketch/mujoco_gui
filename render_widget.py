"""把 MuJoCo 渲染得到的 NumPy 图像显示在 PySide6 窗口中。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

from simulation import SimulationEngine


class RenderWidget(QWidget):
    def __init__(self, engine: SimulationEngine, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self._image = QImage()
        self._last_mouse_pos = None
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background: #20242a;")

    def refresh_frame(self) -> None:
        frame = self.engine.render(self.width(), self.height())
        if frame is None:
            return
        height, width, channels = frame.shape
        bytes_per_line = width * channels
        # copy() 让 QImage 拥有自己的内存，不依赖下一帧会被覆盖的 NumPy 数组。
        self._image = QImage(
            frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        ).copy()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._image.isNull():
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "正在准备 MuJoCo 画面…")
            return
        painter.drawImage(self.rect(), self._image)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse_pos = event.position()

    def mouseMoveEvent(self, event) -> None:
        if self._last_mouse_pos is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        current = event.position()
        delta = current - self._last_mouse_pos
        self._last_mouse_pos = current
        self.engine.rotate_camera(delta.x(), delta.y())
        self.refresh_frame()

    def mouseReleaseEvent(self, event) -> None:
        self._last_mouse_pos = None

    def wheelEvent(self, event) -> None:
        self.engine.zoom_camera(event.angleDelta().y() / 120.0)
        self.refresh_frame()
