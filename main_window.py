"""平台工作台主窗口。

界面只负责发出运行命令和显示状态；实际计时与物理步进由SimulationEngine负责。
"""

from html import escape
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from render_widget import RenderWidget
from simulation import SimulationEngine


class MainWindow(QMainWindow):
    DISPLAY_INTERVAL_MS = 16
    ITEM_KIND_ROLE = int(Qt.ItemDataRole.UserRole)
    ITEM_ID_ROLE = ITEM_KIND_ROLE + 1

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RobotSim Studio · MuJoCo工作台")
        self.resize(1400, 840)
        self.setMinimumSize(1050, 680)

        self.engine = SimulationEngine()
        self.is_running = False
        self.selected_kind = "model"
        self.selected_id = -1

        self._build_ui()
        self._apply_style()

        self.timer = QTimer(self)
        self.timer.setInterval(self.DISPLAY_INTERVAL_MS)
        self.timer.timeout.connect(self._on_timer)
        self.timer.start()

        example = Path(__file__).parent / "models" / "example.xml"
        self._load_model(example)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("workspace")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(central)

        root_layout.addWidget(self._build_top_bar())

        body = QFrame()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._build_navigation())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_model_panel())
        splitter.addWidget(self._build_center_workspace())
        splitter.addWidget(self._build_inspector_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([235, 850, 280])
        body_layout.addWidget(splitter, stretch=1)
        root_layout.addWidget(body, stretch=1)

        self._build_status_bar()

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        mark = QLabel("M")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand = QLabel("RobotSim Studio")
        brand.setObjectName("brandText")
        layout.addWidget(mark)
        layout.addWidget(brand)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setObjectName("separator")
        layout.addWidget(separator)

        self.current_model_label = QLabel("尚未加载模型")
        self.current_model_label.setObjectName("currentModel")
        layout.addWidget(self.current_model_label)
        layout.addStretch()

        load_button = QPushButton("加载模型…")
        load_button.clicked.connect(self._choose_model)
        self.start_button = QPushButton("开始")
        self.start_button.setProperty("role", "primary")
        self.start_button.clicked.connect(self._toggle_running)
        reset_button = QPushButton("重置")
        reset_button.clicked.connect(self._reset)
        layout.addWidget(load_button)
        layout.addWidget(self.start_button)
        layout.addWidget(reset_button)
        return bar

    def _build_navigation(self) -> QWidget:
        navigation = QFrame()
        navigation.setObjectName("navigation")
        navigation.setFixedWidth(66)
        layout = QVBoxLayout(navigation)
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(6)

        entries = [
            ("M\n模型", True, "查看模型、关节和执行器"),
            ("S\n仿真", False, "后续迭代开放"),
            ("C\n控制", False, "后续迭代开放"),
            ("R\n结果", False, "后续迭代开放"),
        ]
        for text, active, tooltip in entries:
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setProperty("active", active)
            button.setEnabled(active)
            button.setToolTip(tooltip)
            layout.addWidget(button)
        layout.addStretch()
        return navigation

    def _build_model_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("sidePanel")
        panel.setMinimumWidth(190)
        panel.setMaximumWidth(330)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("模型工作区")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.model_tree = QTreeWidget()
        self.model_tree.setObjectName("modelTree")
        self.model_tree.setHeaderHidden(True)
        self.model_tree.setIndentation(18)
        self.model_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.model_tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        layout.addWidget(self.model_tree, stretch=1)

        self.model_summary_label = QLabel("尚未加载模型")
        self.model_summary_label.setObjectName("modelSummary")
        self.model_summary_label.setWordWrap(True)
        layout.addWidget(self.model_summary_label)
        return panel

    def _build_center_workspace(self) -> QWidget:
        center = QFrame()
        center.setObjectName("centerWorkspace")
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("viewportHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        heading = QLabel("3D 仿真")
        heading.setObjectName("sectionHeading")
        hint = QLabel("左键拖动旋转 · 鼠标滚轮缩放")
        hint.setObjectName("mutedText")
        header_layout.addWidget(heading)
        header_layout.addWidget(hint)
        header_layout.addStretch()
        layout.addWidget(header)

        self.render_widget = RenderWidget(self.engine)
        layout.addWidget(self.render_widget, stretch=1)

        timeline = QFrame()
        timeline.setObjectName("timelineBar")
        timeline_layout = QHBoxLayout(timeline)
        timeline_layout.setContentsMargins(12, 7, 12, 7)
        timeline_layout.setSpacing(10)
        timeline_layout.addWidget(QLabel("仿真时间"))
        self.time_label = QLabel("0.0000 s")
        self.time_label.setObjectName("timeValue")
        timeline_layout.addWidget(self.time_label)
        timeline_layout.addStretch()
        timestep_caption = QLabel("模型步长")
        timestep_caption.setObjectName("mutedText")
        self.timestep_label = QLabel("- s")
        timeline_layout.addWidget(timestep_caption)
        timeline_layout.addWidget(self.timestep_label)
        step_caption = QLabel("物理步数")
        step_caption.setObjectName("mutedText")
        self.step_count_label = QLabel("0")
        self.step_count_label.setObjectName("timeValue")
        timeline_layout.addWidget(step_caption)
        timeline_layout.addWidget(self.step_count_label)
        speed_caption = QLabel("仿真速度")
        speed_caption.setObjectName("mutedText")
        self.speed_combo = QComboBox()
        self.speed_combo.setToolTip("仿真时间相对于现实时间的速度")
        for label, value in (("0.25×", 0.25), ("0.5×", 0.5), ("1×", 1.0), ("2×", 2.0)):
            self.speed_combo.addItem(label, value)
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.currentIndexChanged.connect(self._change_speed)
        timeline_layout.addWidget(speed_caption)
        timeline_layout.addWidget(self.speed_combo)
        layout.addWidget(timeline)

        state_strip = QFrame()
        state_strip.setObjectName("stateStrip")
        state_layout = QHBoxLayout(state_strip)
        state_layout.setContentsMargins(10, 8, 10, 10)
        state_layout.setSpacing(8)
        self.qpos_text = self._make_state_card("qpos")
        self.qvel_text = self._make_state_card("qvel")
        self.ctrl_text = self._make_state_card("ctrl")
        for card, _ in (self.qpos_text, self.qvel_text, self.ctrl_text):
            state_layout.addWidget(card)
        layout.addWidget(state_strip)
        return center

    @staticmethod
    def _make_state_card(title: str) -> tuple[QWidget, QLineEdit]:
        card = QFrame()
        card.setObjectName("stateCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(3)
        caption = QLabel(title)
        caption.setObjectName("stateCaption")
        value = QLineEdit("[]")
        value.setObjectName("stateValue")
        value.setReadOnly(True)
        value.setFrame(False)
        layout.addWidget(caption)
        layout.addWidget(value)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return card, value

    def _build_inspector_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("sidePanel")
        panel.setMinimumWidth(235)
        panel.setMaximumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("属性检查器")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.object_name_label = QLabel("未选择对象")
        self.object_name_label.setObjectName("objectName")
        self.object_name_label.setWordWrap(True)
        layout.addWidget(self.object_name_label)

        self.property_label = QLabel("请从左侧模型树选择模型、关节或执行器。")
        self.property_label.setObjectName("propertyText")
        self.property_label.setWordWrap(True)
        self.property_label.setTextFormat(Qt.TextFormat.RichText)
        self.property_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.property_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("separator")
        layout.addWidget(separator)

        control_title = QLabel("V1 示例控制")
        control_title.setObjectName("subTitle")
        layout.addWidget(control_title)
        control_note = QLabel("该目标仍控制第一个执行器和第一个自由度。本轮不修改控制器。")
        control_note.setObjectName("controlNote")
        control_note.setWordWrap(True)
        layout.addWidget(control_note)

        control_box = QFrame()
        control_box.setObjectName("controlBox")
        control_layout = QVBoxLayout(control_box)
        control_layout.setContentsMargins(12, 8, 12, 12)
        target_caption = QLabel("目标值")
        target_caption.setObjectName("mutedText")
        self.target_input = QDoubleSpinBox()
        self.target_input.setRange(-1000.0, 1000.0)
        self.target_input.setDecimals(4)
        self.target_input.setSingleStep(0.1)
        apply_button = QPushButton("应用目标")
        apply_button.setProperty("role", "primary")
        apply_button.clicked.connect(self._apply_target)
        control_layout.addWidget(target_caption)
        control_layout.addWidget(self.target_input)
        control_layout.addWidget(apply_button)
        layout.addWidget(control_box)
        layout.addStretch()
        return panel

    def _build_status_bar(self) -> None:
        status = self.statusBar()
        status.setObjectName("statusBar")
        self.run_status_label = QLabel("● 已暂停")
        self.run_status_label.setObjectName("runStatus")
        self.file_status_label = QLabel("未加载模型")
        self.message_status_label = QLabel("无错误")
        status.addWidget(self.run_status_label)
        status.addPermanentWidget(self.file_status_label, 1)
        status.addPermanentWidget(self.message_status_label)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#workspace { background: #eef1f5; color: #1d2632; }
            QFrame#topBar { background: #ffffff; border-bottom: 1px solid #dce2e9; }
            QLabel#brandMark { background: #1669b2; color: white; border-radius: 6px;
                               min-width: 28px; min-height: 28px; max-width: 28px; max-height: 28px;
                               font-weight: 700; }
            QLabel#brandText { font-size: 15px; font-weight: 600; }
            QLabel#currentModel { color: #4f5e6f; }
            QFrame#navigation { background: #ffffff; border-right: 1px solid #dce2e9; }
            QPushButton#navButton { border: 0; border-radius: 6px; background: transparent;
                                    min-height: 48px; color: #7b8794; padding: 5px 2px; }
            QPushButton#navButton[active="true"] { background: #e6f1fb; color: #1264a8; }
            QPushButton#navButton:disabled { color: #aeb7c2; }
            QFrame#sidePanel { background: #ffffff; }
            QLabel#panelTitle { min-height: 42px; padding: 0 12px; font-weight: 600;
                                border-bottom: 1px solid #e1e6ec; }
            QTreeWidget#modelTree { border: 0; background: #ffffff; padding: 6px;
                                    selection-background-color: #e4effa;
                                    selection-color: #105f9f; outline: 0; }
            QLabel#modelSummary { border-top: 1px solid #e1e6ec; padding: 10px 12px;
                                  color: #667384; background: #fafbfd; }
            QFrame#centerWorkspace { background: #20262e; }
            QFrame#viewportHeader, QFrame#timelineBar, QFrame#stateStrip {
                background: #ffffff; border-bottom: 1px solid #dce2e9;
            }
            QFrame#viewportHeader { min-height: 42px; }
            QLabel#sectionHeading { font-weight: 600; }
            QLabel#mutedText, QLabel#stateCaption { color: #778391; }
            QLabel#timeValue { font-family: Consolas, monospace; font-weight: 600; color: #1264a8; }
            QFrame#stateCard { background: #f7f9fb; border: 1px solid #dfe5eb; border-radius: 6px; }
            QLineEdit#stateValue { background: transparent; color: #283442;
                                   font-family: Consolas, monospace; padding: 0; }
            QLabel#objectName { padding: 14px 12px 8px 12px; font-size: 15px; font-weight: 600; }
            QLabel#propertyText { padding: 0 12px 14px 12px; color: #536171; }
            QLabel#subTitle { padding: 14px 12px 4px 12px; font-weight: 600; }
            QLabel#controlNote { padding: 0 12px 8px 12px; color: #7a8695; }
            QFrame#controlBox { background: #ffffff; }
            QFrame#separator { color: #dce2e9; }
            QPushButton { background: #ffffff; border: 1px solid #cfd7e0; border-radius: 5px;
                          padding: 7px 12px; }
            QPushButton:hover { background: #f3f6f9; border-color: #aeb9c5; }
            QPushButton[role="primary"] { background: #1669b2; color: white; border-color: #1669b2; }
            QPushButton[role="primary"]:hover { background: #0f5d9f; }
            QDoubleSpinBox, QComboBox { background: #ffffff; border: 1px solid #cfd7e0;
                                       border-radius: 5px; padding: 6px; }
            QSplitter::handle { background: #dce2e9; width: 1px; }
            QStatusBar#statusBar { background: #ffffff; border-top: 1px solid #dce2e9; color: #687586; }
            QLabel#runStatus { color: #2e7d50; padding-right: 14px; }
            """
        )

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
            self.engine.pause_realtime()
            self._update_running_ui()
            self.engine.load_model(path)
            self.target_input.setValue(self.engine.target)
            self._populate_model_tree()
            self._refresh_state()
            self.render_widget.refresh_frame()
            self.file_status_label.setText(path.name)
            self.message_status_label.setText("模型加载成功")
        except Exception as error:
            self.message_status_label.setText("模型加载失败")
            QMessageBox.critical(self, "模型加载失败", str(error))

    def _populate_model_tree(self) -> None:
        info = self.engine.get_model_info()
        self.model_tree.clear()

        root = QTreeWidgetItem([str(info.get("name", "未命名模型"))])
        root.setData(0, self.ITEM_KIND_ROLE, "model")
        root.setData(0, self.ITEM_ID_ROLE, -1)
        self.model_tree.addTopLevelItem(root)

        joints = self.engine.get_joint_items()
        joint_group = QTreeWidgetItem([f"关节 ({len(joints)})"])
        joint_group.setFlags(joint_group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        root.addChild(joint_group)
        first_selectable = None
        for joint in joints:
            item = QTreeWidgetItem([f"{joint['name']}   · {joint['type']}"])
            item.setData(0, self.ITEM_KIND_ROLE, "joint")
            item.setData(0, self.ITEM_ID_ROLE, int(joint["id"]))
            joint_group.addChild(item)
            first_selectable = first_selectable or item

        actuators = self.engine.get_actuator_items()
        actuator_group = QTreeWidgetItem([f"执行器 ({len(actuators)})"])
        actuator_group.setFlags(actuator_group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        root.addChild(actuator_group)
        for actuator in actuators:
            item = QTreeWidgetItem([str(actuator["name"])])
            item.setData(0, self.ITEM_KIND_ROLE, "actuator")
            item.setData(0, self.ITEM_ID_ROLE, int(actuator["id"]))
            actuator_group.addChild(item)

        root.setExpanded(True)
        joint_group.setExpanded(True)
        actuator_group.setExpanded(True)
        self.model_tree.setCurrentItem(first_selectable or root)

        self.current_model_label.setText(
            f"{info.get('name', '模型')}  ·  nq {info.get('nq', 0)}  nv {info.get('nv', 0)}  nu {info.get('nu', 0)}"
        )
        self.model_summary_label.setText(
            f"nq / nv / nu：{info.get('nq', 0)} / {info.get('nv', 0)} / {info.get('nu', 0)}\n"
            f"关节：{info.get('joints', 0)}   Timestep：{info.get('timestep', 0):.6f} s"
        )
        self.timestep_label.setText(f"{float(info.get('timestep', 0)):.6f} s")

    def _on_tree_selection_changed(self) -> None:
        selected = self.model_tree.selectedItems()
        if not selected:
            return
        item = selected[0]
        kind = item.data(0, self.ITEM_KIND_ROLE)
        if not kind:
            return
        self.selected_kind = str(kind)
        self.selected_id = int(item.data(0, self.ITEM_ID_ROLE) or 0)
        self._refresh_inspector()

    def _refresh_inspector(self) -> None:
        if not self.engine.is_loaded:
            return
        if self.selected_kind == "joint":
            details = self.engine.get_joint_details(self.selected_id)
            self.object_name_label.setText(str(details.get("name", "关节")))
            rows = [
                ("对象", f"Joint {details.get('id', '-') }"),
                ("类型", details.get("type", "-")),
                ("当前位置", self._format_array(details.get("qpos", np.array([])))),
                ("当前速度", self._format_array(details.get("qvel", np.array([])))),
                ("对应执行器", details.get("actuator", "无")),
            ]
            if details.get("limited"):
                rows.append(("关节范围", self._format_array(details.get("range", np.array([])))))
        elif self.selected_kind == "actuator":
            details = self.engine.get_actuator_details(self.selected_id)
            self.object_name_label.setText(str(details.get("name", "执行器")))
            rows = [
                ("对象", f"Actuator {details.get('id', '-') }"),
                ("作用对象", details.get("target", "-")),
                ("当前控制量", f"{float(details.get('ctrl', 0.0)):.6f}"),
            ]
            if details.get("limited"):
                rows.append(("控制范围", self._format_array(details.get("range", np.array([])))))
        else:
            details = self.engine.get_model_info()
            self.object_name_label.setText(str(details.get("name", "模型")))
            rows = [
                ("nq", details.get("nq", 0)),
                ("nv", details.get("nv", 0)),
                ("nu", details.get("nu", 0)),
                ("关节数", details.get("joints", 0)),
                ("Timestep", f"{float(details.get('timestep', 0)):.6f} s"),
            ]
        self.property_label.setText(self._property_table(rows))

    @staticmethod
    def _property_table(rows: list[tuple[str, object]]) -> str:
        body = "".join(
            f"<tr><td style='padding:4px 12px 4px 0;color:#7a8695'>{escape(str(label))}</td>"
            f"<td style='padding:4px 0'>{escape(str(value))}</td></tr>"
            for label, value in rows
        )
        return f"<table cellspacing='0'>{body}</table>"

    def _toggle_running(self) -> None:
        if not self.engine.is_loaded:
            return
        self.is_running = not self.is_running
        if self.is_running:
            self.engine.start_realtime()
        else:
            self.engine.pause_realtime()
        self._update_running_ui()

    def _update_running_ui(self) -> None:
        self.start_button.setText("暂停" if self.is_running else "开始")
        self.run_status_label.setText("● 运行中" if self.is_running else "● 已暂停")

    def _reset(self) -> None:
        self.is_running = False
        self._update_running_ui()
        self.engine.reset()
        self.target_input.setValue(self.engine.target)
        self._refresh_state()
        self.render_widget.refresh_frame()
        self.message_status_label.setText("仿真已重置")

    def _apply_target(self) -> None:
        # GUI -> MuJoCo 的入口：界面只把目标交给SimulationEngine。
        self.engine.set_target(self.target_input.value())
        self.message_status_label.setText(f"目标已更新：{self.target_input.value():.4f}")

    def _change_speed(self) -> None:
        speed = float(self.speed_combo.currentData())
        self.engine.set_speed_multiplier(speed)
        self.message_status_label.setText(f"仿真速度已设为 {speed:g}×")

    def _on_timer(self) -> None:
        if self.is_running:
            self.engine.advance_realtime()
        self._refresh_state()
        self.render_widget.refresh_frame()

    def _refresh_state(self) -> None:
        # MuJoCo -> GUI 的入口：界面只读取get_state()返回的副本。
        state = self.engine.get_state()
        self.time_label.setText(f"{state.time:.4f} s")
        self.step_count_label.setText(str(state.physics_steps))
        self.qpos_text[1].setText(self._format_array(state.qpos))
        self.qvel_text[1].setText(self._format_array(state.qvel))
        self.ctrl_text[1].setText(self._format_array(state.ctrl))
        self._refresh_inspector()

    @staticmethod
    def _format_array(values) -> str:
        array = np.asarray(values)
        return np.array2string(array, precision=4, suppress_small=True, max_line_width=10_000)

    def closeEvent(self, event) -> None:
        self.engine.close()
        super().closeEvent(event)
