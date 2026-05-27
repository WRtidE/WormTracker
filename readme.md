<h1 align="center">WormTracker 线虫计数工具</h1>

<p align="center">
  <a href="https://github.com/WRtidE/WormTracker/actions"><img src="https://img.shields.io/github/actions/workflow/status/WRtidE/WormTracker/build.yml?branch=main&label=build&style=flat-square" alt="Build"></a>
  <a href="https://github.com/WRtidE/WormTracker/releases"><img src="https://img.shields.io/github/v/release/WRtidE/WormTracker?include_prereleases&style=flat-square" alt="Release"></a>
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey?style=flat-square" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.9+-blue?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/version-1.4.1-brightgreen?style=flat-square" alt="Version">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/github/stars/WRtidE/WormTracker?style=flat-square" alt="Stars">
</p>

<p align="center"><img src="https://azusa-img-1348009459.cos.ap-beijing.myqcloud.com/wormtrackericon.png" alt="WormTracker Icon" width="180"></p>

## 1. 系统概述

WormTracker 是一套基于计算机视觉的自动化线虫计数系统，专为微流控芯片中的线虫运动视频分析而设计。系统采用 **MOG2 背景减除** 作为检测后端，通过 PyQt6 图形界面提供实时参数调节、暂停/恢复、预览与 Excel 数据导出等完整功能。

核心能力：

- 动态网格自适应，自动定位 1~100 路物理通道边界
- 🔴 红线越线计数 + 🟡 可调 Y 轴 Mask 范围，屏蔽画面上下方噪点
- 熔断保护机制，抵御设备震动/光照突变
- 运行中支持暂停、参数热调、检测线实时预览
- Excel (.xlsx) 报告一键导出，含视频名称与生成时间

### 项目结构

```
WormTracker/
├── main.py                  # GUI 入口 (PyQt6)
├── config.yaml              # 默认配置文件
├── wormtracker.spec         # PyInstaller 打包配置
└── wormtracker/             # 核心包
    ├── __init__.py          # 包元信息 (版本号 v1.4.1)
    ├── __main__.py          # python -m wormtracker 入口
    ├── config.py            # 配置数据类 & YAML 读写
    ├── core/
    │   ├── counter.py       # 越线计数逻辑
    │   ├── grid.py          # 动态网格提取 + 峰值精修
    │   ├── tracker.py       # 目标追踪 (MOG2 贪心 + YOLO 记忆)
    │   └── visualize.py     # 画面渲染
    ├── engine/
    │   ├── base.py          # 引擎抽象基类
    │   └── mog2.py          # MOG2 检测引擎
    └── ui/
        ├── window.py        # 主窗口 (GUI)
        ├── thread.py        # 视频处理线程
        └── styles.py        # 浅色 & 暗色主题 QSS
```

------

## 2. 快速开始

### 2.1 环境配置

```bash
# 创建 conda 环境
conda create -n worm_env python=3.9 -y
conda activate worm_env

# 安装依赖
pip install opencv-python numpy pandas openpyxl pyyaml
pip install PyQt6 matplotlib
```

### 2.2 启动 GUI

```bash
# 使用默认配置
python main.py

# 或指定配置文件
python main.py -c my_config.yaml

# 也可以模块方式运行
python -m wormtracker
```

启动后显示**启动画面 (Splash Screen)**并加载重型模块。点击 **📂 选择实验视频** 导入视频，然后点击 **▶ 开始识别** 运行分析。按 **Space** 可暂停/继续。

------

## 3. 核心架构与创新机制

### 3.1 动态网格自适应 + 峰值精修

微流控芯片可能出现轻微偏移或形变。系统通过 `core/grid.py` 在预热期动态计算通道边界：

- **Sobel 边缘检测**：提取通道壁的垂直边缘
- **列像素投影 + 一维平滑**：定位有效物理边界
- **双向行走峰值精修** (`wall_refine`)：开启后在 Sobel 垂直投影上搜索每一道墙壁的局部峰值，用图像实际特征修正纯几何等距插值的位置偏差。从两端各分配一半通道，交替识别墙壁→通道间隙，比全局间隙分类更鲁棒
- **等分插值（回退）**：当峰值精修失败时，结合 `num_channels` 和 `wall_ratio`，精准推算所有通道及通道壁的绝对像素坐标

### 3.2 目标检测与智能聚类

高速线虫易产生残影导致首尾断裂，被误判为两个目标：

- **MOG2 高敏背景减除**：较低阈值确保高速残影可被捕获
- **非对称距离聚类（防跨通道误杀）**：
  - **极严水平限制**：X 轴合并距离严格控制在 20px 以内
  - **宽容垂直限制**：Y 轴允许较大跨度 (55px)，将断裂的头尾合并为单一质心

### 3.3 垂直优先追踪策略

- 将 X 与 Y 运动容忍度解耦
- 严格限制水平位移，防止 ID 跨通道跃迁
- 极度宽容垂直位移，适应加速或掉落

### 3.4 熔断机制 (Panic Circuit Breaker)

抵御物理碰撞或显微镜调焦干扰：

- **探针 1：网格崩溃检测** — 通道宽度相对基准突变 > 15%
- **探针 2：全图噪点检测** — 前景掩膜面积占比 > 1.5%
- **熔断保护**：触发后挂起追踪器与计数器，进入 30 帧冷却期。冷却期内调高背景学习率，快速吸收新背景

------

## 4. GUI 使用指南

### 4.1 🎮 工作台

| 控件 | 功能 |
|------|------|
| 📂 选择实验视频 | 导入 .mp4 / .avi / .mov / .mkv 视频文件 |
| ▶ 开始识别 / ⏸ 暂停 / 🔄 重新分析 | 控制分析流程 (Space 快捷键) |
| 进度条滑块 | 拖拽或点击跳转到视频任意位置，跳转后自动重置计数 |
| LCD 总数显示 | 实时展示当前线虫累加总数 |
| 通道分布表格 | 实时更新各通道计数 |
| 📊 导出 Excel 报告 | 分析完成后导出 .xlsx 报告 |
| 💾 保存当前配置 | 将参数保存为 YAML 配置文件 |
| 🌓 主题切换 | 状态栏按钮，一键切换浅色/暗色主题 |
| 🔍 识别视角 | 状态栏按钮，切换查看模型检测到的前景/运动区域 |

### 4.2 ⚙️ 参数调节

| 参数 | 说明 |
|------|------|
| 检测线高度 (红线) | 越线计数触发线，自下而上穿过触发 |
| Mask 上界 / 下界 | 屏蔽画面上/下方无效区域，调节 Y 轴有效检测范围 |
| 墙壁遮罩半宽 (px) | 控制通道壁红色遮罩的像素宽度，排除墙壁边缘伪影 |
| 虫体滤噪 (最小面积) | 过滤小于该面积的噪点，防止灰尘等小颗粒误检 |

> **注意**：通道数 `num_channels` 已移至配置文件 (`config.yaml`) 中设定，GUI 中不再提供实时调节。

### 4.3 结果图表

分析完成后，视频区域自动切换为柱状图展示各通道计数分布，包含总计数值、峰值通道等统计信息。

------

## 5. Excel 报告格式

导出的 `.xlsx` 文件包含两个工作表：

### Sheet 1: 计数结果

| 行 | 内容 |
|----|------|
| 第 1 行 | **视频名称**：(文件名) |
| 第 2 行 | **生成时间**：(导出时间戳) |
| 第 4 行起 | 微通道编号 / 线虫统计数量 (含总计行) |

### Sheet 2: 实验信息

| 项目 | 内容 |
|------|------|
| 视频名称 | (文件名) |
| 生成时间 | (时间戳) |
| 检测后端 | MOG2 |

列宽会自动适配中文字符宽度，确保完整显示。

------

## 6. 配置文件说明 (`config.yaml`)

可手动编辑或通过 GUI 导出。支持 `python main.py -c my_config.yaml` 指定配置。

| 分类 | 参数 | 默认值 | 说明 |
|------|------|--------|------|
| **后端** | `backend` | mog2 | 检测后端 |
| **物理映射** | `num_channels` | 32 | 微流控芯片通道数 |
| | `x_margin_left` / `x_margin_right` | 0.05 / 0.15 | 画面左右裁剪比例 |
| | `wall_ratio` | 0.12 | 通道壁宽度比例 |
| | `wall_refine` | true | 实时竖线峰值检测修正网格 |
| **检测判定** | `tripwire_ratio` | 0.65 | 检测线高度 (0=顶部, 1=底部) |
| | `min_area` / `max_area` | 100 / 4500 | 虫体像素面积区间 |
| | `mask_top_ratio` / `mask_bottom_ratio` | 0.35 / 0.85 | Y 轴屏蔽范围 |
| **背景建模** | `bg_history` | 200 | MOG2 背景历史帧数 (降低以更快遗忘初始帧中的静止物体) |
| | `var_threshold` | 16 | 背景模型敏感度 (越小越敏感) |
| | `init_frame_index` | 20 | 预热帧数 (降低以更早开始检测) |
| **追踪策略** | `max_dist_x` | 25 | 最大水平位移 (防串道) |
| | `max_dist_y` | 300 | 最大垂直位移 (容忍高速) |
| | `track_history_len` | 100 | 轨迹历史最大长度 |
| | `cross_debounce` | 10 | 越线冷却帧数 (降低以允许连续虫快速计数) |
| **墙壁遮罩** | `wall_mask_margin` | 3 | 墙壁向内侵蚀像素，防止光照变化导致墙壁伪影 |
| | `wall_peak_half_width` | 5 | 峰值精修模式下墙壁红线半宽 (px)，全宽 = half_width × 2 |
| **熔断保护** | `panic_noise_ratio` | 0.015 | 触发熔断的噪点比例 |
| | `grid_mutation_tolerance` | 0.15 | 网格突变容忍度 |
| | `cooldown_frames` | 30 | 熔断冷却帧数 |
| **输出** | `export_format` | xlsx | 导出格式: xlsx 或 csv |

------

## 7. 环境依赖

- **Python**：3.9+
- **核心依赖**：
  - `opencv-python` — 视频读取、背景建模、形态学操作
  - `numpy` — 矩阵运算与信号处理
  - `PyQt6` — 图形界面
  - `matplotlib` — 结果图表渲染
  - `pandas` / `openpyxl` — Excel 报告生成
  - `pyyaml` — 配置文件读写
- **内置模块**：`csv`, `collections.deque`, `os`, `datetime`

------

## 8. 安全验证风险说明

从 GitHub Releases 下载的打包应用（`.app` / `.exe`）可能会被操作系统标记为安全风险，这是因为应用未经过商业代码签名证书签名。**这是正常现象，不代表应用包含恶意代码。**

### 8.1 macOS 解决方案

macOS Gatekeeper 会弹出以下提示：

> **"Apple无法验证"WormTracker.app"是否包含可能危害Mac安全或泄漏隐私的恶意软件。"**

也可能显示「无法验证开发者」或「已损坏，无法打开」。

**方法一：右键打开（推荐）**

在 Finder 中找到 `WormTracker.app`，**右键点击** → 选择 **「打开」**，在弹出的对话框中再次点击 **「打开」** 即可。

**方法二：终端解除隔离**

```bash
# 移除下载文件的隔离标记
xattr -d com.apple.quarantine /path/to/WormTracker.app
# 或者对解压后的整个文件夹操作
xattr -dr com.apple.quarantine /path/to/WormTracker.app
```

**方法三：系统设置放行**

打开 **系统设置 → 隐私与安全性**，在底部找到被阻止的 WormTracker，点击 **「仍要打开」**。

### 8.2 Windows 解决方案

Windows SmartScreen 会提示「Windows 已保护你的电脑」。

1. 在弹出的窗口中点击 **「更多信息」**
2. 点击 **「仍要运行」** 即可启动应用

> **提示**：上述警告仅因应用未购买昂贵的代码签名证书。如需彻底消除警告，可以从源码运行：
> ```bash
> git clone https://github.com/WRtidE/WormTracker.git
> cd WormTracker
> pip install -r requirements.txt
> python main.py
> ```


