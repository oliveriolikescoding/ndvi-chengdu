"""W7-2b 变化量的偏移校正：两期 NDVI 相减前，先把「大气/观测条件」造成的整体偏移剔掉。

为什么必须做：
  2025-01-03 与 2026-01-12 两期影像的反射率水平不同（红光全区均值 0.032 vs 0.023，
  近红外 0.074 vs 0.079）——2025 那期明显偏「亮」，是冬季气溶胶/薄霾的典型特征。
  直接相减得到 ΔNDVI 全区中位 +0.136、72% 像元「改善」，但 200×200 像元分块
  的均值标准差只有 0.043、最小值仍有 +0.045：变化在空间上几乎一致，
  说明这是整体偏移，不是真的大面积复绿。

做法（最小假设）：
  认定全区中位差为条件性偏移，把它减掉，使 ΔNDVI 的中位数为 0；
  空间格局（分块差异、局部斑块）全部保留，只是不再有整体偏色。
  原始 Δ 同时保留在 ndvi_delta.tif，两组数字都写进 quality.json 和交付说明，
  不隐藏原始结果。

用法：python ndvi_change.py
输出：data/ndvi_delta_norm.tif、data/change_summary.json
"""
import json

import numpy as np

import geoenv  # noqa: F401
import rasterio

import config as C


def main():
    with rasterio.open(C.DATA / "ndvi_delta.tif") as ds:
        d = ds.read(1)
        prof = ds.profile.copy()

    f = np.isfinite(d)
    med = float(np.median(d[f]))
    dn = (d - med).astype("float32")
    dn[~f] = np.nan

    prof.update(dtype="float32", nodata=np.nan, compress="deflate", tiled=True)
    with rasterio.open(C.DATA / "ndvi_delta_norm.tif", "w", **prof) as ds:
        ds.write(dn, 1)

    fn = np.isfinite(dn)
    summary = {
        "offset_removed": round(med, 4),
        "rationale": "两期影像反射率整体水平不同（红光 0.032 vs 0.023），判为大气/观测条件差异；"
                     "以全区中位差作条件性偏移校正，中位归零。",
        "raw": {
            "median": round(med, 4),
            "mean": round(float(np.nanmean(d)), 4),
            "improved_frac": round(float((d[f] > 0.05).mean()), 4),
            "degraded_frac": round(float((d[f] < -0.05).mean()), 4),
        },
        "normalized": {
            "median": round(float(np.median(dn[fn])), 4),
            "mean": round(float(np.nanmean(dn)), 4),
            "improved_frac": round(float((dn[fn] > 0.05).mean()), 4),
            "degraded_frac": round(float((dn[fn] < -0.05).mean()), 4),
            "stable_frac": round(float((np.abs(dn[fn]) <= 0.05).mean()), 4),
            "p5_p95": [round(float(np.percentile(dn[fn], 5)), 3),
                       round(float(np.percentile(dn[fn], 95)), 3)],
        },
    }
    (C.DATA / "change_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"全区中位偏移 {med:+.3f} 已扣除")
    print("原始：改善 {:.1f}% / 退化 {:.1f}%".format(
        summary["raw"]["improved_frac"] * 100, summary["raw"]["degraded_frac"] * 100))
    print("校正后：改善 {:.1f}% / 退化 {:.1f}% / 基本稳定 {:.1f}%（阈值 ±0.05）".format(
        summary["normalized"]["improved_frac"] * 100,
        summary["normalized"]["degraded_frac"] * 100,
        summary["normalized"]["stable_frac"] * 100))
    print(f"校正后 ΔNDVI 值域（5–95 分位）{summary['normalized']['p5_p95']}")
    print("已写出 data/ndvi_delta_norm.tif、data/change_summary.json")


if __name__ == "__main__":
    main()
