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
        self._backSub.apply(blur, learningRate=0.3)

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
            # 前 10 帧双重学习，快速建立初始背景，高学习率快速遗忘初始静止物体
            if frame_idx <= 10:
                self.warmup(frame)
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
        counts, cross_cooldown, crossing_channels = count_crossings(
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
            crossing_channels=frozenset(crossing_channels),
        )

    # ==========================================================
    # 检测流水线
    # ==========================================================

    def _detect(self, frame: np.ndarray, grid_data: dict) -> tuple:
        """MOG2 检测流水线。

        流水线顺序：
        预处理 → MOG2 → 墙壁遮罩 → Y轴遮罩 → 开运算 → 闭运算×2
        → 墙壁遮罩(二次) → 噪点率 → 轮廓提取 → 聚类合并
        """
        h, w = frame.shape[:2]

        # 预处理
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        # MOG2 背景减除
        raw_fg = self._backSub.apply(blur, learningRate=0.003)

        # 构建墙壁遮罩（前后各用一次）
        wall_mask = self._build_wall_mask(grid_data, h, w)

        # 墙壁遮罩 + Y轴遮罩（形态学前）
        if wall_mask is not None:
            raw_fg = cv2.bitwise_and(raw_fg, wall_mask)
        raw_fg = self._apply_y_mask(raw_fg, h, w)

        # 形态学处理
        fg = self._apply_morphology(raw_fg)

        # 墙壁遮罩二次确认：形态学膨胀可能把前景"长回"墙壁区域
        if wall_mask is not None:
            fg = cv2.bitwise_and(fg, wall_mask)

        # 噪点率
        noise_ratio = cv2.countNonZero(fg) / (h * w)

        # 轮廓提取 → 面积过滤 → 质心 → 聚类合并
        raw_centroids = self._extract_centroids(fg)
        centroids = self._merge_clusters(raw_centroids)

        return centroids, fg, noise_ratio, raw_fg

    # ---- 子步骤 ----

    def _build_wall_mask(
        self, grid_data: dict, h: int, w: int
    ) -> Optional[np.ndarray]:
        """从 channel_bounds 反推墙壁区域遮罩。

        通道之外的区域均为墙壁（左墙、通道间墙、右墙）。
        遮罩中墙壁区域 = 0，通道区域 = 255。

        Returns:
            wall_mask 或 None（无 channel_bounds 时）
        """
        channel_bounds = grid_data.get("channel_bounds", [])
        if not channel_bounds:
            return None

        wall_mask = np.ones((h, w), dtype=np.uint8) * 255
        margin = max(
            getattr(self.config, "wall_mask_margin", 3),
            getattr(self.config, "wall_peak_half_width", 2),
        )

        # 左侧墙壁
        first_ch_left = channel_bounds[0][0]
        if first_ch_left > 0:
            wall_mask[:, : min(w, first_ch_left + margin)] = 0

        # 通道间墙壁
        for i in range(len(channel_bounds) - 1):
            gap_start = max(0, channel_bounds[i][1] - margin)
            gap_end = min(w, channel_bounds[i + 1][0] + margin)
            if gap_end > gap_start:
                wall_mask[:, gap_start:gap_end] = 0

        # 右侧墙壁
        last_ch_right = channel_bounds[-1][1]
        if last_ch_right < w:
            wall_mask[:, max(0, last_ch_right - margin) :] = 0

        return wall_mask

    def _apply_y_mask(
        self, fg: np.ndarray, h: int, w: int
    ) -> np.ndarray:
        """屏蔽画面顶部和底部的噪点区域。

        Returns:
            遮罩后的前景（可能与输入同一对象）
        """
        top = int(h * self.config.mask_top_ratio)
        bot = int(h * self.config.mask_bottom_ratio)
        if top <= 0 and bot >= h:
            return fg
        y_mask = np.ones((h, w), dtype=np.uint8) * 255
        y_mask[:top, :] = 0
        y_mask[bot:, :] = 0
        return cv2.bitwise_and(fg, y_mask)

    def _apply_morphology(self, fg: np.ndarray) -> np.ndarray:
        """形态学：开运算(去竖线噪声) → 闭运算×2(连接虫体断点)。"""
        # 开运算：去除墙壁边缘残留的细竖线噪声
        kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 5))
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel_open)

        # 闭运算：连接虫体碎片
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel_close)
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel_close)

        return fg

    def _extract_centroids(self, fg: np.ndarray) -> list:
        """从二值前景 mask 提取质心坐标（过滤过小轮廓）。"""
        contours, _ = cv2.findContours(
            fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        centroids = []
        for contour in contours:
            if cv2.contourArea(contour) < self.config.min_area:
                continue
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                centroids.append((cx, cy))
        return centroids

    def _merge_clusters(self, raw_centroids: list) -> list:
        """非对称距离聚类合并：X 严格 (20px)，Y 保守 (25px)。

        防止同一虫体被 MOG2 拆成多个碎片导致的重复计数。
        """
        if len(raw_centroids) < 2:
            return raw_centroids

        MERGE_DIST_X = 20
        MERGE_DIST_Y = 25

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
