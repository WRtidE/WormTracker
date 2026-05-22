"""追踪模块

包含 MOG2 模式的贪心追踪器 (update_tracks) 和 YOLO 模式的记忆追踪器 (MemoryTracker)。
"""

from collections import deque

import numpy as np


# ==========================================================
# MOG2 贪心追踪器
# ==========================================================

def update_tracks(
    current_centroids: list,
    active_worms: dict,
    next_worm_id: int,
    cross_cooldown: dict,
    max_dist_x: int = 25,
    max_dist_y: int = 300,
    track_history_len: int = 100,
) -> tuple:
    """MOG2 模式的垂直优先贪心追踪。

    策略：
    - X 轴严格限制 (max_dist_x)，防止跨通道误匹配
    - Y 轴极度宽容 (max_dist_y)，适应高速运动

    Args:
        current_centroids: [(cx, cy), ...] 当前帧检测到的质心
        active_worms: {id: deque([(cx,cy), ...])} 历史活跃轨迹
        next_worm_id: 下一个可分配的轨迹 ID
        cross_cooldown: {id: remaining} 越线冷却状态
        max_dist_x: 最大水平位移
        max_dist_y: 最大垂直位移
        track_history_len: 轨迹历史最大长度

    Returns:
        (new_active_worms, next_worm_id, movements, cross_cooldown)
    """
    new_active_worms = {}
    movements = []

    # 清理过期冷却
    expired_ids = [wid for wid, cd in cross_cooldown.items() if cd <= 0]
    for wid in expired_ids:
        del cross_cooldown[wid]
    for wid in cross_cooldown:
        cross_cooldown[wid] -= 1

    unmatched_worms = dict(active_worms)

    for cx, cy in current_centroids:
        matched_id, min_dist = None, float("inf")

        for wid, history in unmatched_worms.items():
            last_cx, last_cy = history[-1]
            dx = abs(cx - last_cx)
            dy = abs(cy - last_cy)

            if dx < max_dist_x and dy < max_dist_y:
                if dy < min_dist:
                    min_dist = dy
                    matched_id = wid

        if matched_id is not None:
            movements.append(
                (matched_id, unmatched_worms[matched_id][-1][1], cx, cy)
            )
            history = unmatched_worms[matched_id]
            history.append((cx, cy))
            new_active_worms[matched_id] = history
            del unmatched_worms[matched_id]
        else:
            history = deque(maxlen=track_history_len)
            history.append((cx, cy))
            new_active_worms[next_worm_id] = history
            cross_cooldown[next_worm_id] = 0
            next_worm_id += 1

    return new_active_worms, next_worm_id, movements, cross_cooldown


# ==========================================================
# YOLO 记忆追踪器
# ==========================================================

class TrackState:
    """单个目标的追踪状态 (YOLO 模式)"""

    def __init__(self, track_id: int, point: tuple):
        self.id = track_id
        self.history = [point]
        self.lost_count = 0


class MemoryTracker:
    """线虫专用记忆追踪器 (YOLO 模式)。

    使用欧氏距离 + X/Y 独立上限进行匹配，
    丢失目标最多保留 max_age 帧后清理。
    """

    def __init__(
        self,
        max_age: int = 10,
        max_dist_x: int = 80,
        max_dist_y: int = 150,
    ):
        self.max_age = max_age
        self.max_dist_x = max_dist_x
        self.max_dist_y = max_dist_y
        self.tracks: list[TrackState] = []
        self.next_id = 0

    def update(self, centroids: list) -> list[TrackState]:
        """用当前帧质心更新所有轨迹。

        Args:
            centroids: [(cx, cy), ...]

        Returns:
            活跃的 TrackState 列表
        """
        unmatched = list(centroids)

        # 1. 匹配现有轨迹
        for t in self.tracks:
            best_idx = None
            min_dist = float("inf")
            last_pt = t.history[-1]

            for i, pt in enumerate(unmatched):
                dx = abs(pt[0] - last_pt[0])
                dy = abs(pt[1] - last_pt[1])
                dist = (dx ** 2 + dy ** 2) ** 0.5

                if dist < 120 and dx < self.max_dist_x and dy < self.max_dist_y:
                    if dist < min_dist:
                        min_dist = dist
                        best_idx = i

            if best_idx is not None:
                t.history.append(unmatched[best_idx])
                if len(t.history) > 50:
                    t.history.pop(0)
                t.lost_count = 0
                unmatched.pop(best_idx)
            else:
                t.lost_count += 1

        # 2. 为新质心创建轨迹
        for pt in unmatched:
            self.tracks.append(TrackState(self.next_id, pt))
            self.next_id += 1

        # 3. 清理过期轨迹
        self.tracks = [t for t in self.tracks if t.lost_count <= self.max_age]
        return self.tracks

    def clear(self):
        """清空追踪器 (熔断时调用)"""
        self.tracks = []
