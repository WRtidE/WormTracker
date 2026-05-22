"""越线计数模块

基于中心点距离实现精准通道归属的越线计数器。
线虫自上而下穿越 tripwire 时触发计数，带防抖冷却。
"""

import numpy as np


def count_crossings(
    active_worms: dict,
    counts_dict: dict,
    channel_bounds: list,
    tripwire_y: int,
    cross_cooldown: dict,
    cross_debounce: int = 20,
) -> tuple:
    """基于中心点距离的精准归属越线计数器。

    判定逻辑：自下而上穿过 tripwire（图像坐标 Y 减小）。
    归属策略：计算越线点 X 坐标与各通道中心的距离，归属到最近通道。

    Args:
        active_worms: {worm_id: deque([(cx,cy), ...])}
        counts_dict: {channel_label: count}
        channel_bounds: [(left, right), ...]
        tripwire_y: 检测线 Y 坐标
        cross_cooldown: {worm_id: remaining_cooldown_frames}
        cross_debounce: 越线后冷却帧数

    Returns:
        (counts_dict, cross_cooldown)
    """
    for wid, history in active_worms.items():
        if len(history) < 2:
            continue
        if cross_cooldown.get(wid, 0) > 0:
            continue

        p1 = history[-2]  # 上一帧
        p2 = history[-1]  # 当前帧

        # 自下而上越线 (Y 减小)
        if p1[1] >= tripwire_y and p2[1] < tripwire_y:
            curr_x = p2[0]

            # 找最近通道中心
            channel_centers = [(b[0] + b[1]) / 2 for b in channel_bounds]
            distances = [abs(curr_x - center) for center in channel_centers]
            best_idx = np.argmin(distances)

            current_total_channels = len(channel_bounds)
            found_channel = current_total_channels - best_idx

            counts_dict[found_channel] += 1
            cross_cooldown[wid] = cross_debounce

    return counts_dict, cross_cooldown
