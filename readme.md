# WormTracker 技术文档

<p align="center">
  <a href="https://github.com/WRtidE/WormTracker/actions"><img src="https://img.shields.io/github/actions/workflow/status/WRtidE/WormTracker/build.yml?branch=main&label=build&style=flat-square" alt="Build"></a>
  <a href="https://github.com/WRtidE/WormTracker/releases"><img src="https://img.shields.io/github/v/release/WRtidE/WormTracker?include_prereleases&style=flat-square" alt="Release"></a>
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey?style=flat-square" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.9+-blue?style=flat-square&logo=python" alt="Python">
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
└── wormtracker/             # 核心包
    ├── __init__.py
    ├── config.py            # 配置数据类 & YAML 读写
    ├── core/
    │   ├── counter.py       # 越线计数逻辑
    │   ├── grid.py          # 动态网格提取
    │   ├── tracker.py       # 目标追踪
    │   └── visualize.py     # 画面渲染
    ├── engine/
    │   ├── base.py          # 引擎抽象基类
    │   └── mog2.py          # MOG2 检测引擎
    └── ui/
        ├── window.py        # 主窗口 (GUI)
        ├── thread.py        # 视频处理线程
        └── styles.py        # 暗色主题样式
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
python main.py
```

点击 **📂 选择实验视频** 导入视频，然后点击 **▶ 开始识别** 运行分析。按 **Space** 可暂停/继续。

------

## 3. 核心架构与创新机制

### 3.1 动态网格自适应

微流控芯片可能出现轻微偏移或形变。系统通过 `core/grid.py` 在预热期动态计算通道边界：

- **Sobel 边缘检测**：提取通道壁的垂直边缘
- **列像素投影 + 一维平滑**：定位有效物理边界
- **等分插值**：结合 `num_channels` 和 `wall_ratio`，精准推算所有通道及通道壁的绝对像素坐标

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
| LCD 总数显示 | 实时展示当前线虫累加总数 |
| 通道分布表格 | 实时更新各通道计数 |
| 📊 导出 Excel 报告 | 分析完成后导出 .xlsx 报告 |
| 💾 保存当前配置 | 将参数保存为 YAML 配置文件 |

### 4.2 ⚙️ 参数调节

| 参数 | 说明 |
|------|------|
| 微流控通道数量 | 芯片通道数 (1-100) |
| 检测线高度 (红线) | 越线计数触发线，自下而上穿过触发 |
| Mask 上界 / 下界 | 屏蔽画面上下方无效区域 |
| 虫体滤噪 (最小面积) | 过滤小于该面积的噪点 |

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
| | `wall_ratio` | 0.0 | 通道壁宽度比例 |
| **检测判定** | `tripwire_ratio` | 0.65 | 检测线高度 (0=顶部, 1=底部) |
| | `min_area` / `max_area` | 15 / 4500 | 虫体像素面积区间 |
| | `mask_top_ratio` / `mask_bottom_ratio` | 0.35 / 0.85 | Y 轴屏蔽范围 |
| **背景建模** | `bg_history` | 500 | MOG2 背景历史帧数 |
| | `var_threshold` | 16 | 背景模型敏感度 |
| | `init_frame_index` | 30 | 预热帧数 |
| **追踪策略** | `max_dist_x` | 25 | 最大水平位移 (防串道) |
| | `max_dist_y` | 300 | 最大垂直位移 (容忍高速) |
| | `cross_debounce` | 20 | 越线冷却帧数 |
| **熔断保护** | `panic_noise_ratio` | 0.015 | 触发熔断的噪点比例 |
| | `grid_mutation_tolerance` | 0.15 | 网格突变容忍度 |
| | `cooldown_frames` | 30 | 熔断冷却帧数 |
| **输出** | `export_format` | xlsx | 导出格式: xlsx 或 csv |

------

## 7. 环境依赖

- **Python**：3.7+
- **核心依赖**：
  - `opencv-python` — 视频读取、背景建模、形态学操作
  - `numpy` — 矩阵运算与信号处理
  - `PyQt6` — 图形界面
  - `matplotlib` — 结果图表渲染
  - `pandas` / `openpyxl` — Excel 报告生成
  - `pyyaml` — 配置文件读写
- **内置模块**：`csv`, `collections.deque`, `os`, `datetime`


