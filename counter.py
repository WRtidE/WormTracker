import cv2
import numpy as np
import csv
from collections import deque

# ==========================================
# 全局实验配置参数 (终极调优版)
# ==========================================
NUM_CHANNELS = 32              # 物理通道数量
X_MARGIN = (0.05, 0.15)        # 左侧屏蔽5%，右侧屏蔽15%
WALL_RATIO = 0.0               # 物理墙壁厚度比例
TRIPWIRE_RATIO = 0.65           # 虚拟检测线高度 (65%) - 保留兼容
ROI_MASK_TOP_RATIO = 0.35       # 🆕 Mask 上界线 (屏蔽上方噪点)
ROI_MASK_BOTTOM_RATIO = 0.85    # 🆕 Mask 下界线 (屏蔽下方噪点)
MIN_AREA = 15                  # 线虫最小面积
MAX_AREA = 4500                # 线虫最大面积 (稍微调大，容忍高速残影)
BG_HISTORY = 500               # 背景模型历史帧数
INIT_FRAME_INDEX = 30          # 初始化网格帧号
CROSS_DEBOUNCE = 20             # 越线防抖帧数 (计数冷却期)
TRACK_HISTORY_LEN = 100        # 追踪历史长度

# 追踪策略：垂直优先 
MAX_DIST_X = 25               # 严格限制水平位移 (防串道)
MAX_DIST_Y = 300              # 极度宽容垂直位移 (容忍超高速飙车)

# 熔断机制阈值 (设备防抖)
PANIC_NOISE_RATIO = 0.015      # 全图超过 1.5% 的像素突变，视为剧烈震动
GRID_MUTATION_TOLERANCE = 0.15 # 通道宽度突变超过 15%，视为网格崩溃
COOLDOWN_FRAMES = 30           # 每次震动后，强制冷却/暂停计数 10 帧

# 从左到右递减：[32, 31, 30 ... 2, 1]
PHYSICAL_LABELS = list(range(NUM_CHANNELS, 0, -1))

# 💡 提示：如果你的芯片在画面上是从左到右递增的 (1, 2, 3 ... 32)，请改为：
# PHYSICAL_LABELS = list(range(1, NUM_CHANNELS + 1))
# ==========================================
# 获取通道

def get_interpolated_grid(frame, num_channels, x_margin_ratio, crop_ratio=(0.3, 0.7), edge_thresh=30, signal_thresh_ratio=0.15, wall_ratio=0.2):
    """提取绝对物理网格坐标"""
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    start_x = int(w * x_margin_ratio[0])
    end_x = int(w * (1 - x_margin_ratio[1]))
    start_y = int(h * crop_ratio[0])
    end_y = int(h * crop_ratio[1])
    
    mid_roi = gray[start_y:end_y, start_x:end_x]
    
    sobelx = cv2.Sobel(mid_roi, cv2.CV_64F, 1, 0, ksize=3)
    sobel_abs = np.uint8(np.absolute(sobelx))
    _, thresh = cv2.threshold(sobel_abs, edge_thresh, 255, cv2.THRESH_BINARY)
    col_sums = np.sum(thresh, axis=0)
    smoothed = np.convolve(col_sums, np.ones(15)/15, mode='same')
    
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
        'roi_left': roi_left, 'roi_right': roi_right,
        'channel_width': channel_width, 'wall_width': wall_width,
        'channel_bounds': channel_bounds, 'wall_bounds': wall_bounds
    }

# 线虫检测
def detect_worms(frame, backSub, grid_data, min_area=15, roi_mask_top=None, roi_mask_bottom=None):
    """检测器：彻底解决 1虫2点问题，支持 Y 范围 mask 屏蔽界外噪点"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    
    raw_fg_mask = backSub.apply(blur)
    h, w = raw_fg_mask.shape

    # 🆕 Y 范围 mask：屏蔽上下界外的区域
    if roi_mask_top is not None or roi_mask_bottom is not None:
        y_mask = np.ones((h, w), dtype=np.uint8) * 255
        if roi_mask_top is not None:
            y_mask[:int(roi_mask_top), :] = 0
        if roi_mask_bottom is not None:
            y_mask[int(roi_mask_bottom):, :] = 0
        raw_fg_mask = cv2.bitwise_and(raw_fg_mask, y_mask)

    noise_ratio = cv2.countNonZero(raw_fg_mask) / (h * w)
    
    safe_mask = np.zeros((h, w), dtype=np.uint8)
    margin = 3
    for (c_left, c_right) in grid_data['channel_bounds']:
        safe_left = max(0, c_left + margin)
        safe_right = min(w, c_right - margin)
        if safe_left < safe_right:
            safe_mask[:, safe_left:safe_right] = 255
            
    fg_mask = cv2.bitwise_and(raw_fg_mask, safe_mask)

    # 1. 基础形态学连通
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)  

    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    raw_centroids = []

    # 2. 提取所有可能的原始质心
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue

        M = cv2.moments(contour)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            raw_centroids.append((cx, cy))

# ====================== 💥 核心聚类合并逻辑 (防跨通道误杀版) 💥 ======================
    if len(raw_centroids) < 2:
        return raw_centroids, fg_mask, noise_ratio, raw_fg_mask

    final_centroids = []
    used = [False] * len(raw_centroids)
    
    # 将单一的直线距离，拆分为 X 和 Y 的独立限制
    MERGE_DIST_X = 20  # 💥 极严格的水平限制：只有X偏差极小，才可能是一只虫
    MERGE_DIST_Y = 55  # 💥 宽容的垂直限制：允许虫子头尾在Y轴上断开较远
    
    for i in range(len(raw_centroids)):
        if used[i]: continue
        
        cluster = [raw_centroids[i]]
        used[i] = True
        for j in range(i + 1, len(raw_centroids)):
            if not used[j]:
                # 分别计算 X 和 Y 的绝对偏差
                dx = abs(raw_centroids[i][0] - raw_centroids[j][0])
                dy = abs(raw_centroids[i][1] - raw_centroids[j][1])
                
                # 只有当左右非常靠近，且上下距离在允许范围内时，才进行合并
                if dx < MERGE_DIST_X and dy < MERGE_DIST_Y:
                    cluster.append(raw_centroids[j])
                    used[j] = True
        
        # 取该簇的平均坐标作为最终坐标
        avg_x = int(np.mean([p[0] for p in cluster]))
        avg_y = int(np.mean([p[1] for p in cluster]))
        final_centroids.append((avg_x, avg_y))
    # =================================================================

    return final_centroids, fg_mask, noise_ratio, raw_fg_mask
# 追踪更新
def update_tracks(current_centroids, active_worms, next_worm_id, cross_cooldown):
    """追踪更新 (垂直优先追踪策略)"""
    new_active_worms, movements = {}, []
    expired_ids = [wid for wid, cd in cross_cooldown.items() if cd <= 0]
    for wid in expired_ids: del cross_cooldown[wid]
    for wid in cross_cooldown: cross_cooldown[wid] -= 1
    
    unmatched_worms = dict(active_worms)
    
    for (cx, cy) in current_centroids:
        matched_id, min_dist = None, float('inf')
        
        for wid, history in unmatched_worms.items():
            last_cx, last_cy = history[-1]
            dx = abs(cx - last_cx)
            dy = abs(cy - last_cy)
            
            # 💥 核心升级：严格限制 X 位移，极其宽容 Y 位移
            if dx < MAX_DIST_X and dy < MAX_DIST_Y:
                if dy < min_dist:
                    min_dist = dy
                    matched_id = wid
        
        if matched_id is not None:
            movements.append((matched_id, unmatched_worms[matched_id][-1][1], cx, cy))
            history = unmatched_worms[matched_id]
            history.append((cx, cy))
            new_active_worms[matched_id] = history
            del unmatched_worms[matched_id]
        else:
            history = deque(maxlen=TRACK_HISTORY_LEN)
            history.append((cx, cy))
            new_active_worms[next_worm_id] = history
            cross_cooldown[next_worm_id] = 0
            next_worm_id += 1
            
    return new_active_worms, next_worm_id, movements, cross_cooldown


def count_crossings(active_worms, counts_dict, channel_bounds, tripwire_y, cross_cooldown):
    """基于'中心点距离'的精准归属计数器（单线越线模式）"""
    for wid, history in active_worms.items():
        if len(history) < 2: continue
        if cross_cooldown.get(wid, 0) > 0: continue
        
        p1 = history[-2] # 上一帧点
        p2 = history[-1] # 当前帧点
        
        # 判定越线：自下而上 (图像坐标系 Y 减小)
        if p1[1] >= tripwire_y and p2[1] < tripwire_y:
            curr_x = p2[0]
            
            # 💥 基础逻辑升级：寻找距离当前 X 最近的通道中心
            channel_centers = [(b[0] + b[1]) / 2 for b in channel_bounds]
            distances = [abs(curr_x - center) for center in channel_centers]
            best_idx = np.argmin(distances)
            
            current_total_channels = len(channel_bounds)
            found_channel = current_total_channels - best_idx 
            
            counts_dict[found_channel] += 1
            cross_cooldown[wid] = CROSS_DEBOUNCE
            
            print(f"🎯 精准捕获！线虫 ID-{wid} 归属于通道 {found_channel} (距离中心 {distances[best_idx]:.1f}px)")
            
    return counts_dict, cross_cooldown


def draw_dashboard(frame, counts_dict, grid_data, active_worms, tripwire_y, fg_mask=None, is_panic=False, cooldown_rem=0, mask_top=None, mask_bottom=None):
    """UI大屏渲染（tripwire 计数 + mask 边界可视化）"""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    
    if grid_data is not None:
        for w_left, w_right in grid_data['wall_bounds']:
            cv2.rectangle(overlay, (w_left, 0), (w_right, h), (0, 0, 255), -1)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
        
        # 🔴 计数红线 (tripwire)
        cv2.line(frame, (grid_data['roi_left'], tripwire_y),
                 (grid_data['roi_right'], tripwire_y), (0, 0, 255), 2)

        # 🟡 Mask 上下界 (虚线风格)
        if mask_top is not None:
            cv2.line(frame, (grid_data['roi_left'], int(mask_top)),
                     (grid_data['roi_right'], int(mask_top)), (0, 215, 255), 1)
            cv2.putText(frame, "MASK TOP", (grid_data['roi_right'] + 5, int(mask_top) + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 215, 255), 1)
        if mask_bottom is not None:
            cv2.line(frame, (grid_data['roi_left'], int(mask_bottom)),
                     (grid_data['roi_right'], int(mask_bottom)), (0, 215, 255), 1)
            cv2.putText(frame, "MASK BOT", (grid_data['roi_right'] + 5, int(mask_bottom) + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 215, 255), 1)
        
        current_total_channels = len(grid_data['channel_bounds'])
        for idx, (c_left, c_right) in enumerate(grid_data['channel_bounds']):
            channel_id = current_total_channels - idx  
            center_x = int((c_left + c_right) / 2)
            cv2.line(frame, (c_left, 0), (c_left, h), (0, 255, 0), 1)
            cv2.line(frame, (c_right, 0), (c_right, h), (0, 255, 0), 1)
            cv2.putText(frame, str(channel_id), (center_x - 8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            count_val = counts_dict.get(channel_id, 0)
            color = (0, 255, 0) if count_val > 0 else (100, 100, 100)
            cv2.putText(frame, str(count_val), (center_x - 8, tripwire_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    
    for history in active_worms.values():
        cv2.circle(frame, (history[-1][0], history[-1][1]), 4, (0, 255, 255), -1)
    
    cv2.putText(frame, f"TOTAL: {sum(counts_dict.values())}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
    
    if fg_mask is not None:
        fg_color = cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2BGR)
        fg_color = cv2.resize(fg_color, (w//3, h//3))
        frame[10:10+h//3, w-w//3-10:w-10] = fg_color

    # 💥 熔断警报 UI
    if is_panic:
        cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 255), 15)
        cv2.putText(frame, f"PANIC MODE: TRACKING PAUSED ({cooldown_rem})", (w//2 - 350, 100), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        cv2.putText(frame, "Waiting for channel to stabilize...", (w//2 - 250, 150), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
    return frame


def process_video(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ 无法打开视频文件: {video_path}")
        return
    
    # 💥 核心优化：varThreshold 改为 10，大幅提高对极速残影的敏感度
    backSub = cv2.createBackgroundSubtractorMOG2(history=BG_HISTORY, varThreshold=16, detectShadows=False)
    
    counts = {label: 0 for label in PHYSICAL_LABELS}
    active_worms, cross_cooldown = {}, {}
    next_worm_id, frame_idx = 0, 0
    paused = False
    
    base_channel_width = None
    last_valid_grid_data = None
    tripwire_y = 0
    panic_cooldown = 0
    
    print("\n🚀 开始处理视频 (按空格暂停/继续, S截图, Q退出)")
    print("⏳ 正在进行前置预热与背景学习...")
    
    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret: break
            frame_idx += 1
            is_panic_now = False
            
            # ==========================================
            # 1. 动态网格计算 & 熔断探针 (网格宽度检查)
            # ==========================================
            try:
                grid_data = get_interpolated_grid(frame, NUM_CHANNELS, X_MARGIN, wall_ratio=WALL_RATIO)
                
                # 在第30帧正式确认基准网格，并打印各通道像素宽度（仅执行一次）
                if base_channel_width is None and frame_idx >= INIT_FRAME_INDEX:
                    base_channel_width = grid_data['channel_width']
                    print(f"\n✅ 网格初始化完成！基准平均宽度: {base_channel_width:.2f} px")
                    print("📏 各物理通道首帧像素宽度测算结果:")
                    for idx, (c_left, c_right) in enumerate(grid_data['channel_bounds']):
                        if idx < len(PHYSICAL_LABELS):
                            print(f"  ▶ 通道 {PHYSICAL_LABELS[idx]:02d}: {c_right - c_left} px")
                    print("🚀 哨兵系统已全面接管，开始正式监控...\n")
                    
                # 检查网格是否发生崩溃级突变
                if base_channel_width is not None:
                    mutation = abs(grid_data['channel_width'] - base_channel_width) / base_channel_width
                    if mutation > GRID_MUTATION_TOLERANCE:
                        raise ValueError(f"网格突变 {mutation*100:.1f}%")
                        
                last_valid_grid_data = grid_data
                tripwire_y = int(frame.shape[0] * TRIPWIRE_RATIO)
            except Exception as e:
                is_panic_now = True
                if last_valid_grid_data is not None: grid_data = last_valid_grid_data
                else: continue
            
            # ==========================================
            # 2. 目标检测 & 熔断探针 (全屏噪点检查)
            # ==========================================
            if frame_idx > INIT_FRAME_INDEX:
                # 依赖刚刚调优过的 detect_worms 函数
                centroids, fg_mask, noise_ratio, raw_fg = detect_worms(frame, backSub, grid_data, MIN_AREA)
                if noise_ratio > PANIC_NOISE_RATIO:
                    is_panic_now = True
            else:
                # 前 30 帧预热期，快速吸收静态背景
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                backSub.apply(blur, learningRate=0.05)
                raw_fg = None
            
            # ==========================================
            # 3. 状态机分发 (正常工作区 vs 熔断免疫区)
            # ==========================================
            if is_panic_now:
                panic_cooldown = COOLDOWN_FRAMES
            
            if panic_cooldown > 0:
                # ⚠️ 触发熔断保护
                panic_cooldown -= 1
                active_worms.clear()  # 强行清空追踪器，杜绝误数
                cross_cooldown.clear()
                
                # 强制高学习率 (0.1)，迅速把震动后的新墙壁吸纳为背景
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (5, 5), 0)
                backSub.apply(blur, learningRate=0.1) 
                
                display_frame = draw_dashboard(frame, counts, grid_data, {}, tripwire_y, raw_fg, is_panic=True, cooldown_rem=panic_cooldown)
                
            # --- 找到这一行并修改 ---
            elif frame_idx > INIT_FRAME_INDEX:
                # 🟢 正常计数逻辑
                active_worms, next_worm_id, movements, cross_cooldown = update_tracks(centroids, active_worms, next_worm_id, cross_cooldown)
    
                # 💥 关键修改：第一个参数必须是 active_worms
                counts, cross_cooldown = count_crossings(active_worms, counts, grid_data['channel_bounds'], tripwire_y, cross_cooldown)
    
                display_frame = draw_dashboard(frame, counts, grid_data, active_worms, tripwire_y, raw_fg)
            else:
                # 🟡 预热等待
                display_frame = draw_dashboard(frame, counts, grid_data, {}, tripwire_y, raw_fg)
                cv2.putText(display_frame, "WARMING UP...", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 165, 255), 2)

            cv2.imshow("Worm Counter Pro", display_frame)
            
        # 键盘交互监听
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): break
        elif key == ord(' '): paused = not paused
        elif key == ord('s'): cv2.imwrite(f"screenshot_{frame_idx:04d}.png", display_frame)
    
    # ==========================================
    # 4. 实验结束与数据导出
    # ==========================================
    cap.release()
    cv2.destroyAllWindows()
    
    print("\n" + "=" * 50)
    print("📊 最终统计结果")
    print("=" * 50)
    total = sum(counts.values())
    for label in sorted(PHYSICAL_LABELS):
        cnt = counts[label]
        bar = "█" * min(cnt, 50)
        print(f"  通道 {label:02d}: {cnt:4d} 条  {bar}")
    print("-" * 50)
    print(f"  总计: {total} 条线虫")
    print("=" * 50)
    
    # 导出 CSV 文件
    csv_path = video_path.rsplit('.', 1)[0] + '_counts.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['通道编号', '线虫数量'])
        for label in sorted(PHYSICAL_LABELS):
            writer.writerow([label, counts[label]])
        writer.writerow(['总计', total])
    print(f"\n📁 数据已成功导出至: {csv_path}")

if __name__ == "__main__":
    TEST_VIDEO_FILE = "video/video2.mp4" # ⚠️ 记得改成你的实际视频文件名
    process_video(TEST_VIDEO_FILE)