"""网格提取模块

动态计算微流控芯片的物理通道边界。利用 Sobel 边缘检测 + 垂直投影
定位通道壁，结合通道数和墙壁比例等距划分网格坐标。
"""

import cv2
import numpy as np


def get_interpolated_grid(
    frame: np.ndarray,
    num_channels: int,
    x_margin_ratio: tuple = (0.05, 0.15),
    crop_ratio: tuple = (0.3, 0.7),
    edge_thresh: int = 30,
    signal_thresh_ratio: float = 0.15,
    wall_ratio: float = 0.2,
) -> dict:
    """提取绝对物理网格坐标。

    Args:
        frame: 原始视频帧 (BGR)
        num_channels: 物理通道数量
        x_margin_ratio: (左裁剪比, 右裁剪比)
        crop_ratio: (顶部裁剪比, 底部裁剪比) 用于边缘检测的中央ROI
        edge_thresh: Sobel 二值化阈值
        signal_thresh_ratio: 峰值信号阈值比例
        wall_ratio: 墙壁宽度占通道宽度的比例

    Returns:
        dict: {
            'roi_left', 'roi_right': ROI 左右边界 (绝对像素)
            'channel_width': 单个通道宽度 (像素)
            'wall_width': 墙壁宽度 (像素)
            'channel_bounds': [(left, right), ...] 各通道边界
            'wall_bounds': [(left, right), ...] 各墙壁边界
        }

    Raises:
        RuntimeError: 无法找到有效的边界锚点
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    start_x = int(w * x_margin_ratio[0])
    end_x = int(w * (1 - x_margin_ratio[1]))
    start_y = int(h * crop_ratio[0])
    end_y = int(h * crop_ratio[1])

    mid_roi = gray[start_y:end_y, start_x:end_x]

    # Sobel 垂直边缘检测
    sobelx = cv2.Sobel(mid_roi, cv2.CV_64F, 1, 0, ksize=3)
    sobel_abs = np.uint8(np.absolute(sobelx))
    _, thresh = cv2.threshold(sobel_abs, edge_thresh, 255, cv2.THRESH_BINARY)

    # 垂直投影 + 平滑
    col_sums = np.sum(thresh, axis=0)
    smoothed = np.convolve(col_sums, np.ones(15) / 15, mode="same")

    # 定位有效边界
    threshold_val = np.max(smoothed) * signal_thresh_ratio
    valid_x_indices = np.where(smoothed > threshold_val)[0]

    if len(valid_x_indices) == 0:
        raise RuntimeError("未能找到边界锚点")

    roi_left = int(valid_x_indices[0]) + start_x
    roi_right = int(valid_x_indices[-1]) + start_x
    valid_width = roi_right - roi_left

    denominator = num_channels + (num_channels + 1) * wall_ratio
    channel_width = valid_width / denominator
    wall_width = channel_width * wall_ratio

    # 等距划分
    channel_bounds, wall_bounds = [], []
    current_x = float(roi_left)

    for _ in range(num_channels):
        wall_bounds.append((int(current_x), int(current_x + wall_width)))
        current_x += wall_width
        c_left, c_right = int(current_x), int(current_x + channel_width)
        channel_bounds.append((c_left, c_right))
        current_x += channel_width

    wall_bounds.append((int(current_x), int(current_x + wall_width)))

    return {
        "roi_left": roi_left,
        "roi_right": roi_right,
        "channel_width": channel_width,
        "wall_width": wall_width,
        "channel_bounds": channel_bounds,
        "wall_bounds": wall_bounds,
    }
