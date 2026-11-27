"""环境修补（RD-08）：本机 PROJ_LIB 被 PostgreSQL 的 postgis proj 目录污染（里面没有 proj.db），
导致 rasterio 所有 EPSG 查询报 "Cannot find proj.db"。任何脚本 import rasterio 之前先 import 本模块。
"""
import os
import pathlib
import site
import sys

_CANDIDATES = [
    pathlib.Path(sys.prefix) / "Lib" / "site-packages" / "rasterio" / "proj_data",
]
for sp in site.getsitepackages() if hasattr(site, "getsitepackages") else []:
    _CANDIDATES.append(pathlib.Path(sp) / "rasterio" / "proj_data")

for cand in _CANDIDATES:
    if (cand / "proj.db").exists():
        os.environ["PROJ_LIB"] = str(cand)
        os.environ["PROJ_DATA"] = str(cand)
        break
else:  # 找不到就清掉坏值，让 GDAL 用自己的默认
    os.environ.pop("PROJ_LIB", None)
    os.environ.pop("PROJ_DATA", None)

# COG 直读优化：只认 .tif，避免 S3 上做目录列举
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
os.environ.setdefault("VSI_CACHE", "TRUE")
