# -*- coding: utf-8 -*-
"""
carto.py —— 专题地图的图面构件（可复用）

包含：配色、中西文混排字体栈（西文 Times New Roman + 中文宋体 SimSun）、分段比例尺、
指北针、图廓与坐标注记、WCAG 对比度自检。这些是上一张图（SV-01）里被审查出来的
那批图面问题，抽出来复用，省得每张图重做一遍。
"""
from __future__ import annotations

import math

PALETTE = {
    "page": "#FFFFFF",
    "basemap_face": "#F5F7FA",
    "basemap_edge": "#CBD5DF",
    "title": "#12233A",
    "sub": "#5B6B7C",
    "note": "#66727F",
    "frame": "#B9C2CC",
    "leader": "#A7B3BF",
    "district_text": "#8D99A6",
}

CN_FONTS = (
    "SimSun", "NSimSun", "Noto Serif SC", "STSong", "FangSong",
    "DengXian", "Microsoft YaHei", "Source Han Sans SC", "PingFang SC", "SimHei",
)

# 西文优先：Times New Roman（有真 Bold，数字比宋体内置西文更规整）
LATIN_FONTS = ("Times New Roman", "Nimbus Roman", "Liberation Serif", "DejaVu Serif")


def setup_chinese_font() -> bool:
    """中西文混排：西文走 Times New Roman，中文回落到宋体 SimSun。

    matplotlib 3.6+ 支持按字逐个回落，所以直接把 [Times New Roman, SimSun]
    交给 font.family，拉丁字母与数字取前者，汉字取后者。
    """
    import matplotlib
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    cjk = next((f for f in CN_FONTS if f in available), None)
    if cjk is None:
        print("⚠️  没有中文字体，图面改用英文标注")
        return False

    latin = [f for f in LATIN_FONTS if f in available]
    stack = latin + [cjk]
    matplotlib.rcParams["font.family"] = stack
    # 兜底：某些旧代码路径只认 sans-serif / serif 两个别名
    matplotlib.rcParams["font.sans-serif"] = stack
    matplotlib.rcParams["font.serif"] = stack
    matplotlib.rcParams["axes.unicode_minus"] = False
    print(f"字体栈：西文 {latin[0] if latin else 'DejaVu Serif'} + 中文 {cjk}")
    return True


def _lum(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def _f(x: float) -> float:
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    return 0.2126 * _f(r) + 0.7152 * _f(g) + 0.0722 * _f(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 相对亮度对比度，核对 SC 1.4.11 的 3:1 门槛。"""
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def nice_length(target: float) -> float:
    mag = 10 ** math.floor(math.log10(target))
    return min((m * mag for m in (1, 2, 2.5, 5, 10)), key=lambda v: abs(v - target))


def fmt_len(v_m: float) -> str:
    return f"{v_m / 1000:g} km" if v_m >= 1000 else f"{v_m:g} m"


def scale_bar(ax, segments: int = 4) -> float:
    """分段比例尺（黑白相间，左 0 右整值），返回比例尺代表的实地长度（米）。"""
    from matplotlib.patches import Rectangle

    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    width, height = x1 - x0, y1 - y0
    length = nice_length(width / 4.0)
    x_start = x0 + width * 0.045
    y_bar = y0 + height * 0.045
    bar_h = height * 0.008

    seg = length / segments
    for i in range(segments):
        ax.add_patch(Rectangle((x_start + i * seg, y_bar), seg, bar_h,
                               facecolor="#243447" if i % 2 == 0 else "#FFFFFF",
                               edgecolor="#243447", linewidth=0.6, zorder=9))
    for frac in (0.0, 0.5, 1.0):
        ax.plot([x_start + length * frac] * 2, [y_bar, y_bar + bar_h * 1.9],
                color="#243447", linewidth=0.7, zorder=9)
    for frac, ha in ((0.0, "center"), (0.5, "center"), (1.0, "right")):
        label = "0" if frac == 0 else fmt_len(length * frac)
        ax.text(x_start + length * frac, y_bar + bar_h * 2.6, label,
                ha=ha, va="bottom", fontsize=7.2, color="#243447", zorder=9)
    return length


def north_arrow(ax) -> None:
    """指北针（投影坐标北向即图面正上）。"""
    from matplotlib.patches import Polygon

    x, y = 0.944, 0.905
    ax.add_patch(Polygon([[x, y + 0.072], [x - 0.013, y - 0.006], [x, y + 0.016], [x + 0.013, y - 0.006]],
                         closed=True, transform=ax.transAxes, facecolor="#243447",
                         edgecolor="none", zorder=10, clip_on=False))
    ax.text(x, y + 0.080, "N", transform=ax.transAxes, ha="center", va="bottom",
            fontsize=8.6, fontweight="bold", color="#243447", zorder=10)


def frame_and_ticks(ax, crs_note: str | None = "坐标：UTM zone 48N（E / N，km）") -> None:
    """双线图廓 + 图廓外坐标注记（公里数）。"""
    from matplotlib.patches import Rectangle

    for inset, lw in ((0.0, 1.0), (0.008, 0.4)):
        ax.add_patch(Rectangle((inset, inset), 1 - 2 * inset, 1 - 2 * inset,
                               transform=ax.transAxes, fill=False,
                               edgecolor=PALETTE["frame"], linewidth=lw,
                               zorder=8, clip_on=False))

    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    width, height = x1 - x0, y1 - y0
    step_x = nice_length(width / 5.5)
    step_y = nice_length(height / 5.5)

    def _ticks(lo, hi, step):
        start = math.ceil(lo / step) * step
        vals, v = [], start
        while v < hi:
            vals.append(v)
            v += step
        return vals

    for v in _ticks(x0, x1, step_x):
        ax.plot([v, v], [y0, y0 - height * 0.011], color="#243447", linewidth=0.6,
                clip_on=False, zorder=9)
        ax.text(v, y0 - height * 0.017, f"{v / 1000:,.0f}", ha="center", va="top",
                fontsize=6.2, color="#4A5A6A", clip_on=False)
    for v in _ticks(y0, y1, step_y):
        ax.plot([x0, x0 - width * 0.008], [v, v], color="#243447", linewidth=0.6,
                clip_on=False, zorder=9)
        ax.text(x0 - width * 0.013, v, f"{v / 1000:,.0f}", ha="right", va="center",
                fontsize=6.2, color="#4A5A6A", rotation=90, clip_on=False)
    if crs_note:
        ax.text(x0, y0 - height * 0.033, crs_note, ha="left", va="top",
                fontsize=6.6, color="#4A5A6A", clip_on=False)


def overlap(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def avoid_callouts(ax, items, text_fn, max_n: int = 8, avoid=None) -> int:
    """带引线的注记 + 12 方向避让。items: [(x, y, row)]，text_fn(row)->str。"""
    from matplotlib import patheffects

    if not len(items):
        return 0
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    width, height = x1 - x0, y1 - y0
    placed = list(avoid or [])
    # 右上角留给指北针，注记不要压上去
    placed.append((x0 + width * 0.885, y0 + height * 0.835, x1, y1))
    offsets = ((0.018, 0.020), (0.018, -0.022), (-0.018, 0.020), (-0.018, -0.022),
               (0.032, 0.034), (0.032, -0.036), (-0.032, 0.034), (-0.032, -0.036),
               (0.014, 0.048), (0.014, -0.050), (-0.014, 0.048), (-0.014, -0.050))

    # 盒宽按「全角=1、半角=0.5」估算：中文注记若只数字符，会算出过窄的盒，
    # 结果文字压到邻居身上，避让等于没做。
    def _units(s: str) -> float:
        return sum(1.0 if ord(c) > 127 else 0.5 for c in s)

    for i, (px, py, row) in enumerate(items[:max_n]):
        text = text_fn(row)
        # 6.9 pt 等线一个全角字大约占 0.092 in
        box_w = width * (0.092 * _units(text)) / max(ax.get_window_extent().width / ax.figure.dpi, 1e-6)
        box_h = height * 0.0175
        chosen = None
        for fx, fy in offsets:
            ax_x = max(x0 + width * 0.02,
                       min(px + fx * width, x1 - width * 0.02 - box_w))
            ax_y = max(y0 + height * 0.03 + box_h,
                       min(py + fy * height, y1 - height * 0.03))
            rect = (ax_x, ax_y - box_h, ax_x + box_w, ax_y + box_h)
            if not any(overlap(rect, p) for p in placed):
                chosen = (ax_x, ax_y, rect)
                break
        if chosen is None and i == 0:
            ax_x = min(px + width * 0.018, x1 - width * 0.02 - box_w)
            ax_y = min(py + height * 0.020, y1 - height * 0.03)
            chosen = (ax_x, ax_y, (ax_x, ax_y - box_h, ax_x + box_w, ax_y + box_h))
        if chosen is None:
            continue
        ax_x, ax_y, rect = chosen
        placed.append(rect)
        ax.annotate(text, xy=(px, py), xytext=(ax_x, ax_y), fontsize=6.9,
                    color="#1F2933", ha="left", va="bottom", zorder=8,
                    path_effects=[patheffects.withStroke(linewidth=2.0, foreground="white", alpha=0.9)],
                    arrowprops=dict(arrowstyle="-", color=PALETTE["leader"],
                                    linewidth=0.6, shrinkA=2, shrinkB=4))
    return len(placed) - len(avoid or [])
