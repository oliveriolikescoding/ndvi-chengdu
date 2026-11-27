# -*- coding: utf-8 -*-
"""W7-5 QGIS 版布局：栅格伪彩色 + 与 Python 版同一套图面标准（A4 横版 300 dpi）。

与 matplotlib 版的分工：
  · matplotlib 版走「代码可控」路线，图面元素全用坐标画；
  · 本脚本走「QGIS 打印布局」路线，证明同一份数据能出 QGIS 工程级成图
    （比例尺、图廓注记、图例都是布局对象，客户拿到 .qgz/PDF 能直接改）。
图例不用 QgsLayoutItemLegend（它会带出 "Band 1 (Gray)" 这类噪声行），
改用色块 + 文字自己排，保证和 Python 版视觉一致。

运行（必须用 QGIS 自带 python）：
    $env:QT_QPA_PLATFORM="offscreen"; $env:QT_QPA_FONTDIR="C:\Windows\Fonts"
    & 'C:\Program Files\QGIS 3.44.15\bin\python-qgis-ltr.bat' qgis_ndvi_layout.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemMapGrid,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsUnitTypes,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont

BASE = Path(__file__).resolve().parent
NDVI = BASE / "data" / "ndvi_T2.tif"
DISTRICTS = BASE / "data" / "basemap" / "chengdu_districts.json"
OUT_PDF = BASE / "ndvi_layout.pdf"
OUT_PNG = BASE / "ndvi_layout.png"
OUT_SVG = BASE / "ndvi_layout.svg"
CRS_UTM = "EPSG:32648"

FONT_LATIN = "Times New Roman"
FONT_CJK = "SimSun"

MAP_X, MAP_Y, MAP_W = 12.0, 16.0, 100.0
MAP_H = MAP_W * 2315 / 1552   # 高 = 宽 × (2315/1552)
RAMP = [
    (-1.00, "#8FA2B0", "非植被（< −0.2）"),
    (-0.20, "#C3D9A8", "极低（−0.2 ~ 0）"),
    (0.00, "#A2CB80", "低（0 ~ 0.2）"),
    (0.20, "#77B158", "中低（0.2 ~ 0.4）"),
    (0.40, "#4C9443", "中高（0.4 ~ 0.6）"),
    (0.60, "#266A39", "高（0.6 ~ 0.8）"),
    (0.80, "#083A1E", "极密（≥ 0.8）"),
]
INVALID = ("#D3D9DF", "无效／掩膜")


def font(size: float, bold: bool = False) -> QFont:
    f = QFont(FONT_CJK)
    f.setPointSizeF(size)
    f.setBold(bold)
    try:
        f.setFamilies([FONT_LATIN, FONT_CJK, "Noto Serif SC", "DejaVu Serif"])
    except AttributeError:
        pass
    return f


def add_label(layout, text, x, y, w, h, size, color="#12233A", bold=False, align=Qt.AlignLeft):
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setFont(font(size, bold))
    item.setFontColor(QColor(color))
    item.setHAlign(align)
    item.setVAlign(Qt.AlignTop)
    if bold:
        tf = item.textFormat()
        buf = tf.buffer()
        buf.setEnabled(True)
        buf.setSize(0.11)
        buf.setSizeUnit(QgsUnitTypes.RenderMillimeters)
        buf.setColor(QColor(color))
        buf.setOpacity(1.0)
        buf.setFillBufferInterior(True)
        tf.setBuffer(buf)
        item.setTextFormat(tf)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(item)
    return item


def add_swatch(layout, color, x, y, w=6.0, h=3.6):
    """色块用「空文字 + 背景色」的标签实现：QgsLayoutItemShape 的 setShape 在 3.44 已不可用。"""
    item = QgsLayoutItemLabel(layout)
    item.setText("")
    item.setBackgroundEnabled(True)
    item.setBackgroundColor(QColor(color))
    item.setFrameEnabled(True)
    item.setFrameStrokeColor(QColor("#FFFFFF"))
    item.setFrameStrokeWidth(QgsLayoutMeasurement(0.2, QgsUnitTypes.LayoutMillimeters))
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(item)
    return item


def main() -> int:
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        project = QgsProject.instance()
        project.setCrs(QgsCoordinateReferenceSystem(CRS_UTM))

        if not NDVI.exists():
            print(f"缺输入：{NDVI}（先跑 fetch_ndvi.py）")
            return 2

        # 无效像元（原图 nodata=nan）在 QGIS 里会显示成白洞，与 Python 版的中性灰不一致。
        # 做法：另存一份 float32 显示副本，把 nan 换成 -9999 并声明 nodata，色带里给它一个灰档。
        from osgeo import gdal
        import numpy as np
        DISP = BASE / "data" / "ndvi_T2_disp.tif"
        src = gdal.Open(str(NDVI))
        arr = src.GetRasterBand(1).ReadAsArray().astype("float32")
        arr[~np.isfinite(arr)] = -9999.0
        drv = gdal.GetDriverByName("GTiff")
        dst = drv.Create(str(DISP), src.RasterXSize, src.RasterYSize, 1, gdal.GDT_Float32)
        dst.SetGeoTransform(src.GetGeoTransform())
        dst.SetProjection(src.GetProjection())
        band = dst.GetRasterBand(1)
        band.WriteArray(arr)
        band.FlushCache()
        dst = None
        src = None

        rl = QgsRasterLayer(str(DISP), "NDVI", "gdal")
        if not rl.isValid():
            print("栅格加载失败")
            return 2
        print(f"栅格 {rl.width()}×{rl.height()}，CRS {rl.crs().authid()}")
        rl.setName("NDVI")

        shader = QgsColorRampShader()
        shader.setColorRampType(QgsColorRampShader.Discrete)
        items = [QgsColorRampShader.ColorRampItem(-9999.0, QColor(INVALID[0]), "无效／掩膜")]
        items += [QgsColorRampShader.ColorRampItem(v, QColor(c), lab) for v, c, lab in RAMP]
        shader.setColorRampItemList(items)
        rs = QgsRasterShader()
        rs.setRasterShaderFunction(shader)
        renderer = QgsSingleBandPseudoColorRenderer(rl.dataProvider(), 1, rs)
        rl.setRenderer(renderer)
        rl.triggerRepaint()

        districts = QgsVectorLayer(str(DISTRICTS), "成都市区（县）界线", "ogr")
        if districts.isValid():
            sym = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "#1A2430",
                                              "outline_width": "0.18"})
            districts.renderer().setSymbol(sym)
            districts.triggerRepaint()

        layers = [rl] + ([districts] if districts.isValid() else [])
        project.addMapLayers(layers)

        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName("ND-01 植被覆盖度")
        page = layout.pageCollection().pages()[0]
        page.setPageSize(QgsLayoutSize(297, 210, QgsUnitTypes.LayoutMillimeters))

        map_item = QgsLayoutItemMap(layout)
        map_item.attemptMove(QgsLayoutPoint(MAP_X, MAP_Y, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(MAP_W, MAP_H, QgsUnitTypes.LayoutMillimeters))
        map_item.setCrs(QgsCoordinateReferenceSystem(CRS_UTM))
        map_item.setLayers(layers)
        map_item.setBackgroundColor(QColor("#FFFFFF"))
        map_item.setFrameEnabled(True)
        map_item.setFrameStrokeColor(QColor("#B9C2CC"))
        layout.addLayoutItem(map_item)

        ext = rl.extent()
        map_item.setExtent(ext)          # 图幅严格等于数据范围，四周不留白边
        denom = ext.width() / (MAP_W / 1000)
        print(f"图幅 {ext.width()/1000:.2f} × {ext.height()/1000:.2f} km，"
              f"比例尺 1 : {denom:,.0f}")

        grid = map_item.grid()
        grid.setEnabled(True)
        grid.setIntervalX(2000)
        grid.setIntervalY(2000)
        grid.setStyle(QgsLayoutItemMapGrid.FrameAnnotationsOnly)
        grid.setAnnotationEnabled(True)
        for side, direction in ((QgsLayoutItemMapGrid.Top, QgsLayoutItemMapGrid.Horizontal),
                                (QgsLayoutItemMapGrid.Bottom, QgsLayoutItemMapGrid.Horizontal),
                                (QgsLayoutItemMapGrid.Left, QgsLayoutItemMapGrid.Vertical),
                                (QgsLayoutItemMapGrid.Right, QgsLayoutItemMapGrid.Vertical)):
            grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, side)
            grid.setAnnotationDirection(direction, side)
        grid.setAnnotationFormat(QgsLayoutItemMapGrid.CustomFormat)
        grid.setAnnotationExpression("@grid_number / 1000")
        grid.setAnnotationPrecision(0)
        grid.setAnnotationFont(font(6))
        grid.setAnnotationFontColor(QColor("#4A5A6A"))
        grid.setAnnotationFrameDistance(1.0)
        map_item.updateBoundingRect()
        map_item.invalidateCache()
        map_item.refresh()

        pic = QgsLayoutItemPicture(layout)
        pic.setPicturePath(":/images/north_arrows/default.svg")
        try:
            pic.setMode(QgsLayoutItemPicture.FormatSVG)
        except Exception:
            pass
        pic.attemptMove(QgsLayoutPoint(MAP_X + MAP_W - 8.5, MAP_Y + 1.5,
                                       QgsUnitTypes.LayoutMillimeters))
        pic.attemptResize(QgsLayoutSize(7, 9.5, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(pic)

        # ---- 比例尺（自绘；放在右栏图例下方，不压影像） ----
        seg_km = 4.0
        seg_mm = seg_km * 1000 * 1000 / denom          # 4 km 在纸面上的毫米数
        sx, sy = 118.0, 70.0
        for i in range(2):
            add_swatch(layout, "#243447" if i == 0 else "#F7F9FB",
                       sx + i * seg_mm, sy, seg_mm, 1.7)
        for i in range(3):
            txt = ["0", f"{seg_km:.0f}", f"{seg_km*2:.0f} km"][i]
            add_label(layout, txt, sx + i * seg_mm - 5.0, sy + 1.9, 10, 3.0, 6.6, "#243447",
                      align=Qt.AlignHCenter)

        # ---- 图例（色块 + 文字，自己排；右栏顶部） ----
        lx, ly = 118.0, 18.0
        add_label(layout, "NDVI 分级（无量纲）", lx, ly, 80, 5, 8.6, "#1D2733")
        for i, (_, color, lab) in enumerate(RAMP):
            add_swatch(layout, color, lx, ly + 6.5 + i * 4.6)
            add_label(layout, lab, lx + 7.2, ly + 5.9 + i * 4.6, 60, 4.4, 7.2, "#2B3A47")
        add_swatch(layout, INVALID[0], lx, ly + 6.5 + len(RAMP) * 4.6)
        add_label(layout, INVALID[1], lx + 7.2, ly + 5.9 + len(RAMP) * 4.6, 60, 4.4, 7.2, "#2B3A47")

        # ---- 图题与图注（置于图下） ----
        add_label(layout, "图 1　成都城区植被覆盖度（NDVI）", 12, 171, 273, 6,
                  10, align=Qt.AlignHCenter)
        add_label(layout,
                  "　　研究区 104.00–104.16°E / 30.55–30.76°N，15.52 × 23.15 km；"
                  "Sentinel-2 L2A，2026-01-12（云量 0.1%），10 m 网格，UTM zone 48N。\n"
                  "　　NDVI =（B08 - B04）/（B08 + B04），反射率按 scale 0.0001、offset -0.1 校正；"
                  "SCL 掩除云、云影、雪与无数据像元，≤2 像元孤立小孔以邻域填补；有效像元 97%。\n"
                  "　　区县均值按 10 m 像元面积加权，共 9 个区县；全区 2026-01 NDVI 均值 0.48、中位 0.48，"
                  "NDVI ≥ 0.6 的像元占 37.9%。\n"
                  "　　影像来源 Sentinel-2 L2A（ESA / Copernicus，Public Domain，经 Element 84 Earth Search STAC 获取）；"
                  "区县界据 DataV.GeoAtlas，仅作空间参照，非法定界线。\n"
                  "　　投影 EPSG:32648（WGS 84 / UTM zone 48N）；制图日期 2026-11-27；"
                  "本图为分析图件，非标准地图，无审图号。",
                  12, 178, 273, 28, 6.6, "#262626")

        for p in (OUT_PDF, OUT_PNG, OUT_SVG):
            if p.exists():
                p.unlink()
        exporter = QgsLayoutExporter(layout)
        pdf_settings = QgsLayoutExporter.PdfExportSettings()
        pdf_settings.dpi = 300
        res = exporter.exportToPdf(str(OUT_PDF), pdf_settings)
        print(f"{'OK' if res == QgsLayoutExporter.Success else 'FAIL'} PDF {OUT_PDF}（code {res}）")

        img = QgsLayoutExporter.ImageExportSettings()
        img.dpi = 300
        res2 = exporter.exportToImage(str(OUT_PNG), img)
        print(f"{'OK' if res2 == QgsLayoutExporter.Success else 'FAIL'} PNG {OUT_PNG}（code {res2}）")

        svg = QgsLayoutExporter.SvgExportSettings()
        svg.dpi = 300
        svg.forceVectorOutput = True
        svg.textRenderFormat = Qgis.TextRenderFormat.AlwaysOutlines
        res3 = exporter.exportToSvg(str(OUT_SVG), svg)
        print(f"{'OK' if res3 == QgsLayoutExporter.Success else 'FAIL'} SVG {OUT_SVG}（code {res3}）")
        return 0 if res == QgsLayoutExporter.Success else 1
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    sys.exit(main())







