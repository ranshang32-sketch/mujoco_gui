"""PySide6 主窗口，只处理界面事件和数据显示。"""

from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from render_widget import RenderWidget
from simulation import SimulationEngine


class MainWindow(QMainWindow):
    DISPLAY_INTERVAL_MS = 16

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MuJoCo 最小独立 GUI")
        self.resize(1100, 700)

        self.engine = SimulationEngine()
        self.is_running = False
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.setInterval(self.DISPLAY_INTERVAL_MS)
        self.timer.timeout.connect(self._on_timer)
        self.timer.start()

        example = Path(__file__).parent / "models" / "example.xml"
        self._load_model(example)

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QHBoxLayout(central)
        self.setCentralWidget(central)

        self.render_widget = RenderWidget(self.engine)
        root_layout.addWidget(self.render_widget, stretch=1)

        panel = QWidget()
        panel.setFixedWidth(330)
        panel_layout = QVBoxLayout(panel)
        root_layout.addWidget(panel)

        model_group = QGroupBox("模型")
        model_layout = QVBoxLayout(model_group)
        self.model_label = QLabel("尚未加载")
        self.model_label.setWordWrap(True)
        load_button = QPushButton("加载 MuJoCo XML…")
        load_button.clicked.connect(self._choose_model)
        model_layout.addWidget(self.model_label)
        model_layout.addWidget(load_button)
        panel_layout.addWidget(model_group)

        control_group = QGroupBox("仿真控制")
        control_layout = QVBoxLayout(control_group)
        button_row = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._toggle_running)
        reset_button = QPushButton("Reset")
        reset_button.clicked.connect(self._reset)
        button_row.addWidget(self.start_button)
        button_row.addWidget(reset_button)
        control_layout.addLayout(button_row)

        target_form = QFormLayout()
        self.target_input = QDoubleSpinBox()
        self.target_input.setRange(-1000.0, 1000.0)
        self.target_input.setDecimals(4)
        self.target_input.setSingleStep(0.1)
        apply_button = QPushButton("Apply Target")
        apply_button.clicked.connect(self._apply_target)
        target_form.addRow("目标值：", self.target_input)
        target_form.addRow("", apply_button)
        control_layout.addLayout(target_form)
        panel_layout.addWidget(control_group)

        state_group = QGroupBox("MuJoCo 状态")
        state_layout = QFormLayout(state_group)
        self.time_label = QLabel("0.0000 s")
        self.qpos_text = self._make_state_box()
        self.qvel_text = self._make_state_box()
        self.ctrl_text = self._make_state_box()
        state_layout.addRow("data.time：", self.time_label)
        state_layout.addRow("data.qpos：", self.qpos_text)
        state_layout.addRow("data.qvel：", self.qvel_text)
        state_layout.addRow("data.ctrl：", self.ctrl_text)
        panel_layout.addWidget(state_group, stretch=1)

        hint = QLabel("左键拖动：旋转视角\n鼠标滚轮：缩放")
        hint.setStyleSheet("color: #666;")
        panel_layout.addWidget(hint)

    @staticmethod
    def _make_state_box() -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setMaximumHeight(76)
        return box

    def _choose_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 MuJoCo XML 模型",
            str(Path.home()),
            "MuJoCo XML (*.xml *.mjcf);;所有文件 (*)",
        )
        if path:
            self._load_model(Path(path))

    def _load_model(self, path: Path) -> None:
        try:
            self.is_running = False
            self.start_button.setText("Start")
            self.engine.load_model(path)
            self.target_input.setValue(self.engine.target)
            self.model_label.setText(str(path))
            self._refresh_state()
            self.render_widget.refresh_frame()
        except Exception as error:
            QMessageBox.critical(self, "模型加载失败", str(error))

    def _toggle_running(self) -> None:
        if not self.engine.is_loaded:
            return
        self.is_running = not self.is_running
        self.start_button.setText("Pause" if self.is_running else "Start")

    def _reset(self) -> None:
        self.is_running = False
        self.start_button.setText("Start")
        self.engine.reset()
        self.target_input.setValue(self.engine.target)
        self._refresh_state()
        self.render_widget.refresh_frame()

    def _apply_target(self) -> None:
        # GUI -> MuJoCo 的入口：界面只把目标交给 SimulationEngine。
        self.engine.set_target(self.target_input.value())

    def _on_timer(self) -> None:
        if self.is_running:
            self.engine.step_for(self.DISPLAY_INTERVAL_MS / 1000.0)
        self._refresh_state()
        self.render_widget.refresh_frame()

    def _refresh_state(self) -> None:
        # MuJoCo -> GUI 的入口：界面只读取 get_state() 返回的副本。
        state = self.engine.get_state()
        self.time_label.setText(f"{state.time:.4f} s")
        self.qpos_text.setPlainText(self._format_array(state.qpos))
        self.qvel_text.setPlainText(self._format_array(state.qvel))
        self.ctrl_text.setPlainText(self._format_array(state.ctrl))

    @staticmethod
    def _format_array(values: np.ndarray) -> str:
        return np.array2string(values, precision=4, suppress_small=True, max_line_width=36)

    def closeEvent(self, event) -> None:
        self.engine.close()
        super().closeEvent(event)
