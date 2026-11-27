"""W7-3 区县统计：按区县边界，算 NDVI 均值 / 高植被占比 / 变化量 / 有效像元占比。

只统计落在研究区范围内的那部分区县面积（研究区只有 15.5 × 23 km，
20 个区县里多数只被切到一角），`clip_frac` 列给出「该区县被研究区覆盖的比例」，
低于 20% 的区县在图上和结论里都不该拿来比较。

用法：python ndvi_stats.py
输出：data/ndvi_by_district.csv（UTF-8-sig，Excel 直接双击不乱码）
"""
import numpy as np
import pandas as pd

import geoenv  # noqa: F401
import rasterio
from rasterio.features import rasterize
import geopandas as gpd

import config as C


def load(path):
    with rasterio.open(path) as ds:
        return ds.read(1), ds.transform, ds.shape


def main():
    nd1, tr, shape = load(C.DATA / "ndvi_T1.tif")
    nd2, _, _ = load(C.DATA / "ndvi_T2.tif")
    # 变化量用「扣除全区中位偏移」之后的版本（ndvi_change.py 生成），
    # 原始 Δ 一并写进 csv，便于核对，不做隐藏。
    dd, _, _ = load(C.DATA / "ndvi_delta_norm.tif")
    draw, _, _ = load(C.DATA / "ndvi_delta.tif")

    # 区县文件带 BOM，必须 utf-8-sig，否则首列名会变成 "\ufeffadcode"
    dist = gpd.read_file(C.DISTRICTS, encoding="utf-8-sig").to_crs(C.CRS)
    px_area = abs(tr.a * tr.e) / 1e6  # km²/像元（10 m → 0.0001）

    rows = []
    for _, r in dist.iterrows():
        if r.geometry is None or r.geometry.is_empty:
            continue
        mask = rasterize([(r.geometry, 1)], out_shape=shape, transform=tr,
                         fill=0, all_touched=False, dtype="uint8").astype(bool)
        n_all = int(mask.sum())
        if n_all == 0:
            continue  # 完全在研究区外的区县不参与统计（例如都江堰、彭州大部）
        geom_km2 = float(r.geometry.area) / 1e6
        vals1, vals2, vald = nd1[mask], nd2[mask], dd[mask]
        f1, f2, fd = np.isfinite(vals1), np.isfinite(vals2), np.isfinite(vald)

        rows.append({
            "adcode": r.get("adcode"),
            "name": r["name"],
            "clip_frac": round(n_all * px_area / geom_km2 * 100, 1) if geom_km2 else np.nan,
            "area_in_extent_km2": round(n_all * px_area, 2),
            "valid_frac_t1": round(float(f1.mean()) * 100, 1),
            "valid_frac_t2": round(float(f2.mean()) * 100, 1),
            "ndvi_mean_t1": round(float(vals1[f1].mean()), 3) if f1.any() else np.nan,
            "ndvi_mean_t2": round(float(vals2[f2].mean()), 3) if f2.any() else np.nan,
            "ndvi_median_t2": round(float(np.median(vals2[f2])), 3) if f2.any() else np.nan,
            "high_veg_frac_t2": round(float((vals2[f2] >= 0.6).mean()) * 100, 1) if f2.any() else np.nan,
            "delta_mean": round(float(vald[fd].mean()), 3) if fd.any() else np.nan,
            "delta_mean_raw": round(float(np.nanmean(draw[mask])), 3),
            "improved_frac": round(float((vald[fd] > C.DNDVI_BREAKS[2]).mean()) * 100, 1) if fd.any() else np.nan,
            "degraded_frac": round(float((vald[fd] < C.DNDVI_BREAKS[1]).mean()) * 100, 1) if fd.any() else np.nan,
        })

    df = pd.DataFrame(rows).sort_values("ndvi_mean_t2", ascending=False)
    df.to_csv(C.STATS_CSV, index=False, encoding="utf-8-sig")
    print(df.to_string(index=False))
    print(f"\n已写出 {C.STATS_CSV}（{len(df)} 个区县与研究区有交集）")

    f2_all = np.isfinite(nd2)
    print(f"\n全区 NDVI 均值：2025-01 {np.nanmean(nd1):.3f} → 2026-01 {np.nanmean(nd2):.3f}"
          f"（Δ {np.nanmean(nd2) - np.nanmean(nd1):+.3f}）")
    print(f"高植被（NDVI≥0.6）占比 {float((nd2[f2_all] >= 0.6).mean()) * 100:.1f}%")
    print(f"最绿区县：{df.iloc[0]['name']}（{df.iloc[0]['ndvi_mean_t2']:.3f}）"
          f"；最低：{df.iloc[-1]['name']}（{df.iloc[-1]['ndvi_mean_t2']:.3f}）")
    dd_v = df.dropna(subset=["delta_mean"])
    top = dd_v.sort_values("delta_mean").iloc[-1]
    low = dd_v.sort_values("delta_mean").iloc[0]
    print(f"变化最大：{top['name']}（{top['delta_mean']:+.3f}）；"
          f"退化最明显：{low['name']}（{low['delta_mean']:+.3f}）")


if __name__ == "__main__":
    main()
