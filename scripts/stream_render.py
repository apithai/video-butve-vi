#!/usr/bin/env python3
"""
Hoạt ảnh nét bút chảy - đầu vào render cho một ảnh

Render một ảnh màu thành video whiteboard "đầu bút lướt dọc quỹ đạo liên tục, đi tới đâu hạ mực tới đó".
Toàn bộ chia làm ba đoạn:
    Phác nét (ink)   đầu bút theo dòng mực vẽ ra bản phác thảo đen
    Tô màu (color)   quay lại đúng quỹ đạo đó, đầu bút đổi sang màu gốc để làm sáng bức tranh
    Dừng hình (gaze) sau khi thu bút thì dừng lại, hiển thị ảnh gốc đầy đủ

Khác với cách làm "nhảy từng ô": bộ render này coi thứ tự vẽ là đường gấp khúc chuyển động của đầu bút,
nội suy giữa các điểm hạ bút liền kề, cọ mực trượt theo đầu bút để hạ mực liên tục, tạo thành dòng nét bút liền mạch.
"""
from __future__ import annotations

import argparse
import datetime
import math
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

# ──────────────────────────────────────────────────────────────
# Định vị tài nguyên
# ──────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_ASSETS_DIR = _SCRIPT_DIR.parent / "assets"
DEFAULT_HAND_PNG = _ASSETS_DIR / "drawing-hand.png"


def _imread_any(path: str | Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """
        Đọc ảnh, tương thích với đường dẫn Windows chứa tiếng Trung/dấu cách hay ký tự không phải ASCII.
        Trước hết dùng np.fromfile đọc byte, rồi đưa cho cv2.imdecode giải mã,
        để tránh vấn đề tương thích của cv2.imread với đường dẫn không phải ASCII.
    """
    raw = np.fromfile(str(path), dtype=np.uint8)
    if raw.size == 0:
        return None
    return cv2.imdecode(raw, flags)


# ──────────────────────────────────────────────────────────────
# Tham số render tập trung một chỗ
# ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Config:
    fps: int = 60                  # Tần số đầu ra cao giúp đầu bút chuyển động giống viết liền mạch hơn
    grid_edge: int = 10            # Lưới nhỏ hơn giúp việc hé lộ bản phác thảo bớt cảm giác khối
    sample_step: int = 2           # Khoảng cách lấy mẫu pixel của quỹ đạo đầu bút
    cap_long_edge: int = 1080      # Giới hạn cạnh dài của ảnh đầu vào
    brush_radius: int = 40         # Bán kính cọ mực tròn ở giai đoạn tô màu
    ink_weight: int = 2            # Trọng số đoạn phác nét: dành thêm thời gian để quan sát nét bút
    color_weight: int = 1          # Trọng số đoạn tô màu
    gaze_seconds: float = 3.0      # Số giây chuẩn của đoạn dừng hình
    ink_threshold: int = 10        # Điểm ảnh có độ xám thấp hơn giá trị này được coi là "nét mực"
    ink_reveal_radius: int = 4     # Bán kính phác thảo mà mỗi đoạn quỹ đạo của đầu bút có thể hé lộ
    target_hand_height: int = 493  # Chiều cao mục tiêu của bàn tay sau khi co giãn (chỉnh theo 1080p)
    # Tọa độ chuẩn hóa (0..1) của đầu bút trong ảnh bàn tay, quyết định điểm hạ mực khớp với pixel nào của ảnh.
    # Sau khi cắt, drawing-hand.png có đầu bút ở góc trên bên trái của ảnh, nên điểm neo lấy (0, 0).
    # Ở đây mô tả điểm tiếp xúc hạ mực thật, chứ không phải khung ngoài của ảnh bàn tay.
    tip_anchor_x: float = 0.0
    tip_anchor_y: float = 0.0
    canvas_hex: str = "#F6F1E3"    # Màu nền canvas
    match_bg: bool = True          # Nhuộm nền ảnh gốc thành màu nền canvas để nền lúc phác nét/tô màu đồng nhất
    match_bg_threshold: int = 28   # Chênh lệch với màu nền ảnh gốc nhỏ hơn giá trị này thì coi là nền (tổng ba kênh BGR)
    steps_per_frame: int = 4       # Số điểm hạ bút chuẩn tiến lên mỗi khung hình
    # ── Dành riêng cho chế độ tô màu contour-wipe ──
    color_fill: str = "contour-wipe"  # Kiểu tô màu: "contour-wipe" quét từ trên xuống nhận biết đường viền (mặc định) | "brush" quét theo quỹ đạo
    wipe_decay: float = 0.86       # Hệ số giảm dần theo hàng đi xuống của trường cản (nửa chu kỳ ≈4.6px)
    wipe_delay_ratio: float = 0.04  # Tỷ lệ pixel bị trừ ở mép tiến tại đường viền (×h, kẹp vào [12,52])
    wipe_blocks: int = 18          # Số lượt đầu bút quét qua lại theo chiều ngang
    # ── Dừng thích ứng ở đoạn phác nét (mô phỏng nhịp "đổi bút lấy hơi") ──
    # pause_mode: "heavy" dừng rõ (mặc định); "auto" tự chia mức theo mật độ nội dung; "off" tắt dừng; "light" dừng ít
    pause_mode: str = "heavy"
    pause_ratio_heavy: float = 0.03   # Tỷ lệ dừng ở mật độ thấp (nhịp chậm): khoảng 3% khung hình dùng để dừng
    pause_ratio_light: float = 0.008  # Tỷ lệ dừng ở mật độ trung bình: khoảng 0,8%
    # Ngưỡng chia mức mật độ: dùng "số khung hình mỗi ô" (frames_per_cell) đo độ dư thời lượng của video so với nội dung.
    # >= heavy_fpc là dư nhiều → mức heavy (dừng nhiều); >= light_fpc là vừa phải → mức light;
    # < light_fpc nội dung dày, thời lượng eo hẹp → không dừng.
    pause_heavy_fpc: float = 0.7
    pause_light_fpc: float = 0.4
    # ── Chế độ đường đi của nét ──
    # ink_path_mode: "grid" nội suy qua tâm các ô lưới (mặc định) | "skeleton" dò pixel theo khung xương
    ink_path_mode: str = "grid"
    skeleton_min_points: int = 8        # Số điểm tối thiểu của một nét khung xương (lọc mảnh vụn)
    skeleton_resample_spacing: float = 2.5  # Khoảng cách lấy mẫu lại của khung xương (pixel)


# ──────────────────────────────────────────────────────────────
# Tiện ích nhỏ
# ──────────────────────────────────────────────────────────────
def _hex_to_bgr(hex_color: str) -> np.ndarray:
    digits = hex_color.lstrip("#")
    if len(digits) != 6:
        raise ValueError(f"Giá trị màu không hợp lệ: {hex_color}")
    r = int(digits[0:2], 16)
    g = int(digits[2:4], 16)
    b = int(digits[4:6], 16)
    return np.array([b, g, r], dtype=np.uint8)


def _bounding_box(mask: np.ndarray) -> tuple[tuple[int, int], tuple[int, int]]:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return (0, 0), (0, 0)
    return (int(xs.min()), int(ys.min())), (int(xs.max()), int(ys.max()))


# ──────────────────────────────────────────────────────────────
# Chia khối các ô mực
# ──────────────────────────────────────────────────────────────
def _to_grid_blocks(image: np.ndarray, edge: int) -> np.ndarray:
    """Cắt ảnh HxW (x C) thành dạng xem khối (số hàng, số cột, edge, edge[, C])."""
    image = np.ascontiguousarray(image)
    h, w = image.shape[:2]
    if h % edge or w % edge:
        raise ValueError(f"Kích thước ảnh {w}x{h} phải là bội số nguyên của {edge}")
    rows, cols = h // edge, w // edge
    if image.ndim == 2:
        return image.reshape(rows, edge, cols, edge).transpose(0, 2, 1, 3)
    return image.reshape(rows, edge, cols, edge, image.shape[2]).transpose(0, 2, 1, 3, 4)


def _active_mask(threshold_map: np.ndarray, edge: int, threshold: int) -> np.ndarray:
    """Những ô lưới nào có nét mực: trong khối có điểm ảnh độ xám thấp hơn ngưỡng thì là đúng."""
    blocks = _to_grid_blocks(threshold_map, edge)
    return np.any(blocks < threshold, axis=(2, 3))


# ──────────────────────────────────────────────────────────────
# Gom cụm dòng mực + đi theo gradient mật độ
# ──────────────────────────────────────────────────────────────
def _label_components(active: np.ndarray) -> tuple[np.ndarray, int]:
    """Gán nhãn thành phần liên thông 8 hướng cho các ô mực, trả về (ảnh nhãn, số thành phần)."""
    n, labels = cv2.connectedComponents(active.astype(np.uint8), connectivity=8)
    return labels, n - 1  # Bỏ nhãn nền 0


def _component_cells(labels: np.ndarray, label: int) -> list[tuple[int, int]]:
    coords = np.argwhere(labels == label)
    return [(int(r), int(c)) for r, c in coords]


def _merge_small_components(
    components: list[list[tuple[int, int]]],
    merge_threshold: int,
) -> list[list[tuple[int, int]]]:
    """
    Gộp các thành phần liên thông nhỏ (số ô ≤ merge_threshold) vào thành phần liên thông lớn gần nhất về không gian.
    Tránh việc vô số mảnh vụn 1-2 ô xen giữa các khối chữ lớn, khiến "vẽ dở một khối chữ đã nhảy đi chỗ khác".
    Nếu không có thành phần lớn nào để gộp vào thì giữ nguyên (không bỏ sót nét mực nào).
    """
    if not components:
        return components
    big = [c for c in components if len(c) > merge_threshold]
    small = [c for c in components if len(c) <= merge_threshold]
    if not small or not big:
        return components

    # Tính trước trọng tâm của từng vùng lớn
    centroids = []
    for cells in big:
        rs = [c[0] for c in cells]
        cs = [c[1] for c in cells]
        centroids.append((sum(rs) / len(rs), sum(cs) / len(cs)))

    # Mỗi mảnh vụn nhỏ gộp vào vùng lớn gần nhất
    merged = [list(cells) for cells in big]  # Sao chép, có thể thêm vào
    for cells in small:
        rs = [c[0] for c in cells]
        cs = [c[1] for c in cells]
        cr = sum(rs) / len(rs)
        cc = sum(cs) / len(cs)
        best = min(
            range(len(big)),
            key=lambda i: (centroids[i][0] - cr) ** 2 + (centroids[i][1] - cc) ** 2,
        )
        merged[best].extend(cells)
    return merged


def _bounds(cells: Sequence[tuple[int, int]]) -> tuple[int, int, int, int]:
    rows = [row for row, _ in cells]
    cols = [col for _, col in cells]
    return min(rows), min(cols), max(rows), max(cols)


def _split_bridge_connected_component(
    cells: list[tuple[int, int]],
    min_side_cells: int = 20,
) -> list[list[tuple[int, int]]]:
    """Split a very wide component when it is connected only by a thin bridge.

    A baseline, arrow, or stray outline can join separate objects into one
    connected component.  Drawing that component with one nearest-neighbour
    walk makes the pen alternate between those objects.  Valleys in the
    vertical ink projection are reliable weak-bridge signals at grid scale.
    """
    if len(cells) < min_side_cells * 2:
        return [cells]

    min_row, min_col, max_row, max_col = _bounds(cells)
    height = max_row - min_row + 1
    width = max_col - min_col + 1
    if width < 16 or height < 10:
        return [cells]

    counts = {col: 0 for col in range(min_col, max_col + 1)}
    for _, col in cells:
        counts[col] += 1
    valley_limit = max(3, int(np.ceil(height * 0.30)))
    edge_guard = 4
    valleys: list[tuple[int, int]] = []
    start: int | None = None
    for col in range(min_col, max_col + 2):
        low = col <= max_col and counts[col] <= valley_limit
        if low and start is None:
            start = col
        elif not low and start is not None:
            end = col - 1
            if (
                end - start + 1 >= 2
                and start > min_col + edge_guard
                and end < max_col - edge_guard
            ):
                valleys.append((start, end))
            start = None
    if not valleys:
        return [cells]

    # Prefer the broadest empty corridor.  It is much less likely to be an
    # internal detail of a character than a one-column dip.
    start, end = max(valleys, key=lambda band: (band[1] - band[0], -band[0]))
    cut = (start + end) // 2
    left = [cell for cell in cells if cell[1] <= cut]
    right = [cell for cell in cells if cell[1] > cut]
    if len(left) < min_side_cells or len(right) < min_side_cells:
        return [cells]
    return (
        _split_bridge_connected_component(left, min_side_cells)
        + _split_bridge_connected_component(right, min_side_cells)
    )


def _split_bridge_connected_components(
    components: list[list[tuple[int, int]]],
) -> list[list[tuple[int, int]]]:
    return [
        piece
        for cells in components
        for piece in _split_bridge_connected_component(cells)
    ]


def _boxes_touch(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
    margin: int = 2,
) -> bool:
    """Whether two component boxes belong to the same visual region."""
    a_top, a_left, a_bottom, a_right = first
    b_top, b_left, b_bottom, b_right = second
    return not (
        a_right + margin < b_left
        or b_right + margin < a_left
        or a_bottom + margin < b_top
        or b_bottom + margin < a_top
    )


def _group_adjacent_stroke_groups(
    groups: list[tuple[str, list[tuple[int, int]]]],
) -> list[list[tuple[str, list[tuple[int, int]]]]]:
    """Keep overlapping label parts and outline pieces in one draw region."""
    regions: list[list[tuple[str, list[tuple[int, int]]]]] = []
    boxes: list[tuple[int, int, int, int]] = []
    for group in groups:
        group_box = _bounds(group[1])
        touching = [index for index, box in enumerate(boxes) if _boxes_touch(group_box, box)]
        if not touching:
            regions.append([group])
            boxes.append(group_box)
            continue
        target = touching[0]
        regions[target].append(group)
        top, left, bottom, right = boxes[target]
        boxes[target] = (
            min(top, group_box[0]), min(left, group_box[1]),
            max(bottom, group_box[2]), max(right, group_box[3]),
        )
        # Merge any regions newly bridged by the expanded box.
        for index in reversed(touching[1:]):
            regions[target].extend(regions.pop(index))
            other = boxes.pop(index)
            top, left, bottom, right = boxes[target]
            boxes[target] = (
                min(top, other[0]), min(left, other[1]),
                max(bottom, other[2]), max(right, other[3]),
            )
    return regions


def classify_stroke_groups(
    active: np.ndarray,
) -> list[tuple[str, list[tuple[int, int]]]]:
    """Classify connected ink regions as a main subject, text, or local contour."""
    labels, count = _label_components(active)
    components = [
        _component_cells(labels, label)
        for label in range(1, count + 1)
    ]
    components = [cells for cells in components if cells]
    if not components:
        return []

    # A long ground line may connect a mountain, a character, and a crowd.
    # Split that weak connection before any region ordering is decided.
    components = _split_bridge_connected_components(components)

    # Gộp mảnh vụn nhỏ vào vùng lớn gần nhất, tránh mảnh vụn làm gián đoạn việc vẽ liên tục các khối chữ lớn
    total_cells = sum(len(c) for c in components)
    merge_threshold = max(3, int(total_cells * 0.005))
    components = _merge_small_components(components, merge_threshold)

    subject_index = max(range(len(components)), key=lambda index: len(components[index]))
    groups: list[tuple[str, list[tuple[int, int]], tuple[int, int, int]]] = []
    for index, cells in enumerate(components):
        min_row, min_col, max_row, max_col = _bounds(cells)
        height = max_row - min_row + 1
        width = max_col - min_col + 1
        density = len(cells) / (height * width)
        if index == subject_index:
            kind, rank = "subject", 0
        elif height >= 2 and width / height >= 2.2 and density >= 0.5:
            kind, rank = "text", 1
        else:
            kind, rank = "contour", 2
        groups.append((kind, cells, (rank, min_row, min_col)))

    groups.sort(key=lambda group: group[2])
    return [(kind, cells) for kind, cells, _ in groups]


def _density_seed(cells: Sequence[tuple[int, int]], radius: int = 2) -> tuple[int, int]:
    """Chọn ô có hàng xóm cục bộ dày nhất làm điểm hạ bút, mô phỏng "hạ bút ở chỗ mực đậm nhất"."""
    cell_set = set(cells)
    best = cells[0]
    best_score = -1
    for (r, c) in cells:
        score = sum(
            1
            for dr in range(-radius, radius + 1)
            for dc in range(-radius, radius + 1)
            if (r + dr, c + dc) in cell_set
        )
        if score > best_score:
            best_score = score
            best = (r, c)
    return best


def _gradient_walk(cells: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    Đi tham lam dẫn hướng bởi gradient mật độ: xuất phát từ ô hạt giống có mật độ cao nhất, mỗi bước chọn
    ô "trong các hàng xóm chưa đi qua, có mật độ cục bộ cao nhất và góc lệch so với hướng đến nhỏ nhất",
    tạo thành nét bút liên tục "bám theo nét mực, ít quay đầu".
    Khi không còn hàng xóm nào với tới được thì nhảy đến ô chưa đi qua gần nhất trên toàn cục rồi đi tiếp.
    """
    if not cells:
        return []

    cell_set = set(cells)
    seed = _density_seed(cells)
    visited: set[tuple[int, int]] = {seed}
    path: list[tuple[int, int]] = [seed]
    current = seed
    prev_dir = (0, 0)

    while len(visited) < len(cells):
        neighbors = [
            (r, c)
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if (dr or dc)
            and (r := current[0] + dr, c := current[1] + dc) in cell_set
            and (r, c) not in visited
        ]
        if neighbors:
            def cost(cell: tuple[int, int]) -> tuple:
                # Hàng xóm càng nhiều càng tốt (dấu âm để lấy nhỏ nhất), thay đổi hướng càng ít càng tốt, cuối cùng sắp xếp ổn định theo vị trí
                local = sum(
                    1
                    for dr in (-1, 0, 1)
                    for dc in (-1, 0, 1)
                    if (cell[0] + dr, cell[1] + dc) in cell_set
                    and (cell[0] + dr, cell[1] + dc) not in visited
                )
                step = (cell[0] - current[0], cell[1] - current[1])
                turn = (step[0] - prev_dir[0]) ** 2 + (step[1] - prev_dir[1]) ** 2
                return (-local, turn, cell[0], cell[1])

            nxt = min(neighbors, key=cost)
        else:
            # Đứt nét: nhảy đến ô chưa đi qua gần nhất
            unvisited = [cell for cell in cells if cell not in visited]
            nxt = min(
                unvisited,
                key=lambda cell: (
                    (cell[0] - current[0]) ** 2 + (cell[1] - current[1]) ** 2,
                    cell[0],
                    cell[1],
                ),
            )

        prev_dir = (nxt[0] - current[0], nxt[1] - current[1])
        path.append(nxt)
        visited.add(nxt)
        current = nxt

    return path


def _nearest_neighbor_order(
    cells: Sequence[tuple[int, int]], seed: tuple[int, int]
) -> list[tuple[int, int]]:
    """Xuất phát từ seed, mỗi bước đi đến ô chưa đi qua gần nhất, tạo thành nét bút liên tục."""
    if not cells:
        return []
    remaining = list(cells)
    ordered: list[tuple[int, int]] = []
    current = seed if seed in remaining else remaining[0]
    while remaining:
        ordered.append(current)
        remaining.remove(current)
        if not remaining:
            break
        current = min(
            remaining,
            key=lambda cell: (cell[0] - ordered[-1][0]) ** 2
            + (cell[1] - ordered[-1][1]) ** 2,
        )
    return ordered


def _text_scan_order(
    cells: Sequence[tuple[int, int]], segment_cols: int = 4
) -> list[tuple[int, int]]:
    """
    Cách vẽ chuyên cho vùng chữ: quét theo từng đoạn theo chiều ngang, mô phỏng viết chữ.
    Chia các ô theo cột thành nhiều đoạn (mỗi đoạn rộng segment_cols cột), giữa các đoạn đi theo cột từ trái sang phải;
    trong đoạn dùng láng giềng gần nhất đi liên tục dọc theo nét mực (thay vì quét từng hàng kiểu hàng rào), tránh cảm giác "quay lại bù nét":
    vẽ qua một khối chưa đầy, nhảy sang đoạn kế rồi lại bắt đầu từ đỉnh.
    """
    if not cells:
        return []
    if segment_cols < 1:
        segment_cols = 1
    left_col = min(col for _, col in cells)
    # Chia vào các nhóm theo "cột bắt đầu // segment_cols", nhóm có số nhỏ (bên trái) vẽ trước
    buckets: dict[int, list[tuple[int, int]]] = {}
    for cell in cells:
        bucket_key = (cell[1] - left_col) // segment_cols
        buckets.setdefault(bucket_key, []).append(cell)

    ordered: list[tuple[int, int]] = []
    prev_tail: tuple[int, int] | None = None
    for key in sorted(buckets):
        seg_cells = buckets[key]
        # Điểm bắt đầu của đoạn: cố gắng gần lối ra của đoạn trước, giảm nhảy bút giữa các đoạn
        if prev_tail is not None:
            seed = min(
                seg_cells,
                key=lambda cell: (cell[0] - prev_tail[0]) ** 2
                + (cell[1] - prev_tail[1]) ** 2,
            )
        else:
            seed = min(seg_cells, key=lambda cell: (cell[0], cell[1]))
        seg_order = _nearest_neighbor_order(seg_cells, seed)
        ordered.extend(seg_order)
        prev_tail = seg_order[-1]
    return ordered


def _order_stream_by_kind(
    kind: str, cells: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Chọn cách vẽ theo loại vùng: chữ quét ngang theo đoạn, chủ thể/đường viền đi theo mật độ."""
    if kind == "text":
        return _text_scan_order(cells)
    return _gradient_walk(cells)


def _chain_region_paths(
    groups: list[tuple[str, list[tuple[int, int]]]],
) -> list[tuple[int, int]]:
    """Finish every component in one visual region before leaving it."""
    paths = [_order_stream_by_kind(kind, cells) for kind, cells in groups]
    remaining = [path for path in paths if path]
    ordered: list[tuple[int, int]] = []
    tail: tuple[int, int] | None = None
    while remaining:
        if tail is None:
            pick_index = 0  # groups retain subject/text/contour priority.
        else:
            pick_index = min(
                range(len(remaining)),
                key=lambda index: min(
                    (remaining[index][0][0] - tail[0]) ** 2
                    + (remaining[index][0][1] - tail[1]) ** 2,
                    (remaining[index][-1][0] - tail[0]) ** 2
                    + (remaining[index][-1][1] - tail[1]) ** 2,
                ),
            )
        path = remaining.pop(pick_index)
        if tail is not None and len(path) > 1:
            head_distance = (path[0][0] - tail[0]) ** 2 + (path[0][1] - tail[1]) ** 2
            end_distance = (path[-1][0] - tail[0]) ** 2 + (path[-1][1] - tail[1]) ** 2
            if end_distance < head_distance:
                path.reverse()
        ordered.extend(path)
        tail = path[-1]
    return ordered


def cluster_ink_streams(active: np.ndarray) -> list[list[tuple[int, int]]]:
    """
    Gom các ô mực theo ngữ nghĩa thành nhiều dòng mực: chủ thể (subject) → chữ (text) → đường viền cục bộ (contour),
    trong mỗi dòng chọn cách vẽ theo loại (chữ quét theo đoạn, còn lại đi theo mật độ);
    giữa các dòng mực nối động theo "láng giềng gần nhất từ lối ra đến lối vào", khi cần thì đảo ngược cả dòng, giảm nhảy bút.
    Trả về nhiều dòng nét đã được nối và sắp xếp xong.
    """
    if not active.any():
        return []
    groups = classify_stroke_groups(active)
    # A stream is now a complete visual region, not merely one connected
    # component.  Thus a label's border, its characters, and its arrow cannot
    # be interrupted by a different object that happens to be closer.
    regions = _group_adjacent_stroke_groups(groups)
    streams = [_chain_region_paths(region) for region in regions]
    streams = [s for s in streams if s]
    if not streams:
        return []

    # Nối: chủ thể (nét đầu tiên) mở đầu, sau đó mỗi lần chọn dòng mực có lối vào gần lối ra hiện tại nhất,
    # và tùy trường hợp đảo ngược cả dòng mực đó, để điểm đầu của nó gần lối ra của nét trước hơn.
    ordered: list[list[tuple[int, int]]] = []
    remaining = list(streams)
    tail: tuple[int, int] | None = None
    while remaining:
        if tail is None:
            pick_idx = 0  # classify đã xếp chủ thể lên đầu
        else:
            def dist_to_tail(stream: list[tuple[int, int]]) -> int:
                head = stream[0]
                return (head[0] - tail[0]) ** 2 + (head[1] - tail[1]) ** 2
            pick_idx = min(range(len(remaining)), key=lambda i: dist_to_tail(remaining[i]))
        pick = remaining.pop(pick_idx)
        # Tùy trường hợp đảo ngược: nếu đuôi gần điểm cuối của pick hơn điểm đầu thì đảo ngược
        if tail is not None and len(pick) > 1:
            head = pick[0]
            end = pick[-1]
            d_end = (end[0] - tail[0]) ** 2 + (end[1] - tail[1]) ** 2
            d_head = (head[0] - tail[0]) ** 2 + (head[1] - tail[1]) ** 2
            if d_end < d_head:
                pick = pick[::-1]
        ordered.append(pick)
        tail = pick[-1]
    return ordered


def flatten_streams(streams: list[list[tuple[int, int]]]) -> list[tuple[int, int]]:
    return [cell for stream in streams for cell in stream]


# ──────────────────────────────────────────────────────────────
# Đầu bút / lớp phủ bàn tay
# ──────────────────────────────────────────────────────────────
def _load_hand(path: Path, target_h: int) -> tuple[np.ndarray, np.ndarray] | None:
    """
    Đọc ảnh bàn tay và co giãn theo tỷ lệ đến chiều cao mục tiêu.
    Ưu tiên dùng kênh alpha làm mặt nạ; không có alpha thì quay về cách dò "gần trắng là nền".
    Trả về (BGR bàn tay, mặt nạ chuẩn hóa [0..1]), thất bại thì trả về None.
    """
    if not path.exists():
        return None
    raw = _imread_any(path, cv2.IMREAD_UNCHANGED)
    if raw is None:
        return None

    if raw.ndim == 3 and raw.shape[2] == 4:
        hand = raw[:, :, :3]
        mask = raw[:, :, 3]
    else:
        hand = raw
        gray = cv2.cvtColor(hand, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)

    # Cắt về vùng hữu hiệu
    (x0, y0), (x1, y1) = _bounding_box(mask)
    if x1 <= x0 or y1 <= y0:
        return None
    hand = hand[y0:y1 + 1, x0:x1 + 1]
    mask = mask[y0:y1 + 1, x0:x1 + 1]

    scale = target_h / hand.shape[0]
    new_w = max(1, int(round(hand.shape[1] * scale)))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    hand = cv2.resize(hand, (new_w, target_h), interpolation=interp)
    mask = cv2.resize(mask, (new_w, target_h), interpolation=interp)
    mask = mask.astype(np.float32) / 255.0

    # Tô đen vùng ngoài mặt nạ để tiện trộn theo mặt nạ về sau
    hand[mask <= 0] = 0
    return hand, mask


def _procedural_tip(target_h: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Đầu bút dự phòng: vẽ bằng lập trình một cây bút dạ (thân bút chuyển sắc + đầu tròn viền mềm + bóng đổ).
    Không phụ thuộc ảnh bên ngoài nào, thiếu ảnh bàn tay vẫn xuất được hình.
    """
    w = max(1, int(target_h * 0.34))
    h = target_h
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    # Bóng đổ: một dải tối lệch đi, làm mềm rồi lót phía dưới
    shadow = np.zeros((h, w), dtype=np.uint8)
    cv2.rectangle(shadow, (3, int(h * 0.06)), (w - 2, int(h * 0.62)), 90, thickness=-1)
    shadow = cv2.GaussianBlur(shadow, (15, 15), 0)
    rgba[:, :, 3] = shadow

    # Thân bút: chuyển sắc dọc từ sáng sang tối
    for y in range(h):
        t = y / max(1, h - 1)
        shade = int(220 - 130 * t)
        rgba[y, :, 0:3] = (shade, shade, shade + 10)
    cv2.rectangle(rgba, (4, int(h * 0.04)), (w - 4, int(h * 0.58)), (0, 0, 0), thickness=1)

    # Đầu bút tròn (màu ấm, mô phỏng mực dầu)
    tip_cy = int(h * 0.70)
    cv2.circle(rgba, (w // 2, tip_cy), max(3, w // 4), (70, 90, 230), thickness=-1)

    # Dùng đầu tròn + đường viền ngoài của thân bút để ghép mặt nạ alpha
    body_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.rectangle(body_mask, (3, int(h * 0.04)), (w - 3, tip_cy), 255, thickness=-1)
    cv2.circle(body_mask, (w // 2, tip_cy), max(3, w // 4), 255, thickness=-1)
    body_mask = cv2.GaussianBlur(body_mask, (7, 7), 0)

    hand = rgba[:, :, :3]
    mask = np.maximum(rgba[:, :, 3], body_mask).astype(np.float32) / 255.0
    hand[mask <= 0] = 0
    return hand, mask


class TipOverlay:
    """Dán đầu bút/bàn tay lên canvas, để "điểm neo đầu bút" chỉ định khớp với điểm hạ mực, có trộn alpha."""

    def __init__(
        self,
        hand: np.ndarray,
        mask: np.ndarray,
        tip_anchor_x: float = 0.0,
        tip_anchor_y: float = 0.0,
    ) -> None:
        self.hand = hand
        self.mask = mask
        self.h, self.w = hand.shape[:2]
        self.mask_inv = 1.0 - mask
        # Tọa độ pixel của đầu bút trong ảnh (điểm hạ mực phải căn khớp với nó)
        # Map normalized anchors exactly onto the source image's pixel range.
        self.tip_px = int(round((self.w - 1) * np.clip(tip_anchor_x, 0.0, 1.0)))
        self.tip_py = int(round((self.h - 1) * np.clip(tip_anchor_y, 0.0, 1.0)))

    def stamp(self, canvas: np.ndarray, x: int, y: int) -> np.ndarray:
        """Căn điểm neo đầu bút của ảnh khớp với tọa độ canvas (x, y) (tức điểm hạ mực)."""
        # Góc trên bên trái của ảnh = điểm hạ mực - độ lệch của đầu bút
        anchor_x = x - self.tip_px
        anchor_y = y - self.tip_py
        h_canvas, w_canvas = canvas.shape[:2]

        x0 = max(0, anchor_x)
        y0 = max(0, anchor_y)
        x1 = min(w_canvas, anchor_x + self.w)
        y1 = min(h_canvas, anchor_y + self.h)
        if x1 <= x0 or y1 <= y0:
            return canvas

        sx0 = x0 - anchor_x
        sy0 = y0 - anchor_y
        sx1 = sx0 + (x1 - x0)
        sy1 = sy0 + (y1 - y0)

        region = canvas[y0:y1, x0:x1]
        hand_region = self.hand[sy0:sy1, sx0:sx1]
        mask_region = self.mask[sy0:sy1, sx0:sx1]
        inv_region = self.mask_inv[sy0:sy1, sx0:sx1]

        for c in range(3):
            region[:, :, c] = (
                region[:, :, c] * inv_region + hand_region[:, :, c] * mask_region
            )
        canvas[y0:y1, x0:x1] = region
        return canvas


# ──────────────────────────────────────────────────────────────
# Cọ mực
# ──────────────────────────────────────────────────────────────
def _feathered_disk(radius: int) -> np.ndarray:
    """Tạo mặt nạ tròn bán kính r, viền mờ kiểu Gauss, miền giá trị 0..1."""
    y, x = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    dist = np.sqrt(x * x + y * y).astype(np.float32)
    return np.clip(1.0 - (dist - radius * 0.75) / (radius * 0.25), 0.0, 1.0)


# ──────────────────────────────────────────────────────────────
# Công cụ tô màu contour-wipe
# ──────────────────────────────────────────────────────────────
def _ease_in_out_sine(t: float | np.ndarray) -> float | np.ndarray:
    """Làm mượt kiểu sin: đầu và cuối chậm, giữa nhanh. Đầu vào là số vô hướng hoặc mảng, đầu ra cùng dạng."""
    return -(np.cos(np.pi * t) - 1.0) / 2.0


def _build_wipe_wave(width: int) -> np.ndarray:
    """
    Tính trước đường biên sóng sin hai tần số, để mép hé lộ không phải đường thẳng phẳng mà gợn sóng như nước.
    Trả về mảng (W,) float32, miền giá trị xấp xỉ [-1.35, 1.35].
    """
    wave_px1 = max(24.0, width / 20.0)
    wave_px2 = max(8.0, width / 72.0)
    xs = np.arange(width, dtype=np.float32)
    return np.sin(xs / wave_px1) + 0.35 * np.sin(xs / wave_px2 + 1.7)


# ──────────────────────────────────────────────────────────────
# Dò nét ở mức khung xương (chuyển từ preprocess.py của whiteboard-video-engine)
# Làm mảnh Zhang-Suen → dò cạnh thẳng nhất theo 8 láng giềng → nét có thứ tự ở mức pixel
# ──────────────────────────────────────────────────────────────
_SKEL_NEIGHBORS_8 = [
    (-1, -1), (0, -1), (1, -1),
    (-1, 0),           (1, 0),
    (-1, 1),  (0, 1),  (1, 1),
]


def _zhang_suen_skeleton(mask: np.ndarray, max_iterations: int = 160) -> np.ndarray:
    """
    Làm mảnh Zhang-Suen hai vòng lặp con, làm mảnh mặt nạ tiền cảnh nhị phân thành khung xương rộng 1px.
    Đầu vào: mảng hai chiều bool/uint8 (True/1 = nét bút tiền cảnh).
    Đầu ra: ảnh khung xương bool, cùng hình dạng.
    """
    img = np.pad(mask.astype(np.uint8), 1, mode="constant")
    for _ in range(max_iterations):
        changed = False
        for step in (0, 1):
            p2, p3, p4 = img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:]
            p5, p6, p7 = img[2:, 2:], img[2:, 1:-1], img[2:, :-2]
            p8, p9 = img[1:-1, :-2], img[:-2, :-2]
            center = img[1:-1, 1:-1]
            neighbors = [p2, p3, p4, p5, p6, p7, p8, p9]
            # Số lần chuyển 0→1 (vòng quanh theo chiều kim đồng hồ)
            transitions = sum(
                (neighbors[i] == 0) & (neighbors[(i + 1) % 8] == 1) for i in range(8)
            )
            count = sum(neighbors)
            if step == 0:
                marker = (
                    (center == 1) & (count >= 2) & (count <= 6)
                    & (transitions == 1)
                    & ((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0)
                )
            else:
                marker = (
                    (center == 1) & (count >= 2) & (count <= 6)
                    & (transitions == 1)
                    & ((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0)
                )
            if np.any(marker):
                center[marker] = 0
                changed = True
        if not changed:
            break
    return img[1:-1, 1:-1].astype(bool)


def _skel_neighbors(skel: np.ndarray, point: tuple[int, int]) -> list[tuple[int, int]]:
    """
    Trả về các láng giềng 8 hướng hợp lệ của điểm khung xương point.
    Mấu chốt: khi giữa láng giềng chéo và điểm hiện tại đã có cầu trực giao thì bỏ qua láng giềng chéo đó,
    tránh các nét vụn hình tam giác ở chỗ giao chữ T/chữ thập, đồng thời giữ lại đường tâm chéo thuần túy thật sự.
    """
    x, y = point
    h, w = skel.shape
    result: list[tuple[int, int]] = []
    for dx, dy in _SKEL_NEIGHBORS_8:
        nx, ny = x + dx, y + dy
        if not (0 <= nx < w and 0 <= ny < h and skel[ny, nx]):
            continue
        if dx != 0 and dy != 0 and (skel[y, nx] or skel[ny, x]):
            continue  # Cầu trực giao đã nối, bỏ qua đường chéo thừa
        result.append((nx, ny))
    return result


def _edge_key(a: tuple[int, int], b: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    """Chuẩn hóa cạnh vô hướng: (A,B) và (B,A) ánh xạ về cùng một key."""
    return (a, b) if a <= b else (b, a)


def _choose_next(
    prev: tuple[int, int],
    cur: tuple[int, int],
    candidates: list[tuple[int, int]],
    visited_edges: set,
) -> tuple[int, int] | None:
    """
    Tại điểm giao chọn "cạnh chưa đi qua thẳng nhất" để đi tiếp.
    Dùng độ tương đồng cosine giữa hướng đi hiện tại và hướng ứng viên để đo "độ thẳng", lấy giá trị lớn nhất.
    """
    fresh = [p for p in candidates if _edge_key(cur, p) not in visited_edges and p != prev]
    if not fresh:
        return None
    vx, vy = cur[0] - prev[0], cur[1] - prev[1]
    vlen = math.hypot(vx, vy)
    return max(
        fresh,
        key=lambda p: (
            (vx * (p[0] - cur[0]) + vy * (p[1] - cur[1]))
            / (vlen * math.hypot(p[0] - cur[0], p[1] - cur[1]) or 1.0)
        ),
    )


def trace_8connected(skel: np.ndarray, min_points: int = 8) -> list[list[tuple[int, int]]]:
    """
    Dò khung xương 1px thành chuỗi nét có thứ tự.

    - Ưu tiên điểm xuất phát: điểm đầu mút bậc=1 → điểm giao bậc>2 → các điểm khác
    - Tại điểm giao đi tiếp theo cạnh chưa đi qua thẳng nhất (thay vì mỗi nhánh đứt thành một nét ngắn)
    - Dùng tập cạnh vô hướng đánh dấu đã đi (pixel có thể dùng lại, cạnh không được đi lặp)
    - Gặp ngõ cụt (không còn cạnh mới) thì dừng, các nhánh còn lại do điểm xuất phát sau bù vào
    - Mảnh vụn có độ dài < min_points bị loại

    Trả về list[list[(x,y)]], mỗi phần tử là tọa độ pixel có thứ tự theo hướng của nét.
    """
    ys, xs = np.nonzero(skel)
    points = [(int(x), int(y)) for x, y in zip(xs, ys)]
    if not points:
        return []
    degrees = {p: len(_skel_neighbors(skel, p)) for p in points}
    starts = (
        [p for p in points if degrees[p] == 1]
        + [p for p in points if degrees[p] > 2]
        + points
    )
    visited_edges: set = set()
    strokes: list[list[tuple[int, int]]] = []
    for start in starts:
        for nb in _skel_neighbors(skel, start):
            edge = _edge_key(start, nb)
            if edge in visited_edges:
                continue
            path = [start]
            prev, cur = start, nb
            visited_edges.add(edge)
            while True:
                path.append(cur)
                next_pt = _choose_next(prev, cur, _skel_neighbors(skel, cur), visited_edges)
                if next_pt is None:
                    break
                visited_edges.add(_edge_key(cur, next_pt))
                prev, cur = cur, next_pt
            if len(path) >= min_points:
                strokes.append(path)
    return strokes


# ── Hậu xử lý nét khung xương (lấy mẫu lại + làm mượt + sắp xếp) ──
def _stroke_cumulative_length(points: list[tuple[float, float]]) -> list[float]:
    """Độ dài cung tích lũy tại mỗi điểm [0, d01, d012, ...]."""
    cum = [0.0]
    for a, b in zip(points, points[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return cum


def _resample_stroke_points(
    points: list[tuple[float, float]], spacing: float
) -> list[tuple[float, float]]:
    """Lấy mẫu lại cách đều theo chiều dài cung với khoảng cách spacing, khử răng cưa pixel."""
    if len(points) < 2:
        return list(points)
    cum = _stroke_cumulative_length(points)
    total = cum[-1]
    if total < spacing:
        return [points[0], points[-1]]
    n = max(2, int(round(total / spacing)))
    result: list[tuple[float, float]] = []
    for i in range(n + 1):
        target = total * i / n
        # Định vị bằng tìm kiếm nhị phân
        lo, hi = 0, len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < target:
                lo = mid + 1
            else:
                hi = mid
        if lo == 0:
            result.append(points[0])
            continue
        seg_start = cum[lo - 1]
        seg_len = cum[lo] - seg_start
        t = (target - seg_start) / seg_len if seg_len > 0 else 0.0
        ax, ay = points[lo - 1]
        bx, by = points[lo]
        result.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    return result


def _chaikin_smooth(
    points: list[tuple[float, float]], iterations: int = 1
) -> list[tuple[float, float]]:
    """Làm mượt cắt góc Chaikin: mỗi đoạn thay bằng hai điểm 0.25/0.75, giữ nguyên điểm đầu và cuối."""
    pts = list(points)
    for _ in range(iterations):
        if len(pts) < 3:
            break
        smoothed = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            smoothed.append((a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25))
            smoothed.append((a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75))
        smoothed.append(pts[-1])
        pts = smoothed
    return pts


def _order_skeleton_strokes(strokes: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """
    Sắp xếp nét: từ trên xuống dưới, từ trái sang phải, nét dài ưu tiên.
    Bản đơn giản của ①order_strokes: dùng góc trên bên trái của khung bao + độ dài âm làm thứ tự từ điển.
    """
    def sort_key(s):
        if not s:
            return (0, 0, 0, 0)
        xs = [p[0] for p in s]
        ys = [p[1] for p in s]
        length = _stroke_cumulative_length(s)[-1]
        return (min(ys) // 12, min(xs), min(ys), -length)
    return sorted(strokes, key=sort_key)


# ──────────────────────────────────────────────────────────────
# Thời lượng / chia đoạn
# ──────────────────────────────────────────────────────────────
@dataclass
class PhasePlan:
    ink_frames: int
    color_frames: int
    gaze_frames: int
    ratio_label: str


def plan_phases(total_ms: int, cfg: Config) -> PhasePlan:
    """
    Chia tổng thời lượng thành ba đoạn: phác nét/tô màu/dừng hình.
    Đoạn dừng hình trước hết dùng số giây chuẩn làm chỗ giữ, thời lượng còn lại chia cho phác nét và tô màu theo trọng số;
    nếu phần còn lại không chia hết cho tổng trọng số thì phần dư bù cho đoạn dừng hình, tránh mất độ chính xác.
    """
    weight_sum = cfg.ink_weight + cfg.color_weight
    gaze_ms = int(cfg.gaze_seconds * 1000)
    anim_ms = total_ms - gaze_ms
    remainder = anim_ms % weight_sum
    if remainder:
        anim_ms -= remainder
        gaze_ms += remainder

    ink_frames = round(anim_ms * cfg.ink_weight / weight_sum * cfg.fps / 1000)
    color_frames = round(anim_ms * cfg.color_weight / weight_sum * cfg.fps / 1000)
    gaze_frames = round(gaze_ms * cfg.fps / 1000)
    if ink_frames <= 0 and color_frames <= 0:
        ink_frames = color_frames = 0
    return PhasePlan(ink_frames, color_frames, gaze_frames, f"{cfg.ink_weight}:{cfg.color_weight}")


# ──────────────────────────────────────────────────────────────
# Thân chính của bộ render
# ──────────────────────────────────────────────────────────────
class StreamBoardRenderer:
    """Giữ toàn bộ trạng thái của một lần render, các phương thức gắn trên thực thể."""

    def __init__(
        self,
        image_bgr: np.ndarray,
        cfg: Config,
        hand_png: Path | None,
        bare_tip: bool,
    ) -> None:
        self.cfg = cfg
        self.canvas_bgr = _hex_to_bgr(cfg.canvas_hex)

        # Tính kích thước đầu ra: cạnh dài giới hạn ở cap, và căn theo bội số chẵn của grid_edge (mã hóa yêu cầu số chẵn)
        h0, w0 = image_bgr.shape[:2]
        scale = cfg.cap_long_edge / max(h0, w0)
        w = int(round(w0 * scale))
        h = int(round(h0 * scale))
        align = cfg.grid_edge if cfg.grid_edge % 2 == 0 else cfg.grid_edge * 2
        w = (w // align) * align
        h = (h // align) * align
        self.out_w = max(align, w)
        self.out_h = max(align, h)

        self.color_img = cv2.resize(image_bgr, (self.out_w, self.out_h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(self.color_img, cv2.COLOR_BGR2GRAY)
        self.thresh_map = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 10
        )
        self.active = _active_mask(self.thresh_map, cfg.grid_edge, cfg.ink_threshold)
        self.grid_blocks = _to_grid_blocks(self.thresh_map, cfg.grid_edge)
        self.ink_pixels = self.thresh_map < cfg.ink_threshold
        self.ink_paint = np.repeat(self.thresh_map[:, :, None], 3, axis=2).astype(np.float32)

        # Nhuộm nền ảnh gốc thành màu nền canvas (chỉ ảnh hưởng color_img, không đụng ink_pixels / ink_paint).
        # Như vậy nền ở giai đoạn tô màu/dừng hình đồng nhất với giai đoạn phác nét (bản phác thảo), tránh màu nền nhảy đột ngột.
        # Đặt sau khi ink_pixels đã tính xong, chất lượng bản phác thảo hoàn toàn không bị ảnh hưởng.
        if cfg.match_bg:
            self._match_original_background()

        # Gom cụm trong không gian ô (đường đi nét của chế độ grid + trường cản contour-wipe vẫn cần)
        self.ink_streams = cluster_ink_streams(self.active)

        # Đường đi của nét: theo ink_path_mode chọn grid (nội suy qua tâm ô) hoặc skeleton (dò khung xương)
        if cfg.ink_path_mode == "skeleton":
            self.skeleton_strokes = self._build_skeleton_path()
            if self.skeleton_strokes:
                self.stroke_path = [pt for stroke in self.skeleton_strokes for pt in stroke]
            else:
                # Dò khung xương không có nét: thật sự quay về đường đi tâm ô, chứ không để lại một path rỗng
                self.stroke_path = flatten_streams(self.ink_streams)
        else:
            self.skeleton_strokes = []
            self.stroke_path = flatten_streams(self.ink_streams)

        # Canvas (dùng bộ đệm số thực để cọ mực cộng dồn trộn dễ dàng)
        self.drawn = np.zeros((self.out_h, self.out_w, 3), dtype=np.float32)
        self.drawn[...] = self.canvas_bgr.astype(np.float32)

        # Lớp phủ đầu bút
        self.tip: TipOverlay | None = None
        if not bare_tip:
            hand_data = _load_hand(hand_png, cfg.target_hand_height) if hand_png else None
            tip_anchor_x = cfg.tip_anchor_x
            tip_anchor_y = cfg.tip_anchor_y
            if hand_data is None:
                hand_data = _procedural_tip(cfg.target_hand_height)
                tip_anchor_x = 0.5
                tip_anchor_y = 0.70
            self.tip = TipOverlay(
                hand_data[0], hand_data[1],
                tip_anchor_x=tip_anchor_x,
                tip_anchor_y=tip_anchor_y,
            )

    # ── Nhuộm nền ảnh gốc thành màu nền canvas (chỉ ảnh hưởng color_img, không đụng nét mực phác thảo) ──
    def _match_original_background(self) -> None:
        """
        Lấy mẫu bốn góc ảnh gốc làm màu nền chuẩn, thay các điểm ảnh chênh lệch < ngưỡng bằng canvas_hex.
        Làm cho nền ở giai đoạn tô màu/dừng hình đồng nhất với giai đoạn phác nét (bản phác thảo), tránh màu nền nhảy đột ngột.
        Phần nội dung có màu (chênh lệch lớn so với nền) giữ nguyên màu gốc, không bị ảnh hưởng.
        """
        img = self.color_img
        h, w = img.shape[:2]
        margin = max(3, min(h, w) // 50)
        samples = [
            img[:margin, :margin], img[:margin, -margin:],
            img[-margin:, :margin], img[-margin:, -margin:],
        ]
        bg_color = np.median(np.concatenate([s.reshape(-1, 3) for s in samples]), axis=0)
        diff = np.abs(img.astype(np.int16) - bg_color.astype(np.int16)).sum(axis=2)
        bg_mask = diff < self.cfg.match_bg_threshold
        img[bg_mask] = self.canvas_bgr

    # ── Điểm tâm của nét (tọa độ pixel) ──
    def _cell_center(self, cell: tuple[int, int]) -> tuple[int, int]:
        r, c = cell
        e = self.cfg.grid_edge
        return (c * e + e // 2, r * e + e // 2)  # (x, y)

    # ── Đường đi nét ở mức khung xương (làm mảnh Zhang-Suen + dò cạnh thẳng nhất theo 8 láng giềng) ──
    def _build_skeleton_path(self) -> list[list[tuple[int, int]]]:
        """
        Dùng dò khung xương để tạo chuỗi nét có thứ tự ở mức pixel, thay cho nội suy qua tâm ô lưới.
        Đầu bút đi theo khung xương thật, bám sát nét của ảnh gốc hơn so với tâm ô lưới;
        tại điểm giao đi tiếp theo cạnh thẳng nhất, tránh các nét vụn hình tam giác.
        """
        cfg = self.cfg
        skel = _zhang_suen_skeleton(self.ink_pixels, max_iterations=160)
        raw_strokes = trace_8connected(skel, min_points=cfg.skeleton_min_points)
        if not raw_strokes:
            print("  [warn] Dò khung xương không có nét, quay về đường đi tâm ô")
            return []

        spacing = cfg.skeleton_resample_spacing
        processed: list[list[tuple[int, int]]] = []
        for stroke in raw_strokes:
            pts = [(float(x), float(y)) for x, y in stroke]
            pts = _resample_stroke_points(pts, spacing)
            pts = _chaikin_smooth(pts, iterations=1)
            pts = _resample_stroke_points(pts, spacing)
            if len(pts) >= 2 and _stroke_cumulative_length(pts)[-1] > 2.0:
                processed.append([(int(round(x)), int(round(y))) for x, y in pts])

        processed = _order_skeleton_strokes(processed)
        total_pts = sum(len(s) for s in processed)
        print(f"  Dò khung xương: {len(processed)} nét, {total_pts} điểm lấy mẫu")
        return processed

    # ── Trường cản contour-wipe (dựng lười, dùng lại trong cả giai đoạn tô màu) ──
    def _build_resistance_field(self) -> np.ndarray:
        """
        Dùng nét mực phác thảo dựng "trường cản": tại đường viền lực cản ≈1, xuống phía dưới từng hàng giảm theo hàm mũ với decay.
        Mép hé lộ gặp lực cản cao thì bị trừ số pixel, nhờ đó "kẹt lại ở đường viền trước, rồi chậm rãi vượt qua".

        Trường cản tĩnh trong suốt quá trình, không phụ thuộc tiến độ tô màu, nên chỉ tính một lần rồi lưu vào self._resistance.
        """
        if getattr(self, "_resistance", None) is not None:
            return self._resistance

        h, w = self.out_h, self.out_w
        cfg = self.cfg

        # 1) Ảnh nhị phân của nét mực (uint8 0/255)
        ink_u8 = (self.ink_pixels.astype(np.uint8)) * 255

        # 2) Giãn nở: phần tử cấu trúc tròn làm đường viền dày lên, tạo dải chắn
        spread = int(np.clip(min(w, h) // 64, 3, 17))
        if spread % 2 == 0:  # Bán kính phần tử cấu trúc phải là số lẻ dương
            spread = max(3, spread - 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (spread, spread))
        dilated = cv2.dilate(ink_u8, kernel, iterations=1)

        # 3) Làm mờ Gauss: biến cạnh cứng thành dải chuyển sắc (bán kính phải là số lẻ dương)
        blur_r = max(1, int(round(min(w, h) / 220.0)))
        if blur_r % 2 == 0:
            blur_r += 1
        resistance = cv2.GaussianBlur(dilated, (blur_r, blur_r), 0).astype(np.float32)

        # 4) Chuẩn hóa về [0,1]
        peak = float(resistance.max())
        if peak > 1e-6:
            resistance /= peak
        else:
            # Không có nét mực (ảnh toàn trắng): trường cản luôn bằng 0, contour-wipe thoái hóa thành quét thẳng
            resistance = np.zeros((h, w), dtype=np.float32)

        # 5) Lan truyền nhân quả giảm decay theo từng hàng đi xuống: để mỗi đường viền đổ xuống phía dưới một cái bóng giảm theo hàm mũ
        decay = cfg.wipe_decay
        for row in range(1, h):
            resistance[row] = np.maximum(resistance[row], resistance[row - 1] * decay)

        self._resistance = resistance
        return resistance

    # ── Chấm một "điểm mực" tại điểm hạ bút: giai đoạn phác thảo chấm ảnh ngưỡng, giai đoạn tô màu chấm màu gốc ──
    def _reveal_ink_segment(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> None:
        """Reveal only the original line-art pixels touched by one pen movement."""
        segment = np.zeros((self.out_h, self.out_w), dtype=np.uint8)
        thickness = max(1, self.cfg.ink_reveal_radius * 2 + 1)
        cv2.line(segment, start, end, 255, thickness=thickness, lineType=cv2.LINE_AA)
        revealed = (segment > 0) & self.ink_pixels
        self.drawn[revealed] = self.ink_paint[revealed]

    def _ink_stamp(self, cell: tuple[int, int]) -> None:
        r, c = cell
        e = self.cfg.grid_edge
        block = self.grid_blocks[r, c]
        ink_region = block < self.cfg.ink_threshold
        # Ảnh ngưỡng là đơn kênh, sao chép sang canvas ba kênh
        paint = np.repeat(block[:, :, None], 3, axis=2)
        target = self.drawn[r * e:r * e + e, c * e:c * e + e]
        target[ink_region] = paint[ink_region]

    def _color_stamp(self, px: int, py: int, disk: np.ndarray) -> None:
        radius = self.cfg.brush_radius
        h, w = self.out_h, self.out_w
        y0, y1 = max(0, py - radius), min(h, py + radius + 1)
        x0, x1 = max(0, px - radius), min(w, px + radius + 1)
        if y1 <= y0 or x1 <= x0:
            return
        by0, by1 = y0 - (py - radius), disk.shape[0] - ((py + radius + 1) - y1)
        bx0, bx1 = x0 - (px - radius), disk.shape[1] - ((px + radius + 1) - x1)
        m = disk[by0:by1, bx0:bx1]
        inv = 1.0 - m
        target = self.drawn[y0:y1, x0:x1]
        source = self.color_img[y0:y1, x0:x1].astype(np.float32)
        for ch in range(3):
            target[:, :, ch] = target[:, :, ch] * inv + source[:, :, ch] * m

    # ── Ghi vài khung hình từ ảnh chụp canvas hiện tại (kèm đầu bút) ──
    def _snapshot_with_tip(self, px: int, py: int) -> np.ndarray:
        snap = self.drawn.astype(np.uint8)  # astype đã trả về mảng mới, không cần copy thêm
        if self.tip is not None:
            self.tip.stamp(snap, px, py)
        return snap

    def _build_stroke_samples(
        self, path: list[tuple[int, int]]
    ) -> tuple[list[tuple[int, int]], set[int], list[int]]:
        """
        Nội suy đường gấp khúc của nét thành chuỗi tọa độ pixel đầu bút liên tục.
        Giữa tâm hai ô liền kề lấy mẫu đều theo sample_step pixel, tạo thành quỹ đạo trượt liền mạch.

        Trả về (samples, pen_lifts, sample_cell_index):
            samples         —— danh sách tọa độ pixel đầu bút
            pen_lifts       —— tập chỉ số các điểm lấy mẫu "nhấc bút" (chỗ chuyển giữa các ô không liền kề)
            sample_cell_index —— chỉ số trong path của ô mà mỗi điểm lấy mẫu thuộc về,
                                                    dùng để tiến độ "hé lộ mực" đồng bộ chặt chẽ với "vị trí đầu bút".
        """
        samples: list[tuple[int, int]] = []
        pen_lifts: set[int] = set()
        sample_cell_index: list[int] = []
        for idx, cell in enumerate(path):
            cx, cy = self._cell_center(cell)
            if idx == 0:
                samples.append((cx, cy))
                sample_cell_index.append(idx)
                continue
            prev_cell = path[idx - 1]
            prev = self._cell_center(prev_cell)
            cell_distance = math.hypot(cell[0] - prev_cell[0], cell[1] - prev_cell[1])
            if cell_distance > math.sqrt(2):
                pen_lifts.add(len(samples))
                samples.append((cx, cy))
                sample_cell_index.append(idx)
                continue
            steps = max(
                1, int(math.hypot(cx - prev[0], cy - prev[1]) / self.cfg.sample_step)
            )
            for s in range(1, steps + 1):
                samples.append(
                    (int(prev[0] + (cx - prev[0]) * s / steps),
                     int(prev[1] + (cy - prev[1]) * s / steps))
                )
                sample_cell_index.append(idx)
        return samples, pen_lifts, sample_cell_index

    def _frame_progress_indices(self, n_steps: int, target_frames: int) -> list[int]:
        """
        Cho n_steps vị trí đầu bút và target_frames khung hình mục tiêu,
        trả về chỉ số vị trí đầu bút mà mỗi khung hình mục tiêu nên lấy (ánh xạ đều, bao phủ toàn bộ quỹ đạo).
        target_frames <= n_steps thì là lấy mẫu giảm, > thì là lấy mẫu lặp.
        target_frames <= 0 (ví dụ tổng thời lượng ≤ đoạn dừng hình khiến đoạn này không có khung nào) thì trả về rỗng, không tạo khung nào.
        """
        if n_steps == 0 or target_frames <= 0:
            return []
        if target_frames == 1:
            return [n_steps - 1]
        return [
            round(f * (n_steps - 1) / (target_frames - 1))
            for f in range(target_frames)
        ]

    def _pause_frame_indices(
        self, target_frames: int, n_cells: int
    ) -> set[int]:
        """
        Dừng thích ứng: chia mức theo mật độ nội dung để quyết định tỷ lệ dừng, rồi phân bố đều các khung dừng trên trục thời gian.
        Trả về tập chỉ số khung hình cần "đóng băng (lặp lại tiến độ của khung trước)".

        Chỉ số chia mức dùng "số khung hình mỗi ô" frames_per_cell = target_frames / n_cells:
        khung nhiều hơn ô rất nhiều (giá trị lớn) cho thấy thời lượng video dư dả so với nội dung → dừng nhiều để mô phỏng đổi bút lấy hơi;
        khung ít hơn ô (giá trị nhỏ) cho thấy nội dung dày, thời lượng eo hẹp → không dừng.

        pause_mode có thể cưỡng chế ghi đè: "off" tắt, "light"/"heavy" mức cố định, "auto" tự động.
        """
        mode = self.cfg.pause_mode
        if mode == "off" or target_frames < 8 or n_cells <= 0:
            return set()

        if mode == "light":
            ratio = self.cfg.pause_ratio_light
        elif mode == "heavy":
            ratio = self.cfg.pause_ratio_heavy
        else:  # auto: tự chia mức theo "số khung hình mỗi ô"
            fpc = target_frames / n_cells
            if fpc >= self.cfg.pause_heavy_fpc:
                ratio = self.cfg.pause_ratio_heavy
            elif fpc >= self.cfg.pause_light_fpc:
                ratio = self.cfg.pause_ratio_light
            else:
                return set()  # Nội dung dày: nhịp nhanh, không dừng

        # Số khung dừng, tối thiểu là 0; kẹp vào target_frames-2 để tránh dừng ở khung đầu và cuối
        pause_count = min(
            max(0, int(round(target_frames * ratio))),
            max(0, target_frames - 2),
        )
        if pause_count <= 0:
            return set()

        # Chia đều để chèn: chia target_frames thành pause_count+1 phần bằng nhau, điểm dừng rơi vào các điểm chia bên trong
        # Không dùng đầu cuối (tử số của 1/(n+1) bắt đầu từ 1), đảm bảo đầu và cuối không bị ngắt
        return {
            max(1, min(target_frames - 2,
                       round((idx + 1) * target_frames / (pause_count + 1))))
            for idx in range(pause_count)
        }

    # ── Đoạn phác nét: dọc theo stroke_path vẽ bản phác thảo, đầu bút trượt và đồng bộ chặt chẽ với việc hé lộ mực ──
    def lay_down_ink(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        """Cổng vào đoạn phác nét: theo ink_path_mode điều hướng đến dò khung xương hoặc đường đi qua các ô lưới."""
        if self.cfg.ink_path_mode == "skeleton" and self.skeleton_strokes:
            return self._lay_down_ink_skeleton(writer, target_frames)
        return self._lay_down_ink_grid(writer, target_frames)

    # ── Chế độ grid: hé lộ mực dọc theo đường nội suy qua tâm ô lưới (logic gốc) ──
    def _lay_down_ink_grid(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        path = self.stroke_path
        n = len(path)
        if n == 0:
            print("  Không có nét mực, bỏ qua đoạn phác nét")
            for _ in range(target_frames):
                writer.write(self._snapshot_with_tip(self.out_w // 2, self.out_h // 2))
            return

        samples, pen_lifts, sample_cell_index = self._build_stroke_samples(path)
        sample_idx_for_frame = self._frame_progress_indices(len(samples), target_frames)

        # Dừng thích ứng: theo mật độ chọn ra "khung đóng băng" (đầu bút không động, mực không tiến),
        # mô phỏng nhịp đổi bút/lấy hơi khi người thật viết.
        pause_frames = self._pause_frame_indices(target_frames, n)
        if pause_frames:
            print(f"  Dừng thích ứng: {len(pause_frames)} khung đóng băng (chế độ={self.cfg.pause_mode})")

        written = 0
        cells_revealed = 0  # Số ô đã hé lộ nguyên khối (tăng dần, bám sát tiến độ đầu bút)
        last_sample_idx: int | None = None
        for fi, si in enumerate(sample_idx_for_frame):
            # Khung dừng: dùng lại vị trí và tiến độ đầu bút của khung trước, không hé lộ mực, chỉ ghi một khung ảnh chụp (đầu bút đóng băng)
            if fi in pause_frames and last_sample_idx is not None:
                sx, sy = samples[last_sample_idx]
                writer.write(self._snapshot_with_tip(sx, sy))
                written += 1
                if (fi + 1) % max(1, target_frames // 10) == 0:
                    print(f"  Tiến độ phác nét: {int((fi + 1) / target_frames * 100)}%")
                continue

            # Đầu bút hé lộ dọc theo đường nét (giữ cảm giác nét bút chảy)
            if last_sample_idx is None:
                self._reveal_ink_segment(samples[si], samples[si])
            else:
                for sample_idx in range(last_sample_idx + 1, si + 1):
                    if sample_idx in pen_lifts:
                        continue
                    self._reveal_ink_segment(
                        samples[sample_idx - 1], samples[sample_idx]
                    )

            # Hé lộ nguyên khối: hé lộ chính xác đến "ô mà đầu bút hiện đang ở", đảm bảo đầu bút đồng bộ với hình vẽ, chữ đầy đủ.
            # sample_cell_index[si] là chỉ số ô mà đầu bút của khung hiện tại thuộc về, hé lộ đến đó là dừng.
            target_cell = sample_cell_index[si]
            while cells_revealed <= target_cell and cells_revealed < n:
                self._ink_stamp(path[cells_revealed])
                cells_revealed += 1

            sx, sy = samples[si]
            writer.write(self._snapshot_with_tip(sx, sy))
            written += 1
            last_sample_idx = si
            if (fi + 1) % max(1, target_frames // 10) == 0:
                print(f"  Tiến độ phác nét: {int((fi + 1) / target_frames * 100)}%")

        # Chốt cuối: đảm bảo nét mực của mọi ô được hé lộ đầy đủ, và bù đủ số khung hình
        while cells_revealed < n:
            self._ink_stamp(path[cells_revealed])
            cells_revealed += 1
        last = samples[-1]
        while written < target_frames:
            writer.write(self._snapshot_with_tip(*last))
            written += 1
        print(f"  Phác nét xong: {n} ô, {written} khung")

    # ── Chế độ skeleton: hé lộ mực dọc theo đường pixel khung xương (đầu bút đi theo khung xương thật) ──
    def _lay_down_ink_skeleton(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        """
        Phác nét chế độ khung xương: đầu bút trượt theo các điểm pixel khung xương, dùng _reveal_ink_segment hé lộ nét mực của ảnh gốc.
        Không hé lộ nguyên khối (_ink_stamp), vì khung xương đã chính xác đến pixel, không cần đảm bảo ô đầy đủ.
        Chỗ chuyển giữa các nét đánh dấu nhấc bút (pen_lifts), bỏ qua nội suy.
        """
        strokes = self.skeleton_strokes
        if not strokes:
            return self._lay_down_ink_grid(writer, target_frames)

        # Dàn nhiều nét thành chuỗi điểm lấy mẫu liên tục, đánh dấu nhấc bút ở chỗ chuyển giữa các nét
        samples: list[tuple[int, int]] = []
        pen_lifts: set[int] = set()
        for si, stroke in enumerate(strokes):
            if si > 0:
                pen_lifts.add(len(samples))  # Nhấc bút giữa các nét
            samples.extend(stroke)

        n = len(samples)
        if n == 0:
            print("  Không có nét khung xương, bỏ qua đoạn phác nét")
            for _ in range(target_frames):
                writer.write(self._snapshot_with_tip(self.out_w // 2, self.out_h // 2))
            return

        sample_idx_for_frame = self._frame_progress_indices(n, target_frames)

        # Dừng thích ứng (dùng số nét chứ không phải số ô để xét mật độ)
        pause_frames = self._pause_frame_indices(target_frames, len(strokes))
        if pause_frames:
            print(f"  Dừng thích ứng: {len(pause_frames)} khung đóng băng (chế độ={self.cfg.pause_mode})")

        written = 0
        last_sample_idx: int | None = None
        report_step = max(1, target_frames // 10)
        for fi, si in enumerate(sample_idx_for_frame):
            # Khung dừng: đầu bút đóng băng
            if fi in pause_frames and last_sample_idx is not None:
                sx, sy = samples[last_sample_idx]
                writer.write(self._snapshot_with_tip(sx, sy))
                written += 1
                if (fi + 1) % report_step == 0:
                    print(f"  Tiến độ phác nét: {int((fi + 1) / target_frames * 100)}%")
                continue

            # Hé lộ mực dọc theo khung xương: từ điểm lấy mẫu của khung trước đến điểm lấy mẫu của khung hiện tại, lần lượt hé lộ nét mực của ảnh gốc
            if last_sample_idx is None:
                self._reveal_ink_segment(samples[si], samples[si])
            else:
                for idx in range(last_sample_idx + 1, si + 1):
                    if idx in pen_lifts:
                        continue
                    self._reveal_ink_segment(samples[idx - 1], samples[idx])

            sx, sy = samples[si]
            writer.write(self._snapshot_with_tip(sx, sy))
            written += 1
            last_sample_idx = si
            if (fi + 1) % report_step == 0:
                print(f"  Tiến độ phác nét: {int((fi + 1) / target_frames * 100)}%")

        # Chốt cuối: bù đủ số khung hình
        last = samples[-1]
        while written < target_frames:
            writer.write(self._snapshot_with_tip(*last))
            written += 1
        print(f"  Phác nét xong (khung xương): {n} điểm lấy mẫu, {written} khung")

    # ── Cổng vào đoạn tô màu: theo color_fill điều hướng đến kiểu tương ứng ──
    def wash_color(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        if self.cfg.color_fill == "contour-wipe":
            return self.wash_color_contour(writer, target_frames)
        return self.wash_color_brush(writer, target_frames)

    # ── brush: dọc theo quỹ đạo nét, dùng cọ mực tròn phủ màu gốc (kiểu mặc định) ──
    def wash_color_brush(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        path = self.stroke_path
        n = len(path)
        disk = _feathered_disk(self.cfg.brush_radius)
        if n == 0:
            print("  Không có nét mực, bỏ qua đoạn tô màu")
            gaze = self.color_img
            for _ in range(target_frames):
                writer.write(gaze)
            return

        centers = [self._cell_center(cell) for cell in path]
        cell_idx_for_frame = self._frame_progress_indices(n, target_frames)

        written = 0
        last_cell_idx: int | None = None
        for fi, ci in enumerate(cell_idx_for_frame):
            # Tô màu theo tiến độ khung hiện tại: từ ô của khung trước quét bù đến ô hiện tại,
            # quét luôn những ô ở giữa có thể bị bỏ qua khi lấy mẫu giảm, đảm bảo màu gốc liền mạch.
            if last_cell_idx is None:
                self._color_stamp(*centers[ci], disk)
            else:
                for cell_idx in range(last_cell_idx + 1, ci + 1):
                    self._color_stamp(*centers[cell_idx], disk)

            cx, cy = centers[ci]
            writer.write(self._snapshot_with_tip(cx, cy))
            written += 1
            last_cell_idx = ci
            if (fi + 1) % max(1, target_frames // 10) == 0:
                print(f"  Tiến độ tô màu: {int((fi + 1) / target_frames * 100)}%")

        # Chốt cuối
        last = centers[-1]
        while written < target_frames:
            writer.write(self._snapshot_with_tip(*last))
            written += 1
        print(f"  Tô màu xong: {n} ô, {written} khung")

    # ── contour-wipe: tô màu quét từ trên xuống nhận biết đường viền ──
    def wash_color_contour(self, writer: cv2.VideoWriter, target_frames: int) -> None:
        """
        Màu không quét theo quỹ đạo nét, mà là một mép hé lộ quét toàn cục từ trên xuống.
        Mép gặp đường viền thì kẹt lại trước (lực cản ≈1 bị trừ delay_px), rồi chậm rãi vượt qua theo bóng giảm dần phía dưới nó,
        tạo cảm giác "màu lan dọc theo đường nét". Đầu bút quét qua lại theo chiều ngang, mô phỏng bàn tay đang tô màu.
        """
        cfg = self.cfg
        h, w = self.out_h, self.out_w

        if target_frames <= 0:
            print("  Không có khung tô màu, bỏ qua đoạn contour-wipe")
            return

        # Tính trước một lần: trường cản, đường biên sóng, số pixel bị trừ, lưới tọa độ hàng
        resistance = self._build_resistance_field()
        wave = _build_wipe_wave(w)
        delay_px = int(np.clip(h * cfg.wipe_delay_ratio, 12, 52))
        blocks = max(1, cfg.wipe_blocks)
        ys = np.arange(h, dtype=np.float32)[:, None]   # (H,1), dùng lại từng khung

        # Đặt self.drawn về trạng thái "bản phác thảo đã vẽ xong" (brush tiếp nối sau lay_down_ink, ở đây cũng tiếp nối)
        # color_img là mục tiêu hé lộ
        color_src = self.color_img.astype(np.float32)

        print(f"  contour-wipe: {w}x{h}, delay_px={delay_px}, số lượt={blocks}")

        written = 0
        # Mép hé lộ quét từ -delay_px đến h+delay_px, bao phủ toàn bộ
        sweep = h + 2 * delay_px
        report_step = max(1, target_frames // 10)

        for fi in range(target_frames):
            # Tiến độ toàn cục (có làm mượt kiểu sin): 0 → 1
            if target_frames == 1:
                progress = 1.0
            else:
                progress = fi / (target_frames - 1)
            lead = _ease_in_out_sine(progress) * sweep - delay_px

            # Mặt nạ hé lộ: y <= lead + wave[x] - resistance[y,x]*delay_px
            threshold = lead + wave[None, :] - resistance * delay_px  # (H,W)
            reveal = ys <= threshold                        # (H,W) bool

            # Hé lộ màu gốc vào bộ đệm drawn
            self.drawn[reveal] = color_src[reveal]

            # Đầu bút quét ngang: blocks lượt qua lại, lượt lẻ đi ngược
            lane = (fi / blocks * 2.0) % 1.0               # Tiến độ chuẩn hóa của một lượt 0..1
            lane = _ease_in_out_sine(lane)
            forward = (int(fi // blocks) % 2 == 0)         # Lượt chẵn đi xuôi, lượt lẻ đi ngược
            cursor_x = int(lane * w) if forward else int((1.0 - lane) * w)
            cursor_x = max(0, min(w - 1, cursor_x))

            # Con trỏ y = hàng thấp nhất trong số pixel đã hé lộ của cột hiện tại
            col_revealed = np.where(reveal[:, cursor_x])[0]
            cursor_y = int(col_revealed[-1]) if col_revealed.size > 0 else 0

            writer.write(self._snapshot_with_tip(cursor_x, cursor_y))
            written += 1
            if (fi + 1) % report_step == 0:
                print(f"  Tiến độ tô màu (contour-wipe): {int((fi + 1) / target_frames * 100)}%")

        # Chốt cuối: đảm bảo cả ảnh đã hé lộ (khung cuối tiến độ=1 thì lead≈h+delay_px, về lý thuyết phủ toàn bộ)
        full_reveal = np.ones((h, w), dtype=bool)
        self.drawn[full_reveal] = color_src[full_reveal]
        last = self._snapshot_with_tip(w // 2, h - 1)
        while written < target_frames:
            writer.write(last)
            written += 1
        print(f"  contour-wipe xong: {written} khung")

    def render_to(self, raw_path: Path, total_ms: int) -> Path:
        cfg = self.cfg
        plan = plan_phases(total_ms, cfg)
        ink_cells = len(self.stroke_path)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(raw_path), fourcc, cfg.fps, (self.out_w, self.out_h))

        print(f"  Dòng mực: {len(self.ink_streams)} dòng, ô mực: {ink_cells}")
        print(
            f"  Thời lượng: {total_ms}ms -> phác nét {plan.ink_frames}f / "
            f"tô màu {plan.color_frames}f / dừng hình {plan.gaze_frames}f (trọng số {plan.ratio_label})"
        )

        started = time.time()
        self.lay_down_ink(writer, plan.ink_frames)
        self.wash_color(writer, plan.color_frames)
        # Dừng hình: ảnh gốc đầy đủ
        gaze_img = self.color_img
        for _ in range(plan.gaze_frames):
            writer.write(gaze_img)
        writer.release()
        print(f"  Thời gian render: {time.time() - started:.1f}s")
        return raw_path


# ──────────────────────────────────────────────────────────────
# Chuyển mã (ưu tiên ffmpeg hệ thống, PyAV dự phòng, cả hai đều không có thì giữ mp4v)
# ──────────────────────────────────────────────────────────────
def transcode_h264(src: Path, dst: Path) -> Path:
    """
    Chuyển mã video thô mp4v sang H.264 (yuv420p), tăng khả năng tương thích với trình phát.

    Thứ tự ưu tiên:
        1. Tiến trình con ffmpeg hệ thống (hiệu suất mã hóa cao nhất, dung lượng nhỏ nhất, CRF=20)
        2. PyAV (cài thuần bằng pip, không cần ffmpeg hệ thống; hiệu suất mã hóa kém hơn chút, dùng CRF=28 để kiểm soát dung lượng)
        3. Cả hai đều không có: giữ nguyên mã hóa mp4v thô và cảnh báo
    """
    # Đường 1: ffmpeg hệ thống (khuyến nghị, dung lượng tối ưu)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is not None:
        cmd = [
            ffmpeg, "-y", "-loglevel", "error",
            "-i", str(src),
            "-c:v", "libx264",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(dst),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            src.unlink(missing_ok=True)
            print(f"  Chuyển mã H.264 xong (ffmpeg): {dst}")
            return dst
        print(f"  [warn] Chuyển mã bằng ffmpeg thất bại: {res.stderr.strip()}")

    # Đường 2: PyAV (dự phòng, cài thuần bằng pip)
    try:
        return _transcode_with_pyav(src, dst)
    except ImportError:
        pass
    except Exception as e:
        print(f"  [warn] Chuyển mã bằng PyAV thất bại: {e}")

    # Đường 3: đều không có, giữ mp4v
    print(f"  [warn] Không tìm thấy ffmpeg và PyAV, giữ nguyên mã hóa mp4v thô: {src}")
    print(f"         Cài một trong hai là có H.264: pip install av  hoặc cài ffmpeg hệ thống")
    return src


def _transcode_with_pyav(src: Path, dst: Path) -> Path:
    """
    Dùng PyAV chuyển mã H.264 ngay trong Python. Chưa cài PyAV thì ném ImportError.
    libx264 đi kèm PyAV có hiệu suất mã hóa thấp hơn ffmpeg hệ thống (cùng CRF dung lượng lớn gấp nhiều lần),
    nên dùng CRF=28 để cân bằng dung lượng và chất lượng hình ảnh.
    """
    import av
    input_container = av.open(str(src), mode="r")
    in_stream = input_container.streams.video[0]
    width = in_stream.codec_context.width
    height = in_stream.codec_context.height
    fps = in_stream.average_rate

    output_container = av.open(str(dst), mode="w")
    out_stream = output_container.add_stream("h264", rate=fps)
    out_stream.width = width
    out_stream.height = height
    out_stream.pix_fmt = "yuv420p"
    out_stream.options = {"crf": "28", "preset": "medium"}

    for frame in input_container.decode(video=0):
        packet = out_stream.encode(frame)
        if packet:
            output_container.mux(packet)
    # flush
    packet = out_stream.encode(None)
    if packet:
        output_container.mux(packet)

    output_container.close()
    input_container.close()
    src.unlink(missing_ok=True)
    print(f"  Chuyển mã H.264 xong (PyAV): {dst}")
    return dst


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────
def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Render một ảnh thành video whiteboard nét bút chảy"
    )
    p.add_argument("image", help="Đường dẫn ảnh đầu vào (PNG/JPG/JPEG/BMP/TIFF)")
    p.add_argument("--out-dir", default="./out", help="Thư mục đầu ra (mặc định: ./out)")
    p.add_argument("--total-ms", type=int, default=10000, help="Tổng thời lượng video, đơn vị mili giây (mặc định: 10000)")
    p.add_argument("--bare-tip", action="store_true", help="Không chèn lớp phủ đầu bút/bàn tay")
    p.add_argument(
        "--pen-image", default=str(DEFAULT_HAND_PNG),
        help="Đường dẫn ảnh đầu bút/bàn tay tùy chỉnh (mặc định: drawing-hand.png có sẵn trong skill)",
    )
    p.add_argument("--fps", type=int, default=None, help="Ghi đè tốc độ khung hình mặc định")
    p.add_argument("--grid-edge", type=int, default=None, help="Ghi đè cạnh lưới mặc định")
    p.add_argument("--brush-radius", type=int, default=None, help="Ghi đè bán kính cọ mực mặc định")
    p.add_argument(
        "--color-fill", default="contour-wipe", choices=["brush", "contour-wipe"],
        help="Kiểu tô màu ở giai đoạn tô màu: contour-wipe quét từ trên xuống nhận biết đường viền (mặc định); brush quét theo quỹ đạo nét",
    )
    p.add_argument(
        "--wipe-decay", type=float, default=None,
        help="contour-wipe: hệ số giảm dần theo hàng đi xuống của trường cản (mặc định 0.86, càng nhỏ càng vượt đường viền nhanh)",
    )
    p.add_argument(
        "--wipe-delay-ratio", type=float, default=None,
        help="contour-wipe: tỷ lệ trừ ở mép tại đường viền ×h (mặc định 0.04, càng lớn càng dừng lâu ở đường viền)",
    )
    p.add_argument(
        "--wipe-blocks", type=int, default=None,
        help="contour-wipe: số lượt đầu bút quét qua lại theo chiều ngang (mặc định 18)",
    )
    p.add_argument(
        "--pause", default="heavy", choices=["auto", "off", "light", "heavy"],
        help="Nhịp dừng của đoạn phác nét: heavy rõ (mặc định); auto tự chia mức theo mật độ; off tắt; light ít",
    )
    p.add_argument(
        "--ink-path", default="grid", choices=["grid", "skeleton"],
        help="Đường đi nét của đoạn phác nét: grid nội suy qua tâm ô lưới (mặc định); skeleton dò pixel ở mức khung xương (bám sát đường nét chính xác hơn)",
    )
    return p.parse_args(argv)


def _build_cfg(args: argparse.Namespace) -> Config:
    kw: dict = {}
    if args.fps is not None:
        kw["fps"] = args.fps
    if args.grid_edge is not None:
        kw["grid_edge"] = args.grid_edge
    if args.brush_radius is not None:
        kw["brush_radius"] = args.brush_radius
    if args.color_fill is not None:
        kw["color_fill"] = args.color_fill
    if args.wipe_decay is not None:
        kw["wipe_decay"] = args.wipe_decay
    if args.wipe_delay_ratio is not None:
        kw["wipe_delay_ratio"] = args.wipe_delay_ratio
    if args.wipe_blocks is not None:
        kw["wipe_blocks"] = args.wipe_blocks
    if args.pause is not None:
        kw["pause_mode"] = args.pause
    if args.ink_path is not None:
        kw["ink_path_mode"] = args.ink_path
    return Config(**kw)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    cfg = _build_cfg(args)

    print("=" * 56)
    print("Bộ render hoạt ảnh nét bút chảy")
    print("=" * 56)

    image_bgr = _imread_any(args.image)
    if image_bgr is None:
        print(f"[err] Không đọc được ảnh: {args.image}")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = out_dir / f"stream_{ts}.mp4"
    h264_path = out_dir / f"stream_{ts}_h264.mp4"

    pen_png = Path(args.pen_image) if args.pen_image else None
    renderer = StreamBoardRenderer(image_bgr, cfg, pen_png, args.bare_tip)
    print(f"  Đầu vào: {args.image}")
    print(f"  Kích thước đầu ra: {renderer.out_w}x{renderer.out_h}, tốc độ khung hình: {cfg.fps}")

    renderer.render_to(raw_path, args.total_ms)
    final = transcode_h264(raw_path, h264_path)

    size_mb = final.stat().st_size / (1024 * 1024)
    print(f"\nVideo cuối: {final}")
    print(f"  Kích thước file: {size_mb:.2f} MB")
    print("=" * 56)
    print("Hoàn thành")
    # Dòng cuối xuất đường dẫn cuối cùng, để bên gọi dễ bắt lấy
    print(f"OUTPUT={final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
