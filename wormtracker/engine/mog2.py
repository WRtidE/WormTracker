"""MOG2 检测引擎

基于 OpenCV MOG2 背景减除 + 形态学聚类的传统视觉后端。
支持熔断保护、Y 轴 Mask 噪点屏蔽。
"""

from typing import Optional

import cv2
import numpy as np

from wormtracker.engine.base import BaseEngine, FrameResult
from wormtracker.core.tracker import update_tracks
from wormtracker.core.counter import count_crossings
from wormtracker.config import WormTrackerConfig, get_config


class MOG2Engine(BaseEngine):
    """MOG2 背景减除检测引擎"""

    def __init__(self, config: Optional[WormTrackerConfig] = None):
        self.config = config or get_config()
        self._backSub: Optional[cv2.BackgroundSubtractor] = None
        self._active_worms: dict = {}
        self._next_worm_id: int = 0
        self._base_channel_width: Optional[float] = None

    def _ensure_backsub(self, frame_shape: tuple) -> None:
        if self._backSub is None:
            self._backSub = cv2.createBackgroundSubtractorMOG2(
                history=self.config.bg_history,
                varThreshold=self.config.var_threshold,
                detectShadows=False,
            )

    # ---- 公共接口 ----

    def warmup(self, frame: np.ndarray) -> None:
        """预热：快速吸收静态背景"""
        self._ensure_backsub(frame.shape)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        self._backSub.apply(blur, learningRate=0.1)

    def reset(self) -> None:
        """熔断时清空追踪器"""
        self._active_worms.clear()

    def process_frame(
        self,
        frame: np.ndarray,
        frame_idx: int,
        grid_data: dict,
        counts: dict,
        cross_cooldown: dict,
    ) -> FrameResult:
        self._ensure_backsub(frame.shape)

        centroids = []
        fg_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        raw_fg = None
        noise_ratio = 0.0
        is_panic = False

        if frame_idx <= self.config.init_frame_index:
            # 预热期：不检测，纯背景学习
            # 前 10 帧双重学习，快速建立初始背景
            if frame_idx <= 10:
                self.warmup(frame)
            self.warmup(frame)
            return FrameResult(
                centroids=[],
                active_worms={},
                fg_mask=fg_mask,
                raw_fg=raw_fg,
                noise_ratio=0.0,
            )

        # MOG2 检测
        centroids, fg_mask, noise_ratio, raw_fg = self._detect(frame, grid_data)

        # 噪点熔断检查 — 触发时跳过追踪和计数
        if noise_ratio > self.config.panic_noise_ratio:
            is_panic = True

        if is_panic:
            return FrameResult(
                centroids=centroids,
                active_worms={},
                fg_mask=fg_mask,
                raw_fg=raw_fg,
                noise_ratio=noise_ratio,
                is_panic=True,
            )

        # 追踪更新
        self._active_worms, self._next_worm_id, _, cross_cooldown = update_tracks(
            centroids,
            self._active_worms,
            self._next_worm_id,
            cross_cooldown,
            max_dist_x=self.config.max_dist_x,
            max_dist_y=self.config.max_dist_y,
            track_history_len=self.config.track_history_len,
        )

        # 越线计数
        counts, cross_cooldown = count_crossings(
            self._active_worms,
            counts,
            grid_data["channel_bounds"],
            int(frame.shape[0] * self.config.tripwire_ratio),
            cross_cooldown,
            cross_debounce=self.config.cross_debounce,
        )

        return FrameResult(
            centroids=centroids,
            active_worms=self._active_worms,
            fg_mask=fg_mask,
            raw_fg=raw_fg,
            noise_ratio=noise_ratio,
            is_panic=False,
        )

    # ---- 内部方法 ----

    def _detect(self, frame: np.ndarray, grid_data: dict) -> tuple:
        """MOG2 检测 + 形态学聚类合并"""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        raw_fg_mask = self._backSub.apply(blur)

        # Y 范围 Mask
        mask_top_y = int(h * self.config.mask_top_ratio)
        mask_bottom_y = int(h * self.config.mask_bottom_ratio)
        if mask_top_y > 0 or mask_bottom_y < h:
            y_mask = np.ones((h, w), dtype=np.uint8) * 255
            y_mask[:mask_top_y, :] = 0
            y_mask[mask_bottom_y:, :] = 0
            raw_fg_mask = cv2.bitwise_and(raw_fg_mask, y_mask)

        noise_ratio = cv2.countNonZero(raw_fg_mask) / (h * w)

        # 通道安全遮罩 (排除墙壁)
        safe_mask = np.zeros((h, w), dtype=np.uint8)
        margin = 3
        for c_left, c_right in grid_data["channel_bounds"]:
            safe_left = max(0, c_left + margin)
            safe_right = min(w, c_right - margin)
            if safe_left < safe_right:
                safe_mask[:, safe_left:safe_right] = 255

        fg_mask = cv2.bitwise_and(raw_fg_mask, safe_mask)

        # 形态学闭运算 (连接断点)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)

        # 轮廓提取
        contours, _ = cv2.findContours(
            fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        raw_centroids = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.config.min_area:
                continue
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                raw_centroids.append((cx, cy))

        # 非对称距离聚类合并 (防跨通道误杀)
        centroids = self._merge_clusters(raw_centroids)
        return centroids, fg_mask, noise_ratio, raw_fg_mask

    def _merge_clusters(self, raw_centroids: list) -> list:
        """非对称距离合并：X 严格 (20px)，Y 宽容 (55px)"""
        if len(raw_centroids) < 2:
            return raw_centroids

        MERGE_DIST_X = 20
        MERGE_DIST_Y = 55

        final = []
        used = [False] * len(raw_centroids)

        for i in range(len(raw_centroids)):
            if used[i]:
                continue
            cluster = [raw_centroids[i]]
            used[i] = True
            for j in range(i + 1, len(raw_centroids)):
                if used[j]:
                    continue
                dx = abs(raw_centroids[i][0] - raw_centroids[j][0])
                dy = abs(raw_centroids[i][1] - raw_centroids[j][1])
                if dx < MERGE_DIST_X and dy < MERGE_DIST_Y:
                    cluster.append(raw_centroids[j])
                    used[j] = True
            avg_x = int(np.mean([p[0] for p in cluster]))
            avg_y = int(np.mean([p[1] for p in cluster]))
            final.append((avg_x, avg_y))

        return final
