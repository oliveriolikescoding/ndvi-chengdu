"""配置集中（RD-03）：路径、范围、时相、阈值、字体栈都从这里取，脚本内不写魔法数。"""
from pathlib import Path

# ---------- 路径 ----------
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "output"
DOCS = ROOT / "docs"
DISTRICTS = DATA / "basemap" / "chengdu_districts.json"   # 复用上周（W6）成果
SCENES_JSON = DATA / "scenes.json"
QUALITY_JSON = DATA / "quality.json"
STATS_CSV = DATA / "ndvi_by_district.csv"

# ---------- 研究区与投影 ----------
BBOX = (104.00, 30.55, 104.16, 30.76)   # xmin, ymin, xmax, ymax（WGS84）
CRS = "EPSG:32648"                       # UTM 48N，与 W6 同投影（RG-01：按纬度自动分带）
TARGET_RES = 10                          # 米，Sentinel-2 B04/B08 原生分辨率

# ---------- 数据源（免账号 STAC，2026-11-26 实测可达） ----------
STAC_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
ASSETS = {"red": "red", "nir": "nir", "scl": "scl"}   # STAC asset key

# ---------- 候选时相（先扫全部，再按时相一致性 + 云量择优） ----------
CANDIDATE_PERIODS = {
    "冬": (("01-01", "02-28")),
    "春": (("03-01", "04-30")),
    "夏前": (("05-01", "06-30")),
    "秋": (("10-01", "11-30")),
}
YEARS = (2025, 2026)

# 选景门槛
CLOUD_MAX_OK = 20.0        # 云量 ≤20% 视为合格
CLOUD_MAX_FALLBACK = 40.0  # 两期都无 ≤20% 时，退到 ≤40%
SCENES_PER_PERIOD = 100    # 单次检索上限

# ---------- 掩膜与分级 ----------
SCL_INVALID = (0, 1, 3, 8, 9, 10, 11)   # 无数据/饱和/云影/中云/高云/卷云/雪 → 置 NaN
SCL_WATER = 6
VALID_PIXEL_MIN = 0.80                   # 有效像元占比门槛（低于则换景）
HOLE_FILL_MAX_PX = 2.5                   # 孤立小孔填补半径（像元）：只填 1–2 像元的椒盐，
                                         # 大片无效区（云、水体阴影）保留，不做整片插值

NDVI_BREAKS = (-0.2, 0.0, 0.2, 0.4, 0.6, 0.8)   # 用于分级
NDVI_LABELS = ("非植被", "极低", "低", "中低", "中高", "高", "极密")
# 连续栅格配色：低→亮、高→深，亮度单调递减（RV-04 / 自检项 D9-r）；
# 「非植被」是特殊类，用灰蓝 + 斜纹，与绿色系区分（灰度下靠纹理，不靠色相）
NDVI_COLORS = ("#8FA2B0", "#C3D9A8", "#A2CB80", "#77B158", "#4C9443", "#266A39", "#083A1E")
NDVI_HATCH = {0: "//"}

DNDVI_BREAKS = (-0.15, -0.05, 0.05, 0.15)
DNDVI_LABELS = ("明显退化", "轻微退化", "基本稳定", "轻微改善", "明显改善")
DNDVI_COLORS = ("#B23A2E", "#E0876B", "#CDD3D0", "#8CBF6F", "#2E7A45")
DNDVI_HATCH = {0: "//", 1: "/"}   # 退化类加斜纹，灰度下可辨方向

# ---------- 版式与字体（RV-01/RV-02：中文宋体 + 西文 Times New Roman） ----------
FONT_LATIN = "Times New Roman"
FONT_CJK = "SimSun"
FONT_FALLBACK = ["SimSun", "Noto Serif SC", "STSong", "DejaVu Serif"]
FONT_FAMILY = [FONT_LATIN] + FONT_FALLBACK
FIG_DPI = 300
FIG_SIZE = (11.69, 8.27)   # 英寸，＝ A4 横版 297×210 mm，@300dpi → 3507×2481 px（RV-03）
TEXT_DARK = "#1D2733"
TEXT_MUTED = "#4E5965"
BASEMAP_GRAY = "#F5F7FA"
