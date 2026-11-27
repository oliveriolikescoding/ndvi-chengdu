"""W7-2 算 NDVI（v3）：gdalwarp 直接按 bbox 从 COG 取窗 → 拼幅 → 反射率校正 → NDVI → SCL 掩膜。

网络实测（2026-11-26，本机）：
  · 到 sentinel-cogs(S3 us-west-2) 的短区间请求很快（8 MB / 2.3 s），
    但持续性大文件传输会掉到 ~70 KB/s（169 MB 整景不可下）；
  · python-requests / curl 的整档下载同样卡死，只有 Schannel 客户端（PowerShell）能跑满短区间。
  → 所以不用「整块下载」，而是让 GDAL 自己按需取块：先把 CPL_VSIL_CURL_CHUNK_SIZE 顶到上限 10 MB
    （上限 10485760，超过会被 GDAL 回退成 16 KB，实测那样会慢到 100 s+/景），
    再用 gdalwarp 只裁 bbox。单景整窗约 100 s，2 tile × 3 波段 × 2 期 ≈ 15 分钟。

用法：python fetch_ndvi.py           全流程
      python fetch_ndvi.py --test    只跑 T1 的 B04，验证链路
"""
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import requests
from shapely.geometry import shape, box
from shapely.ops import unary_union

import geoenv  # noqa: F401
import rasterio
from pyproj import Transformer

import config as C

QGIS_BIN = Path(r"C:\Program Files\QGIS 3.44.15\bin")
GDALWARP = QGIS_BIN / "gdalwarp.exe"
QGIS_PROJ = Path(r"C:\Program Files\QGIS 3.44.15\share\proj")
TMP = C.DATA / "tmp"


def gdal_env():
    env = os.environ.copy()
    if (QGIS_PROJ / "proj.db").exists():
        env["PROJ_LIB"] = str(QGIS_PROJ)
        env["PROJ_DATA"] = str(QGIS_PROJ)
    # 分块大小：窗口读取只需几 MB，块太大会把「读一块」变成「拉 10 MB」，
    # 实测在本机受限带宽下会浪费 4–5 倍流量；用环境变量可现场调（默认 1 MB）
    env["CPL_VSIL_CURL_CHUNK_SIZE"] = os.environ.get("ND_CHUNK", "1048576")
    env["CPL_VSIL_CURL_CACHE_SIZE"] = "268435456"
    env["VSI_CACHE"] = "TRUE"
    env["VSI_CACHE_SIZE"] = "268435456"
    env["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
    env["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".tif"
    return env


def log(msg, to_list=None):
    print(msg, flush=True)
    if to_list is not None:
        to_list.append(msg)


def target_extent():
    tr = Transformer.from_crs("EPSG:4326", C.CRS, always_xy=True)
    xmin, ymin = tr.transform(C.BBOX[0], C.BBOX[1])
    xmax, ymax = tr.transform(C.BBOX[2], C.BBOX[3])
    xmin, ymin = round(xmin / C.TARGET_RES) * C.TARGET_RES, round(ymin / C.TARGET_RES) * C.TARGET_RES
    xmax, ymax = round(xmax / C.TARGET_RES) * C.TARGET_RES, round(ymax / C.TARGET_RES) * C.TARGET_RES
    return (xmin, ymin, xmax, ymax), int((xmax - xmin) / C.TARGET_RES), int((ymax - ymin) / C.TARGET_RES)


def scenes_on_date(date_str):
    body = {"collections": [C.COLLECTION], "bbox": list(C.BBOX),
            "datetime": f"{date_str}T00:00:00Z/{date_str}T23:59:59Z", "limit": 20}
    r = requests.post(C.STAC_URL, json=body, timeout=90)
    r.raise_for_status()
    feats = [f for f in r.json()["features"] if f["properties"].get("eo:cloud_cover") is not None]
    return sorted(feats, key=lambda f: f["properties"]["eo:cloud_cover"])


def minimal_tiles(feats):
    """贪心求覆盖 bbox 的最少 tile 组合（>99.5% 即认为覆盖）。"""
    target = box(*C.BBOX)
    geoms = {f["id"]: shape(f["geometry"]).buffer(0) for f in feats}
    for n in (1, 2, 3):
        for combo in itertools.combinations(geoms, n):
            u = unary_union([geoms[c] for c in combo]).intersection(target)
            if u.area / target.area > 0.995:
                return [f for f in feats if f["id"] in combo]
    return feats


def prepare_period(tag, date_str, log_list):
    """只挑覆盖研究区的最少 tile，不做整块下载（见 gdal_env() 里关于网络与 chunk 的说明）。"""
    feats = minimal_tiles(scenes_on_date(date_str))
    log(f"[{tag}] {date_str} 采用 {len(feats)} 个 tile：" +
        "、".join(f["id"] for f in feats), log_list)
    return feats


def warp_local(inputs, out_path, extent, resampling="bilinear"):
    """本地或远端（/vsicurl）裁剪 + 拼幅到统一网格。"""
    xmin, ymin, xmax, ymax = extent
    cmd = [str(GDALWARP), "-tr", str(C.TARGET_RES), str(C.TARGET_RES),
           "-te", str(xmin), str(ymin), str(xmax), str(ymax),
           "-t_srs", C.CRS, "-r", resampling,
           "-srcnodata", "0", "-dstnodata", "0",
           "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES",
           *[str(p) for p in inputs], str(out_path)]
    t0 = time.time()
    # 带宽最差时单次拼幅可达 20 分钟，超时放宽到 60 分钟
    res = subprocess.run(cmd, env=gdal_env(), capture_output=True, text=True, timeout=3600)
    if res.returncode != 0:
        raise RuntimeError(f"gdalwarp 失败：{(res.stderr or res.stdout)[-800:]}")
    print(f"   拼幅完成 {time.time()-t0:.0f}s → {Path(out_path).name}", flush=True)
    return out_path


def warp_ok(path, w, h):
    """已完成的拼接块是否可用（尺寸对得上且不是全 0——被超时杀掉的文件正好是全 0）。"""
    p = Path(path)
    if not p.exists() or p.stat().st_size < 1000:
        return False
    try:
        with rasterio.open(p) as ds:
            if (ds.width, ds.height) != (w, h):
                return False
            a = ds.read(1, out_shape=(min(ds.height, 800), min(ds.width, 800)))
        return bool(a.any())
    except Exception:
        return False


def read_tif(path):
    with rasterio.open(path) as ds:
        return ds.read(1), ds.transform


def fill_small_holes(arr, max_px=C.HOLE_FILL_MAX_PX):
    """只填补 1–2 像元的孤立小孔（椒盐噪声），大片无效区原样保留。

    冬季低太阳高度角下，暗像元（深色屋顶、阴影、窄水面）的红光反射率会被 BOA 偏移压到
    0 附近，判为不可信后会在图面上形成密集白点。这类点不是数据缺失，只是不满足反射率
    正性约束，用最近有效像元补上比留洞更接近真实地表；大面积的掩膜（云、云影）不动。
    """
    from scipy.ndimage import distance_transform_edt

    valid = np.isfinite(arr)
    inv = ~valid
    if not inv.any() or valid.sum() == 0:
        return arr
    dist, inds = distance_transform_edt(inv, return_indices=True)
    fill = inv & (dist <= max_px)
    out = arr.copy()
    out[fill] = arr[tuple(inds[:, fill])]
    print(f"   小孔填补 {int(fill.sum()):,} 像元（{fill.mean()*100:.1f}%），"
          f"有效像元 {valid.mean()*100:.1f}% → {np.isfinite(out).mean()*100:.1f}%", flush=True)
    return out


def process_period(tag, date_str, extent, w, h, log_list):
    feats = prepare_period(tag, date_str, log_list)
    for asset, rs in (("red", "bilinear"), ("nir", "bilinear"), ("scl", "near")):
        inputs = [f"/vsicurl/{f['assets'][asset]['href']}" for f in feats]
        out = TMP / f"warp_{tag}_{asset}.tif"
        if warp_ok(out, w, h):
            log(f"   取 {asset}：已有可用拼接块，跳过", log_list)
            continue
        log(f"   取 {asset}（{len(inputs)} 个 tile 拼接）", log_list)
        warp_local(inputs, out, extent, rs)

    red, tr = read_tif(TMP / f"warp_{tag}_red.tif")
    nir, _ = read_tif(TMP / f"warp_{tag}_nir.tif")
    scl, _ = read_tif(TMP / f"warp_{tag}_scl.tif")
    if red.shape != (h, w):
        raise RuntimeError(f"网格不符 {red.shape} != {(h, w)}")

    meta = feats[0]["assets"]["red"]["raster:bands"][0]
    scale, offset = float(meta.get("scale", 1 / 10000)), float(meta.get("offset", 0.0))
    log(f"   反射率校正 scale={scale} offset={offset}（BOA_ADD_OFFSET）", log_list)

    red_r = red.astype("float32") * scale + offset
    nir_r = nir.astype("float32") * scale + offset
    valid = (red > 0) & (nir > 0) & (scl > 0)
    valid &= ~np.isin(scl.astype("int16"), C.SCL_INVALID)
    denom = nir_r + red_r
    # 关键：BOA 偏移后深色像元（水面、浓阴影）反射率会掉到 0 附近，
    # 直接相除会炸出 ±1 的假极值（实测占 4%）。约束「两波段反射率之和 > 0.02」即可，
    # 不必要求单波段 > 0.002——那会把冬季 20% 的暗像元一起丢掉。
    valid &= (red_r > 0.002) & (nir_r > 0.002) & (denom > 0.002)
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(valid, (nir_r - red_r) / denom, np.nan)
    ndvi = np.clip(ndvi, -1, 1).astype("float32")
    ndvi = fill_small_holes(ndvi, C.HOLE_FILL_MAX_PX)

    st = {
        "valid_frac": float(np.isfinite(ndvi).mean()),
        "water_frac": float((scl == C.SCL_WATER).mean()),
        "ndvi_min": float(np.nanmin(ndvi)), "ndvi_max": float(np.nanmax(ndvi)),
        "ndvi_mean": float(np.nanmean(ndvi)), "ndvi_median": float(np.nanmedian(ndvi)),
        "scenes": [f["id"] for f in feats],
        "cloud_cover": [round(f["properties"]["eo:cloud_cover"], 3) for f in feats],
    }
    log(f"   {tag} 有效像元 {st['valid_frac']*100:.1f}%｜NDVI 均值 {st['ndvi_mean']:.3f}"
        f"｜中位 {st['ndvi_median']:.3f}｜值域 {st['ndvi_min']:.3f}–{st['ndvi_max']:.3f}", log_list)
    return ndvi, tr, st


def write_tif(path, arr, transform):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                       count=1, dtype="float32", crs=C.CRS, transform=transform,
                       nodata=np.nan, compress="deflate", tiled=True) as ds:
        ds.write(arr, 1)


def main():
    test = "--test" in sys.argv
    keep = "--keep" in sys.argv
    scenes = json.loads(C.SCENES_JSON.read_text(encoding="utf-8"))
    sel = scenes["selected"]
    t1_date, t2_date = sel["T1"]["datetime"][:10], sel["T2"]["datetime"][:10]
    log(f"选定时相：{sel['period']}｜T1={t1_date}  T2={t2_date}")

    extent, w, h = target_extent()
    log(f"目标范围 {extent} → {w}×{h} @ {C.TARGET_RES} m {C.CRS}")

    log_list = []
    quality = {"period": sel["period"],
               "T1": {"date": t1_date}, "T2": {"date": t2_date},
               "grid": {"w": w, "h": h, "res": C.TARGET_RES, "crs": C.CRS, "extent": list(extent)},
               "log": log_list}

    if test:
        feats = prepare_period("T1", t1_date, log_list)
        warp_local([f"/vsicurl/{f['assets']['red']['href']}" for f in feats],
                   TMP / "test_red.tif", extent)
        a, _ = read_tif(TMP / "test_red.tif")
        v = a > 0
        log(f"TEST 形状 {a.shape}｜有效 {v.mean()*100:.1f}%｜DN 值域 {a[v].min()}–{a.max()}")
        return

    res = {}
    for tag, date_str in (("T1", t1_date), ("T2", t2_date)):
        ndvi, tr, st = process_period(tag, date_str, extent, w, h, log_list)
        quality[tag].update(st)
        write_tif(C.DATA / f"ndvi_{tag}.tif", ndvi, tr)
        res[tag] = ndvi

    d = (res["T2"] - res["T1"]).astype("float32")
    write_tif(C.DATA / "ndvi_delta.tif", d, tr)
    dv = np.isfinite(d)
    quality["delta"] = {
        "valid_frac": float(dv.mean()),
        "mean": float(np.nanmean(d)), "median": float(np.nanmedian(d)),
        "improved_frac": float((d[dv] > C.DNDVI_BREAKS[2]).mean()),
        "degraded_frac": float((d[dv] < C.DNDVI_BREAKS[1]).mean()),
    }
    log(f"变化 ΔNDVI 均值 {quality['delta']['mean']:+.3f}｜中位 {quality['delta']['median']:+.3f}"
        f"｜改善 {quality['delta']['improved_frac']*100:.1f}%｜退化 {quality['delta']['degraded_frac']*100:.1f}%",
        log_list)
    C.QUALITY_JSON.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    log("已写出 ndvi_T1.tif / ndvi_T2.tif / ndvi_delta.tif + quality.json")

    if not keep:
        removed = 0
        for p in TMP.glob("*.tif"):
            if p.name.startswith("warp_"):
                continue
            p.unlink()
            removed += 1
        log(f"已清理中间瓦片 {removed} 个文件")


if __name__ == "__main__":
    main()


