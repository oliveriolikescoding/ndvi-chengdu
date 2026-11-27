"""W7-4 出图：NDVI 分级 + 年际变化 + 区县排序，一张 A4 横版（297×210 mm）。

复用 W6 的 carto.py（字体栈、比例尺、指北针、图廓、避让），只扩展栅格表达。
版式按毫米排：图幅 297×210，左边主图 99×146，右上变化图 67×100，右下图内排序图。

用法：python ndvi_map.py
输出：ndvi_map.png（300 dpi）/ ndvi_map.svg（文字转路径）/ ndvi_map_gray.png
"""
import json

import numpy as np
import _caption as CAP
import pandas as pd
import geopandas as gpd

import geoenv  # noqa: F401
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib import patheffects
import matplotlib.patches as mpatches

import carto
import config as C

OUT_PNG = C.ROOT / "ndvi_map.png"
PAGE_W, PAGE_H = 297.0, 210.0

NDVI_COLORS, DNDVI_COLORS = C.NDVI_COLORS, C.DNDVI_COLORS


def mm(x, y, w, h):
    """毫米 → figure 归一化坐标（原点左上）。"""
    return [x / PAGE_W, 1 - (y + h) / PAGE_H, w / PAGE_W, h / PAGE_H]


def load(tag):
    with rasterio.open(C.DATA / f"ndvi_{tag}.tif") as ds:
        arr = ds.read(1)
        tr = ds.transform
        h, w = arr.shape
    extent = (tr.c, tr.c + w * tr.a, tr.f + h * tr.e, tr.f)
    return arr, extent


def classify(arr, breaks):
    cls = np.full(arr.shape, -1, dtype="int8")
    valid = np.isfinite(arr)
    cls[valid] = np.digitize(arr[valid], breaks)
    return cls


def xy_axes(extent, shape):
    x = np.linspace(extent[0] + (extent[1] - extent[0]) / shape[1] / 2,
                   extent[1] - (extent[1] - extent[0]) / shape[1] / 2, shape[1])
    y = np.linspace(extent[3] - (extent[3] - extent[2]) / shape[0] / 2,
                   extent[2] + (extent[3] - extent[2]) / shape[0] / 2, shape[0])
    return x, y


INVALID_GRAY = "#D3D9DF"   # 无效像元（云/暗像元掩膜）用中性灰，不画成透明白洞


def draw_map(ax, cls, extent, colors, hatches=None):
    """cls 里 -1 表示无效；显示时给它单独一档中性灰，避免图面出现白洞。"""
    colors_ext = list(colors) + [INVALID_GRAY]
    n = len(colors_ext)
    cls_d = np.where(cls < 0, n - 1, cls)
    cmap = ListedColormap(colors_ext)
    ax.imshow(cls_d, extent=extent, origin="upper", cmap=cmap,
              norm=BoundaryNorm(np.arange(-0.5, n + 0.5, 1), n),
              interpolation="nearest", zorder=3, aspect="auto")
    if hatches:
        x, y = xy_axes(extent, cls.shape)
        for idx, hatch in hatches.items():
            m = np.ma.masked_where(cls != idx, cls)
            ax.contourf(x, y, m, levels=[idx - 0.5, idx + 0.5], colors="none",
                        hatches=[hatch * 3], zorder=4)


def legend_patches(colors, labels, hatches=None, **kw):
    out = []
    for i, (c, l) in enumerate(zip(colors, labels)):
        h = (hatches or {}).get(i, "")
        out.append(mpatches.Patch(facecolor=c, edgecolor="#FFFFFF", linewidth=0.5,
                                  hatch=h, label=l, **kw))
    return out


def main():
    carto.setup_chinese_font()

    nd_t1, extent = load("T1")
    nd_t2, _ = load("T2")
    dlt, _ = load("delta_norm")   # 已扣除两期整体偏移（见 ndvi_change.py）
    cls_t2 = classify(nd_t2, C.NDVI_BREAKS)
    cls_d = classify(dlt, C.DNDVI_BREAKS)

    dist = gpd.read_file(C.DISTRICTS, encoding="utf-8-sig").to_crs(C.CRS)
    stats = pd.read_csv(C.STATS_CSV, encoding="utf-8-sig")
    off = json.loads((C.DATA / "change_summary.json").read_text(encoding="utf-8"))["offset_removed"]
    # 排序图只保留被研究区覆盖 ≥20% 的区县：1% 的碎片（双流、龙泉驿）拿来排序会误导
    rank = stats[stats["clip_frac"] >= 20].reset_index(drop=True)

    xmin, xmax, ymin, ymax = extent[0], extent[1], extent[2], extent[3]
    width_m = xmax - xmin

    fig = plt.figure(figsize=C.FIG_SIZE, dpi=C.FIG_DPI)
    fig.patch.set_facecolor("white")

    ax = fig.add_axes(mm(12, 32, 91, 136))
    ax2 = fig.add_axes(mm(108, 32, 61, 91))
    ax3 = fig.add_axes(mm(190, 32, 95, 91))

    fig.text(12 / PAGE_W, 1 - 30 / PAGE_H, "（a）2026-01-12 植被覆盖度（NDVI 分级）",
             fontsize=8.2, color=C.TEXT_DARK, ha="left", va="bottom")
    fig.text(108 / PAGE_W, 1 - 30 / PAGE_H, "（b）2025-01 → 2026-01 NDVI 变化",
             fontsize=8.2, color=C.TEXT_DARK, ha="left", va="bottom")

    # ---------- ① 主图 ----------
    draw_map(ax, cls_t2, extent, NDVI_COLORS, hatches=C.NDVI_HATCH)
    dist.plot(ax=ax, facecolor="none", edgecolor="#12233A", linewidth=0.5, alpha=0.35, zorder=5)
    for _, r in dist.iterrows():
        if r["name"] not in set(rank["name"]):
            continue
        pt = r.geometry.representative_point()
        if xmin < pt.x < xmax and ymin < pt.y < ymax:
            ax.text(pt.x, pt.y, r["name"], fontsize=6.0, color="#12233A", ha="center", va="center",
                    zorder=6, path_effects=[patheffects.withStroke(linewidth=2.2,
                                                                  foreground="white", alpha=0.9)])

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_aspect("equal")
    for s in ax.spines.values():
        s.set_linewidth(0.8); s.set_color(carto.PALETTE["frame"])

    carto.frame_and_ticks(ax, "坐标 UTM 48N（E / N，km）")
    carto.north_arrow(ax)
    carto.scale_bar(ax)

    ax_w_in = ax.get_position().width * C.FIG_SIZE[0]
    denom = width_m / (ax_w_in * 0.0254)
    print(f"比例尺 1:{denom:,.0f}（图幅 {ax_w_in:.2f} in ≈ 实地 {width_m/1000:.2f} km）")

    leg1 = ax.legend(handles=legend_patches(list(NDVI_COLORS) + [INVALID_GRAY],
                                            list(C.NDVI_LABELS) + ["无效像元"], C.NDVI_HATCH),
                     loc="lower right", bbox_to_anchor=(0.988, 0.006), ncol=1,
                     title="NDVI 分级（无量纲）", title_fontsize=6.4, fontsize=5.6,
                     frameon=True, framealpha=0.94, edgecolor="#D5DCE3", labelspacing=0.2,
                     handlelength=1.0, handleheight=0.78, borderpad=0.35)
    leg1.get_frame().set_linewidth(0.5)
    ax.add_artist(leg1)

    # ---------- ② 变化图 ----------
    draw_map(ax2, cls_d, extent, DNDVI_COLORS, hatches=C.DNDVI_HATCH)
    dist.boundary.plot(ax=ax2, color="#12233A", linewidth=0.35, alpha=0.3, zorder=5)
    ax2.set_xlim(xmin, xmax); ax2.set_ylim(ymin, ymax)
    ax2.set_xticks([]); ax2.set_yticks([])
    ax2.set_aspect("equal")
    for s in ax2.spines.values():
        s.set_linewidth(0.7); s.set_color(carto.PALETTE["frame"])
    ax2.text(0.012, 1.0, "", transform=ax2.transAxes)  # 占位（标题已移到图幅外）
    leg2 = ax2.legend(handles=legend_patches(list(DNDVI_COLORS) + [INVALID_GRAY],
                                             list(C.DNDVI_LABELS) + ["无效/掩膜"], C.DNDVI_HATCH),
                      loc="lower left", bbox_to_anchor=(0.005, 0.005), ncol=2, fontsize=5.2,
                      title="ΔNDVI 分级", title_fontsize=5.6,
                      frameon=True, framealpha=0.95, edgecolor="#D5DCE3", handlelength=0.9,
                      handleheight=0.7, borderpad=0.3, labelspacing=0.18, columnspacing=0.5)
    leg2.get_frame().set_linewidth(0.5)

    # ---------- ③ 区县排序 ----------
    s = rank.sort_values("ndvi_mean_t2", ascending=True)
    y = np.arange(len(s))
    ax3.barh(y, s["ndvi_mean_t2"], color="#5CA456", height=0.62, zorder=3, label="2026-01 均值")
    ax3.barh(y, s["ndvi_mean_t1"], color="none", edgecolor="#B23A2E", linewidth=0.8,
             height=0.62, zorder=4, label="2025-01 均值")
    for i, v in enumerate(s["ndvi_mean_t2"]):
        ax3.text(v + 0.008, i, f"{v:.2f}", fontsize=6.2, va="center", color="#1D2733")
    ax3.set_yticks(y)
    ax3.set_yticklabels(list(s["name"]), fontsize=6.4)
    ax3.set_xlim(0, max(s["ndvi_mean_t2"].max(), 0.01) * 1.16)
    ax3.set_xlabel("NDVI 均值（无量纲）", fontsize=7.0)
    ax3.tick_params(axis="x", labelsize=6.2, length=2)
    ax3.grid(axis="x", color="#E4E9EE", linewidth=0.5, zorder=0)
    ax3.set_axisbelow(True)
    for sp in ("top", "right"):
        ax3.spines[sp].set_visible(False)
    ax3.set_title("（c）各区县 NDVI 均值（2026-01 排序）", fontsize=8.2, color=C.TEXT_DARK, pad=6,
                  loc="left")
    ax3.legend(fontsize=5.9, frameon=False, loc="lower right", handlelength=1.0)

    # ---------- 图题与图注（置于图下） ----------
    top, low = rank.iloc[0], rank.iloc[-1]
    summ = json.loads((C.DATA / "change_summary.json").read_text(encoding="utf-8"))["normalized"]
    notes = [
        f"全区 2026-01 NDVI 均值 {np.nanmean(nd_t2):.2f}、中位 {np.nanmedian(nd_t2):.2f}，"
        f"NDVI ≥ 0.6 的高植被占比 {float((nd_t2[np.isfinite(nd_t2)] >= 0.6).mean()) * 100:.1f}%，"
        f"有效像元 {float(np.isfinite(nd_t2).mean() * 100):.1f}%",
        f"仅列研究区覆盖不低于 20% 的 5 个区县：{top['name']} 均值最高（{top['ndvi_mean_t2']:.2f}，研究区覆盖 {top['clip_frac']:.0f}%），"
        f"{low['name']} 最低（{low['ndvi_mean_t2']:.2f}，覆盖 {low['clip_frac']:.0f}%）",
        f"两期原始 ΔNDVI 中位 {off:+.3f}，扣除该中位偏移后改善 {summ['improved_frac'] * 100:.0f}%、"
        f"退化 {summ['degraded_frac'] * 100:.0f}%、基本稳定 {summ['stable_frac'] * 100:.0f}%；"
        "变化图只反映空间格局，不做面积统计",
        "据 Sentinel-2 L2A（ESA / Copernicus，Public Domain，经 Element 84 Earth Search STAC 获取）与 DataV.GeoAtlas 区县界绘制；"
        "反射率按 scale 0.0001、offset -0.1 校正，SCL 掩膜云、云影、雪与无数据像元",
        "投影 EPSG:32648（WGS 84 / UTM zone 48N），制图日期 2026-11-26；1 月为植被休眠期，两期仅相隔一年，可比较同期格局，不作长期趋势判断；"
        "本图为分析图件，非标准地图，无审图号",
    ]
    CAP.add_caption(fig, 1, "成都城区植被覆盖度（NDVI）与年际变化", notes, lb=0.04, rb=0.96, pad=0.12)

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=C.FIG_DPI, facecolor="white")
    with plt.rc_context({"svg.fonttype": "path"}):
        fig.savefig(OUT_PNG.with_suffix(".svg"), facecolor="white")
    print(f"已写出 {OUT_PNG} 与同名 .svg")

    print("\n对比度（对白底，WCAG 非文本 3:1）：")
    for c, l in zip(NDVI_COLORS, C.NDVI_LABELS):
        print(f"  {l:<6} {c}  {carto.contrast_ratio(c, '#FFFFFF'):.2f}")
    gray = OUT_PNG.with_name("ndvi_map_gray.png")
    from PIL import Image
    Image.open(OUT_PNG).convert("L").save(gray)
    print(f"灰度版已写出 {gray}")


if __name__ == "__main__":
    main()


