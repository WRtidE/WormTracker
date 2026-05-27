#!/usr/bin/env python3
"""墙壁竖线检测 Demo

用法:
    python demo_wall_detect.py <图片或视频路径> [选项]

    python demo_wall_detect.py test.png
    python demo_wall_detect.py test.mp4
    python demo_wall_detect.py test.mp4 --frame 100 --channels 16 --wall-ratio 0.08

视频输入时默认截取第 50 帧，可通过 --frame 指定帧号。
图片输入时 --frame 参数忽略。

在图片/视频帧上可视化 Sobel 垂直投影、检测到的墙壁峰值、以及划分出的
通道/墙壁区域，用于验证参数是否合理。
"""

import argparse
import sys

import cv2
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# 修复中文显示问题：优先使用系统中文字体
matplotlib.rcParams["font.sans-serif"] = [
    "Songti SC", "PingFang HK", "Heiti TC", "STHeiti",
    "SimSong", "Arial Unicode MS", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

# 直接导入项目内的模块（需要 wormtracker 在 PYTHONPATH 中）
try:
    from wormtracker.core.grid import get_interpolated_grid, _find_projection_peaks
except ImportError:
    # 如果不在包路径中，手动添加
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from wormtracker.core.grid import get_interpolated_grid, _find_projection_peaks


def _load_frame(path: str, frame_no: int) -> np.ndarray:
    """加载图片或从视频中提取指定帧。

    优先尝试作为视频打开，失败则作为图片读取。

    Args:
        path: 文件路径
        frame_no: 视频帧号 (从1开始)

    Returns:
        BGR 格式的帧

    Raises:
        RuntimeError: 无法读取文件
    """
    # 先尝试视频
    cap = cv2.VideoCapture(path)
    if cap.isOpened():
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"检测到视频文件, 共 {total} 帧")
        target = max(1, min(frame_no, total))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target - 1)
        ret, frame = cap.read()
        cap.release()
        if ret:
            print(f"已提取第 {target} 帧")
            return frame
        raise RuntimeError(f"无法从视频中读取第 {target} 帧")

    # 回退图片
    frame = cv2.imread(path)
    if frame is None:
        raise RuntimeError(f"无法读取文件: {path} (不是有效图片或视频)")
    print("检测到图片文件")
    return frame


# ── 默认输入路径 (方便快速修改) ──
DEFAULT_INPUT = "video/T14.mp4"


def main():
    parser = argparse.ArgumentParser(description="墙壁竖线检测可视化 Demo")
    parser.add_argument(
        "input", nargs="?", default=DEFAULT_INPUT,
        help=f"输入图片或视频路径 (默认: {DEFAULT_INPUT})"
    )
    parser.add_argument("--frame", type=int, default=50, help="视频帧号 (默认 50, 图片忽略)")
    parser.add_argument("--channels", type=int, default=32, help="通道数 (默认 32)")
    parser.add_argument("--wall-ratio", type=float, default=0.08, help="墙壁宽度比例 (默认 0.08)")
    parser.add_argument("--margin-left", type=float, default=0.05, help="左侧裁剪比例")
    parser.add_argument("--margin-right", type=float, default=0.15, help="右侧裁剪比例")
    parser.add_argument("--crop-top", type=float, default=0.3, help="边缘检测 ROI 上界")
    parser.add_argument("--crop-bottom", type=float, default=0.7, help="边缘检测 ROI 下界")
    parser.add_argument("--edge-thresh", type=int, default=30, help="Sobel 二值化阈值")
    parser.add_argument("--signal-thresh", type=float, default=0.15, help="边界信号阈值比例")
    parser.add_argument("--no-refine", action="store_true", help="禁用峰值修正（仅等距插值）")
    parser.add_argument("--wall-peak-half-width", type=int, default=2, help="峰值精修墙壁红线半宽 (px, 默认 2)")
    parser.add_argument("--output", type=str, default=None, help="保存结果图片路径")
    args = parser.parse_args()

    try:
        frame = _load_frame(args.input, args.frame)
    except RuntimeError as e:
        print(f"错误: {e}")
        sys.exit(1)

    print(f"帧尺寸: {frame.shape[1]} x {frame.shape[0]} (W x H)")

    # ---- 运行网格检测 ----
    try:
        grid = get_interpolated_grid(
            frame,
            num_channels=args.channels,
            x_margin_ratio=(args.margin_left, args.margin_right),
            crop_ratio=(args.crop_top, args.crop_bottom),
            edge_thresh=args.edge_thresh,
            signal_thresh_ratio=args.signal_thresh,
            wall_ratio=args.wall_ratio,
            refine_walls=not args.no_refine,
            wall_peak_half_width=args.wall_peak_half_width,
        )
    except RuntimeError as e:
        print(f"网格检测失败: {e}")
        sys.exit(1)

    # ---- 打印结果 ----
    print(f"\n=== 网格结果 ===")
    print(f"ROI 范围:    {grid['roi_left']} – {grid['roi_right']}  ({grid['roi_right'] - grid['roi_left']} px)")
    print(f"通道宽度:    {grid['channel_width']:.1f} px")
    print(f"墙壁宽度:    {grid['wall_width']:.1f} px")
    print(f"通道边界:    {len(grid['channel_bounds'])} 条通道")
    print(f"墙壁边界:    {len(grid['wall_bounds'])} 道墙壁")
    print(f"峰值修正:    {'✅ 已启用' if not args.no_refine else '❌ 仅等距'}")

    # ---- 重新计算 Sobel 投影供可视化 ----
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    start_x = int(w * args.margin_left)
    end_x = int(w * (1 - args.margin_right))
    start_y = int(h * args.crop_top)
    end_y = int(h * args.crop_bottom)
    mid_roi = gray[start_y:end_y, start_x:end_x]
    sobelx = cv2.Sobel(mid_roi, cv2.CV_64F, 1, 0, ksize=3)
    sobel_abs = np.uint8(np.absolute(sobelx))
    _, thresh = cv2.threshold(sobel_abs, args.edge_thresh, 255, cv2.THRESH_BINARY)
    col_sums = np.sum(thresh, axis=0)
    smoothed = np.convolve(col_sums, np.ones(15) / 15, mode="same")

    # 使用敏感投影 (edge_thresh=20, 匹配 grid.py)
    from wormtracker.core.grid import _recompute_projection
    signal_sensitive = _recompute_projection(frame, edge_thresh=20)
    est_wall_px = grid['wall_width']
    est_ch_w = grid['channel_width']
    est_wall_spacing = est_ch_w + est_wall_px
    min_prom = 0.03
    min_dist = max(2, int(est_wall_spacing * 0.06))
    all_peaks = _find_projection_peaks(signal_sensitive, min_distance=min_dist, min_prominence=min_prom)

    min_signal_abs = 50000
    top_n = 64
    scored = [(p, signal_sensitive[p]) for p in all_peaks if signal_sensitive[p] >= min_signal_abs]
    scored.sort(key=lambda x: x[1], reverse=True)
    top_peaks = scored[:top_n]
    peak_x_all = sorted([int(p) for p, _ in top_peaks])  # 全宽坐标

    print(f"\n检测到 {len(all_peaks)} 个极大值峰 → 信号≥{min_signal_abs}: {len(scored)} 个 → 取前{top_n}: {len(peak_x_all)} 个")
    print(f"{'编号':>4}  {'X坐标':>6}  {'信号值':>8}  {'到下一峰间隙':>12}")
    print("-" * 36)
    for i, px in enumerate(peak_x_all):
        signal_val = signal_sensitive[px] if 0 <= px < len(signal_sensitive) else 0
        gap_to_next = peak_x_all[i+1] - px if i + 1 < len(peak_x_all) else 0
        gap_str = f"{gap_to_next} px" if gap_to_next > 0 else "(末尾)"
        print(f"{i:>4}  {px:>6}  {signal_val:>8.0f}  {gap_str:>12}")

    # 间隙分类提示
    gaps = [peak_x_all[i+1] - peak_x_all[i] for i in range(len(peak_x_all)-1)]
    large_gaps = [(g, i) for i, g in enumerate(gaps) if g >= 39]
    print(f"\n大间隙 (≥39px): {len(large_gaps)} 个 (通道候选)")
    small_gaps = [(g, i) for i, g in enumerate(gaps) if g < 39]
    print(f"小间隙 (<39px):  {len(small_gaps)} 个 (墙壁/噪声)")
    if large_gaps:
        lg_indices = [f"{i}-{i+1}" for _, i in large_gaps]
        print(f"通道候选编号: {', '.join(lg_indices)}")

    # ---- 可视化 ----

    WALL_COLOR = "#E53E3E"

    fig = plt.figure(figsize=(18, 10))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1], hspace=0.35, wspace=0.3)

    # ---- 1. 图片 + 通道 + 墙线 ----
    ax_img = fig.add_subplot(gs[0, :])
    display = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    ax_img.imshow(display)
    ax_img.axvline(grid["roi_left"], color="cyan", ls="--", lw=1, alpha=0.7)
    ax_img.axvline(grid["roi_right"], color="cyan", ls="--", lw=1, alpha=0.7)
    ax_img.axhline(start_y, color="cyan", ls=":", lw=0.8, alpha=0.5)
    ax_img.axhline(end_y, color="cyan", ls=":", lw=0.8, alpha=0.5)
    for i in range(0, len(peak_x_all), 2):
        left = peak_x_all[i]
        right = peak_x_all[i + 1] if i + 1 < len(peak_x_all) else left + 50
        ax_img.axvspan(left, right, alpha=0.18, color="green")
    for i, px in enumerate(peak_x_all):
        ax_img.axvline(px, color=WALL_COLOR, ls="-", lw=2, alpha=0.9)
        ax_img.text(px + 2, 30, str(i), color=WALL_COLOR, fontsize=7, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.1", facecolor="white", alpha=0.8))
    ax_img.set_title("64峰配对 | 绿=通道 红线=墙峰", fontsize=12, fontweight="bold")

    # ---- 2. 敏感投影 ----
    ax_sig = fig.add_subplot(gs[1, 0])
    ax_sig.plot(np.arange(len(signal_sensitive)), signal_sensitive, color="steelblue", lw=1)
    for i in range(0, len(peak_x_all), 2):
        left = peak_x_all[i]
        right = peak_x_all[i + 1] if i + 1 < len(peak_x_all) else left + 50
        ax_sig.axvspan(left, right, alpha=0.15, color="green")
    for i, px in enumerate(peak_x_all):
        ax_sig.axvline(px, color=WALL_COLOR, ls="-", lw=1.2, alpha=0.8)
    ax_sig.set_xlim(grid["roi_left"] - 50, grid["roi_right"] + 50)
    ax_sig.set_title("敏感投影 (edge_thresh=20)", fontsize=11, fontweight="bold")
    ax_sig.set_xlabel("X")
    ax_sig.set_ylabel("edge")

    # ---- 3. 二值化 ----
    ax_edge = fig.add_subplot(gs[1, 1])
    h2, w2 = frame.shape[:2]
    sy2, ey2 = int(h2*0.3), int(h2*0.7)
    roi2 = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)[sy2:ey2, :]
    sx2 = cv2.Sobel(roi2, cv2.CV_64F, 1, 0, ksize=3)
    _, th2 = cv2.threshold(np.uint8(np.absolute(sx2)), 20, 255, cv2.THRESH_BINARY)
    ax_edge.imshow(th2, cmap="gray", aspect="auto", extent=[0, w2, ey2, sy2])
    ax_edge.set_title("Sobel (thr=20)", fontsize=11, fontweight="bold")

    fig.suptitle("64峰配对 | 绿=通道 红线=墙峰", fontsize=13, fontweight="bold", y=0.98)

    # ---- 输出图像 ----
    if args.output:
        fig.savefig(args.output, dpi=150, bbox_inches="tight")
        print(f"\n图像已保存到: {args.output}")
    plt.show()

if __name__ == "__main__":
    main()
