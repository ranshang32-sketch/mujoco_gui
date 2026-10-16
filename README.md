# RobotSim Studio · MuJoCo工作台

这是一个独立的 PySide6 + MuJoCo Python 学习项目，不依赖旧抓取 Demo、MuJoCo Studio 或 LoongEnv。

## 启动

在项目目录打开终端：

```powershell
python main.py
```

## 当前功能

- 加载 MuJoCo MJCF/XML
- 在 PySide6 窗口内显示 3D 画面
- Start / Pause
- 暂停状态下单步推进一个 MuJoCo timestep
- Reset
- 按现实经过时间推进 MuJoCo，不把GUI定时器间隔直接当作物理时间
- `0.25× / 0.5× / 1× / 2×`仿真速度
- 显示 `data.time`、物理步数、模型`timestep`、`data.qpos`、`data.qvel`、`data.ctrl`
- 左键旋转视角，滚轮缩放
- 平台工作台布局：模型区、3D工作区、属性检查器和状态栏
- 从实际`MjModel`读取关节与执行器并生成模型树
- 正确区分 actuator 数量和 control 输入数量
- 点击模型、关节或执行器查看实时只读属性与控制通道映射
- 默认保持`data.ctrl`为零，不自动控制新加载模型

## 文件职责

- `main.py`：程序入口。
- `main_window.py`：平台工作台布局、模型树、属性检查器和状态显示。
- `simulation.py`：模型加载、现实时间同步、控制、`mj_step`、状态读取和渲染。
- `render_widget.py`：把 MuJoCo 图像显示到 PySide6 窗口。
- `controller.py`：保留的最小 PD 学习示例；当前平台不会自动调用它。
- `models/example.xml`：初始姿态略微倾斜、可在零控制输入下自然摆动的单关节示例模型。

## 数据流

```text
Start / 单步
   ↓
SimulationEngine
   ↓ data.ctrl保持为零
mujoco.mj_step()
   ↓
data.time / qpos / qvel / ctrl
   ↓ get_state()
GUI状态显示

model + data
   ↓ mujoco.Renderer
NumPy RGB图像
   ↓ QImage
PySide6内嵌3D画面
```

GUI使用约16 ms的定时器刷新界面，但MuJoCo的推进量由真实经过时间、仿真速度和
`model.opt.timestep`共同决定。暂停和恢复时会重新对齐现实时间，因此暂停期间不会补步。

`controller.py`中的示例控制器只假定“第一个执行器控制第一个自由度”，因此不属于通用平台功能。当前主程序不会调用它，避免加载其他机器人后错误控制第一个执行器。

当前“仿真 / 控制 / 结果”导航是平台结构占位，尚未加入对应高级功能。这样可以先确认整体方向，再逐步实现，避免一次堆入过多功能。
