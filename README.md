# MuJoCo 最小独立 GUI

这是一个独立的 PySide6 + MuJoCo Python 学习项目，不依赖旧抓取 Demo、MuJoCo Studio 或 LoongEnv。

## 启动

在项目目录打开终端：

```powershell
python main.py
```

## 第一版功能

- 加载 MuJoCo MJCF/XML
- 在 PySide6 窗口内显示 3D 画面
- Start / Pause
- Reset
- 修改一个目标值
- 显示 `data.time`、`data.qpos`、`data.qvel`、`data.ctrl`
- 左键旋转视角，滚轮缩放

## 文件职责

- `main.py`：程序入口。
- `main_window.py`：按钮、输入框和状态显示。
- `simulation.py`：模型加载、控制、`mj_step`、状态读取和渲染。
- `render_widget.py`：把 MuJoCo 图像显示到 PySide6 窗口。
- `controller.py`：最小 PD 控制器示例。
- `models/example.xml`：可直接运行的单关节示例模型。

## 数据流

```text
目标输入框
   ↓ set_target()
SimulationEngine
   ↓ controller.compute()
data.ctrl
   ↓ mujoco.mj_step()
data.time / qpos / qvel / ctrl
   ↓ get_state()
GUI状态显示

model + data
   ↓ mujoco.Renderer
NumPy RGB图像
   ↓ QImage
PySide6内嵌3D画面
```

示例控制器只假定“第一个执行器控制第一个自由度”。加载其他机器人模型时，3D显示和状态读取仍然可用，但控制器不一定适合该模型，需要单独编写对应控制算法。
