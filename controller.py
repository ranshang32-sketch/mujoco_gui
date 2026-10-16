"""最小控制器示例。

控制器和 GUI 分开：GUI 只修改目标值，控制器负责把目标值变成 data.ctrl。
这不是通用机器人控制算法，只用于演示数据如何流入 MuJoCo。
"""

import numpy as np


class FirstJointPDController:
    """用第一个执行器控制第一个自由度的简单 PD 控制器。"""

    def __init__(self, kp: float = 20.0, kd: float = 2.0) -> None:
        self.kp = kp
        self.kd = kd
        self.target = 0.0

    def reset(self, model, data) -> None:
        """模型重置后，以当前关节位置作为初始目标。"""
        self.target = float(data.qpos[0]) if model.nq else 0.0

    def set_target(self, value: float) -> None:
        self.target = float(value)

    def compute(self, model, data) -> np.ndarray:
        """返回长度为 model.nu 的控制输入数组。"""
        ctrl = np.zeros(model.nu, dtype=float)
        if model.nu == 0 or model.nq == 0 or model.nv == 0:
            return ctrl

        position_error = self.target - float(data.qpos[0])
        ctrl[0] = self.kp * position_error - self.kd * float(data.qvel[0])

        # 如果 XML 为执行器设置了 ctrlrange，就把控制量限制在安全范围内。
        if bool(model.actuator_ctrllimited[0]):
            low, high = model.actuator_ctrlrange[0]
            ctrl[0] = np.clip(ctrl[0], low, high)
        return ctrl
