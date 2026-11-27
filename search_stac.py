"""W7-1 选景：按候选时相扫 Sentinel-2 L2A，客户端按云量排序，输出 scenes.json。

用法：python search_stac.py
说明：Earth Search 的 STAC 接口对 CQL2 云量过滤不生效（2026-11-26 实测），
      因此一次取回该时相全部场景（limit=100），在本地排序。
"""
import json
import sys
from datetime import datetime

import requests

import config as C


def search_period(start, end):
    body = {
        "collections": [C.COLLECTION],
        "bbox": list(C.BBOX),
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": C.SCENES_PER_PERIOD,
    }
    r = requests.post(C.STAC_URL, json=body, timeout=60)
    r.raise_for_status()
    return r.json().get("features", [])


def summarize(features):
    rows = []
    for f in features:
        cloud = f["properties"].get("eo:cloud_cover")
        if cloud is None:
            continue
        rows.append({
            "id": f["id"],
            "cloud": round(float(cloud), 2),
            "datetime": f["properties"]["datetime"],
            "assets": {k: f["assets"][k]["href"] for k in C.ASSETS if k in f["assets"]},
            "raster_bands": {k: f["assets"][k].get("raster:bands", [{}])[0] for k in C.ASSETS if k in f["assets"]},
        })
    rows.sort(key=lambda x: x["cloud"])
    return rows


def main():
    C.DATA.mkdir(parents=True, exist_ok=True)
    result = {"bbox": list(C.BBOX), "collection": C.COLLECTION, "periods": {}}
    print(f"{'时相':<8}{'年':<6}{'场景数':>6}{'最低云量':>10}  最优场景")
    print("-" * 78)
    for pname, (mstart, mend) in C.CANDIDATE_PERIODS.items():
        for yr in C.YEARS:
            start, end = f"{yr}-{mstart}", f"{yr}-{mend}"
            try:
                feats = search_period(start, end)
            except Exception as e:
                print(f"{pname:<8}{yr:<6}  检索失败：{type(e).__name__} {e}")
                continue
            rows = summarize(feats)
            key = f"{pname}{yr}"
            result["periods"][key] = {"window": [start, end], "count": len(rows), "scenes": rows[:5]}
            if rows:
                print(f"{pname:<8}{yr:<6}{len(rows):>6}{rows[0]['cloud']:>10}  {rows[0]['id']}")
            else:
                print(f"{pname:<8}{yr:<6}{0:>6}{'-':>10}  （无场景）")

    C.SCENES_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写出 {C.SCENES_JSON}")

    # 择优：同一时相、两年都有合格场景、取两期云量最大值最小的那一组
    best = None
    for pname in C.CANDIDATE_PERIODS:
        s1 = result["periods"].get(f"{pname}{C.YEARS[0]}", {}).get("scenes", [])
        s2 = result["periods"].get(f"{pname}{C.YEARS[1]}", {}).get("scenes", [])
        if not s1 or not s2:
            continue
        cand = {
            "period": pname,
            "T1": s1[0], "T2": s2[0],
            "worst_cloud": max(s1[0]["cloud"], s2[0]["cloud"]),
        }
        if best is None or cand["worst_cloud"] < best["worst_cloud"]:
            best = cand
    if best is None:
        print("!! 没有可用时相：检查网络或 bbox")
        sys.exit(1)
    print(f"\n>> 选定时相：{best['period']}｜两期最差云量 {best['worst_cloud']}%")
    print(f"   T1 {best['T1']['id']}  cloud={best['T1']['cloud']}  {best['T1']['datetime']}")
    print(f"   T2 {best['T2']['id']}  cloud={best['T2']['cloud']}  {best['T2']['datetime']}")
    result["selected"] = best
    C.SCENES_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
