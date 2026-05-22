"""可视化模块

提供统一的 draw_dashboard 函数，支持计数红线、Mask 上下界、
通道标签、熔断警报、前景遮罩预览等渲染。
"""

from typing import Optional

import cv2
import numpy as np


def draw_dashboard(
    frame: np.ndarray,
    counts_dict: dict,
    grid_data: dict,
    active_worms: dict,
    tripwire_y: int,
    fg_mask: Optional[np.ndarray] = None,
    is_panic: bool = False,
    cooldown_rem: int = 0,
    mask_top: Optional[float] = None,
    mask_bottom: Optional[float] = None,
) -> np.ndarray:
    """UI 大屏渲染。

    绘制内容：
    - 通道壁红色半透明遮罩
    - 绿色通道边界线 + 通道编号
    - 红色计数检测线 (tripwire)
    - 黄色 Mask 上下界
    - 目标点 (黄点)
    - 总计数字
    - 前景遮罩缩略图 (右下角)
    - 熔断警报 (全屏红框)

    Args:
        frame: 原始帧 (BGR, 会被原地修改)
        counts_dict: {channel_label: count}
        grid_data: 网格数据字典
        active_worms: {id: deque([(cx,cy), ...])}
        tripwire_y: 检测线 Y 像素坐标
        fg_mask: 前景/检测遮罩 (用于右下角缩略图)
        is_panic: 是否处于熔断状态
        cooldown_rem: 熔断剩余帧数
        mask_top: Mask 上界 Y 像素坐标
        mask_bottom: Mask 下界 Y 像素坐标

    Returns:
        标注后的帧 (与输入 frame 同一对象)
    """
    h, w = frame.shape[:2]

    # 通道壁红色遮罩
    if grid_data is not None:
        overlay = frame.copy()
        for w_left, w_right in grid_data["wall_bounds"]:
            cv2.rectangle(overlay, (w_left, 0), (w_right, h), (0, 0, 255), -1)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)

        # 红色检测线
        cv2.line(
            frame,
            (grid_data["roi_left"], tripwire_y),
            (grid_data["roi_right"], tripwire_y),
            (0, 0, 255),
            2,
        )

        # 黄色 Mask 上下界
        if mask_top is not None:
            cv2.line(
                frame,
                (grid_data["roi_left"], int(mask_top)),
                (grid_data["roi_right"], int(mask_top)),
                (0, 215, 255),
                1,
            )
            cv2.putText(
                frame,
                "MASK TOP",
                (grid_data["roi_right"] + 5, int(mask_top) + 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (0, 215, 255),
                1,
            )
        if mask_bottom is not None:
            cv2.line(
                frame,
                (grid_data["roi_left"], int(mask_bottom)),
                (grid_data["roi_right"], int(mask_bottom)),
                (0, 215, 255),
                1,
            )
            cv2.putText(
                frame,
                "MASK BOT",
                (grid_data["roi_right"] + 5, int(mask_bottom) + 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (0, 215, 255),
                1,
            )

        # 通道边界 + 编号 + 计数
        current_total_channels = len(grid_data["channel_bounds"])
        for idx, (c_left, c_right) in enumerate(grid_data["channel_bounds"]):
            channel_id = current_total_channels - idx
            center_x = int((c_left + c_right) / 2)
            cv2.line(frame, (c_left, 0), (c_left, h), (0, 255, 0), 1)
            cv2.line(frame, (c_right, 0), (c_right, h), (0, 255, 0), 1)
            cv2.putText(
                frame, str(channel_id), (center_x - 8, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1,
            )

            count_val = counts_dict.get(channel_id, 0)
            color = (0, 255, 0) if count_val > 0 else (100, 100, 100)
            cv2.putText(
                frame, str(count_val), (center_x - 8, tripwire_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1,
            )

    # 目标点
    for history in active_worms.values():
        cv2.circle(frame, (history[-1][0], history[-1][1]), 4, (0, 255, 255), -1)

    # 总计
    cv2.putText(
        frame, f"TOTAL: {sum(counts_dict.values())}",
        (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2,
    )

    # 熔断警报
    if is_panic:
        cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 255), 15)
        cv2.putText(
            frame,
            f"PANIC MODE: TRACKING PAUSED ({cooldown_rem})",
            (w // 2 - 350, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 0, 255),
            3,
        )
        cv2.putText(
            frame,
            "Waiting for channel to stabilize...",
            (w // 2 - 250, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
        )

    return frame
