"""MuJoCo 仿真逻辑。

这个文件不知道按钮、输入框或窗口布局，只管理 model、data、控制器和渲染器。
"""

from dataclasses import dataclass
from pathlib import Path
import time

import mujoco
import numpy as np

from controller import FirstJointPDController


@dataclass
class SimulationState:
    """从 MuJoCo 返回给 GUI 的只读快照。"""

    time: float
    qpos: np.ndarray
    qvel: np.ndarray
    ctrl: np.ndarray
    physics_steps: int


class SimulationEngine:
    MAX_WALL_DELTA = 0.1
    MAX_STEPS_PER_UPDATE = 500

    def __init__(self) -> None:
        self.model: mujoco.MjModel | None = None
        self.data: mujoco.MjData | None = None
        self.model_path: Path | None = None
        self.controller = FirstJointPDController()
        self._renderer: mujoco.Renderer | None = None
        self._render_size = (0, 0)
        self.camera = mujoco.MjvCamera()
        self._speed_multiplier = 1.0
        self._clock_running = False
        self._last_wall_time: float | None = None
        self._time_accumulator = 0.0
        self._physics_steps = 0

    @property
    def is_loaded(self) -> bool:
        return self.model is not None and self.data is not None

    @property
    def target(self) -> float:
        return self.controller.target

    @property
    def speed_multiplier(self) -> float:
        return self._speed_multiplier

    def load_model(self, xml_path: str | Path) -> None:
        """加载一个 MuJoCo MJCF/XML，并创建全新的仿真状态。"""
        path = Path(xml_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"找不到模型文件：{path}")

        self.close_renderer()
        self.model = self._load_model_windows_safe(path)
        self.data = mujoco.MjData(self.model)
        self.model_path = path
        mujoco.mj_forward(self.model, self.data)

        mujoco.mjv_defaultCamera(self.camera)
        if hasattr(mujoco, "mjv_defaultFreeCamera"):
            mujoco.mjv_defaultFreeCamera(self.model, self.camera)
        self.controller.reset(self.model, self.data)
        self._reset_clock()

    @staticmethod
    def _load_model_windows_safe(path: Path) -> mujoco.MjModel:
        """通过内存加载模型，绕过部分Windows环境的中文路径编码问题。

        assets 的键仍然保留相对于主 XML 的目录结构，所以 XML 中的
        ``meshdir``、纹理以及 ``include`` 可以继续使用相对路径。
        """
        xml_bytes = path.read_bytes()
        try:
            xml_text = xml_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            xml_text = xml_bytes.decode("gb18030")

        assets: dict[str, bytes] = {}
        for asset_path in path.parent.rglob("*"):
            if not asset_path.is_file() or asset_path == path:
                continue
            relative_name = asset_path.relative_to(path.parent).as_posix()
            assets[relative_name] = asset_path.read_bytes()

        return mujoco.MjModel.from_xml_string(xml_text, assets=assets)

    def set_target(self, value: float) -> None:
        """GUI -> 仿真：接收界面输入的目标值。"""
        self.controller.set_target(value)

    def get_model_info(self) -> dict[str, object]:
        """返回模型树和属性面板需要的基本信息。"""
        if not self.is_loaded:
            return {}
        return {
            "name": self.model_path.stem if self.model_path else "未命名模型",
            "path": str(self.model_path) if self.model_path else "",
            "nq": int(self.model.nq),
            "nv": int(self.model.nv),
            "nu": int(self.model.nu),
            "joints": int(self.model.njnt),
            "timestep": float(self.model.opt.timestep),
        }

    def get_joint_items(self) -> list[dict[str, object]]:
        """从当前MjModel读取真实关节名称和类型。"""
        if not self.is_loaded:
            return []
        type_names = {
            int(mujoco.mjtJoint.mjJNT_FREE): "free",
            int(mujoco.mjtJoint.mjJNT_BALL): "ball",
            int(mujoco.mjtJoint.mjJNT_SLIDE): "slide",
            int(mujoco.mjtJoint.mjJNT_HINGE): "hinge",
        }
        items = []
        for joint_id in range(self.model.njnt):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
            items.append(
                {
                    "id": joint_id,
                    "name": name or f"未命名关节 {joint_id}",
                    "type": type_names.get(int(self.model.jnt_type[joint_id]), "unknown"),
                }
            )
        return items

    def get_actuator_items(self) -> list[dict[str, object]]:
        """从当前MjModel读取真实执行器名称。"""
        if not self.is_loaded:
            return []
        items = []
        for actuator_id in range(self.model.nu):
            name = mujoco.mj_id2name(
                self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_id
            )
            items.append({"id": actuator_id, "name": name or f"未命名执行器 {actuator_id}"})
        return items

    def get_joint_details(self, joint_id: int) -> dict[str, object]:
        """返回一个关节当前的只读属性，供右侧检查器显示。"""
        item = next((item for item in self.get_joint_items() if item["id"] == joint_id), None)
        if item is None:
            return {}

        qpos_size = {"free": 7, "ball": 4}.get(str(item["type"]), 1)
        dof_size = {"free": 6, "ball": 3}.get(str(item["type"]), 1)
        qpos_adr = int(self.model.jnt_qposadr[joint_id])
        dof_adr = int(self.model.jnt_dofadr[joint_id])
        actuator_names = []
        joint_transmissions = {
            int(mujoco.mjtTrn.mjTRN_JOINT),
            int(mujoco.mjtTrn.mjTRN_JOINTINPARENT),
        }
        for actuator in self.get_actuator_items():
            actuator_id = int(actuator["id"])
            if (
                int(self.model.actuator_trntype[actuator_id]) in joint_transmissions
                and int(self.model.actuator_trnid[actuator_id, 0]) == joint_id
            ):
                actuator_names.append(str(actuator["name"]))

        details = dict(item)
        details.update(
            {
                "qpos": self.data.qpos[qpos_adr : qpos_adr + qpos_size].copy(),
                "qvel": self.data.qvel[dof_adr : dof_adr + dof_size].copy(),
                "actuator": ", ".join(actuator_names) if actuator_names else "无",
                "limited": bool(self.model.jnt_limited[joint_id]),
            }
        )
        if bool(self.model.jnt_limited[joint_id]):
            details["range"] = self.model.jnt_range[joint_id].copy()
        return details

    def get_actuator_details(self, actuator_id: int) -> dict[str, object]:
        item = next(
            (item for item in self.get_actuator_items() if item["id"] == actuator_id),
            None,
        )
        if item is None:
            return {}

        transmission = int(self.model.actuator_trntype[actuator_id])
        joint_transmissions = {
            int(mujoco.mjtTrn.mjTRN_JOINT),
            int(mujoco.mjtTrn.mjTRN_JOINTINPARENT),
        }
        target = "其他传动类型"
        if transmission in joint_transmissions:
            joint_id = int(self.model.actuator_trnid[actuator_id, 0])
            target = mujoco.mj_id2name(
                self.model, mujoco.mjtObj.mjOBJ_JOINT, joint_id
            ) or f"关节 {joint_id}"

        details = dict(item)
        details.update(
            {
                "target": target,
                "ctrl": float(self.data.ctrl[actuator_id]),
                "limited": bool(self.model.actuator_ctrllimited[actuator_id]),
            }
        )
        if bool(self.model.actuator_ctrllimited[actuator_id]):
            details["range"] = self.model.actuator_ctrlrange[actuator_id].copy()
        return details

    def reset(self) -> None:
        if not self.is_loaded:
            return
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        self.controller.reset(self.model, self.data)
        self._reset_clock()

    def set_speed_multiplier(self, value: float) -> None:
        """设置仿真速度；它只影响之后经过的现实时间。"""
        value = float(value)
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError("仿真速度必须是大于 0 的有限数值。")
        self._speed_multiplier = value
        if self._clock_running:
            # 从现在重新计时，避免把切换速度前的时间按新速度计算。
            self._last_wall_time = time.perf_counter()

    def start_realtime(self, now: float | None = None) -> None:
        """开始或恢复实时仿真，不把暂停期间的时间补算进去。"""
        if not self.is_loaded:
            return
        self._clock_running = True
        self._last_wall_time = time.perf_counter() if now is None else float(now)

    def pause_realtime(self) -> None:
        """暂停物理步进；保留不足一个 timestep 的小数时间。"""
        self._clock_running = False
        self._last_wall_time = None

    def advance_realtime(self, now: float | None = None) -> int:
        """按照实际经过时间执行所需数量的 ``mj_step``。

        Qt 定时器只负责定期调用本方法，并不直接决定 MuJoCo 前进多少时间。
        单次现实时间会被截断，并限制最大步数，防止窗口卡顿后疯狂补步。
        """
        if not self.is_loaded or not self._clock_running:
            return 0

        current = time.perf_counter() if now is None else float(now)
        if self._last_wall_time is None:
            self._last_wall_time = current
            return 0

        wall_delta = max(0.0, current - self._last_wall_time)
        self._last_wall_time = current
        wall_delta = min(wall_delta, self.MAX_WALL_DELTA)
        self._time_accumulator += wall_delta * self._speed_multiplier

        timestep = float(self.model.opt.timestep)
        # 极小容差只用于抵消浮点表示误差，例如理论上的0.040/0.002
        # 不应因为二进制小数略小于整数而少执行一步。
        scheduled_steps = int((self._time_accumulator + timestep * 1e-9) / timestep)
        if scheduled_steps <= 0:
            return 0

        # 无论是否触发上限，都丢弃已经调度的完整步时间，只保留不足一步的余量。
        # 这样界面卡顿后不会形成永远追不完的积压。
        self._time_accumulator = max(
            0.0, self._time_accumulator - scheduled_steps * timestep
        )
        steps_to_run = min(scheduled_steps, self.MAX_STEPS_PER_UPDATE)
        for _ in range(steps_to_run):
            self._step_once()
        return steps_to_run

    def _reset_clock(self) -> None:
        self._clock_running = False
        self._last_wall_time = None
        self._time_accumulator = 0.0
        self._physics_steps = 0

    def _step_once(self) -> None:
        """计算一次控制输入，然后推进一个 MuJoCo 物理步。"""
        if self.model.nu:
            self.data.ctrl[:] = self.controller.compute(self.model, self.data)
        mujoco.mj_step(self.model, self.data)
        self._physics_steps += 1

    def step_for(self, duration: float) -> None:
        """推进指定的仿真时长，物理步长始终读取当前 model.opt.timestep。"""
        if not self.is_loaded:
            return

        end_time = self.data.time + max(0.0, duration)
        max_steps = 10_000  # 防止错误 timestep 导致 GUI 长时间卡住。
        steps = 0
        while self.data.time < end_time and steps < max_steps:
            # GUI目标值 -> 控制器 -> data.ctrl -> MuJoCo。
            self._step_once()
            steps += 1

    def get_state(self) -> SimulationState:
        """仿真 -> GUI：复制状态，避免 GUI 意外改写 MuJoCo 内部数组。"""
        if not self.is_loaded:
            return SimulationState(0.0, np.array([]), np.array([]), np.array([]), 0)
        return SimulationState(
            time=float(self.data.time),
            qpos=self.data.qpos.copy(),
            qvel=self.data.qvel.copy(),
            ctrl=self.data.ctrl.copy(),
            physics_steps=self._physics_steps,
        )

    def render(self, width: int, height: int) -> np.ndarray | None:
        if not self.is_loaded or width < 2 or height < 2:
            return None

        # 窗口尺寸改变时重建离屏渲染器，保证画面不会拉伸。
        size = (int(width), int(height))
        if self._renderer is None or self._render_size != size:
            self.close_renderer()
            # MuJoCo模型常把离屏缓冲区默认设为640×480。GUI窗口可能更大，
            # 因此在创建Renderer前同步扩大缓冲区，不要求用户修改XML。
            self.model.vis.global_.offwidth = max(self.model.vis.global_.offwidth, size[0])
            self.model.vis.global_.offheight = max(self.model.vis.global_.offheight, size[1])
            self._renderer = mujoco.Renderer(self.model, height=size[1], width=size[0])
            self._render_size = size

        self._renderer.update_scene(self.data, camera=self.camera)
        return self._renderer.render()

    def rotate_camera(self, dx: float, dy: float) -> None:
        self.camera.azimuth += dx * 0.35
        self.camera.elevation = float(np.clip(self.camera.elevation - dy * 0.35, -89.0, 89.0))

    def zoom_camera(self, wheel_steps: float) -> None:
        factor = 0.9 ** wheel_steps
        self.camera.distance = max(0.05, self.camera.distance * factor)

    def close_renderer(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
        self._render_size = (0, 0)

    def close(self) -> None:
        self.close_renderer()
