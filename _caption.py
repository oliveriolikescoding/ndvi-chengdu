# -*- coding: utf-8 -*-
"""_caption.py —— 论文式图注（RV-16）。

规矩（照 RV-16 与 GB/T 7713.2—2022 §5.4.3、CY/T 171—2019 §7.2 排）：
    · 图号＋题名居中置**图下**，图上不放标题；字号小于正文、黑体不加粗；
    · “图”与号之间 0.14 em 细空，号与题名之间按墨迹给 0.72 em 字身；
    · 整图注置图题**下方**、左对齐、首行缩进 2 字、排字宽度不超图宽；
    · 中英混排逐段落字：中文宋体、西文与数字 Times New Roman；
    · 各条用分号、末条句号；断行不切西文数字串，并做简易避头尾。
"""
from __future__ import annotations

import re

from matplotlib import font_manager

_LATIN_TOKEN = re.compile(r"[+\-−]?[A-Za-z0-9][A-Za-z0-9\.\-_/+:]*")
_NUMBER = re.compile(r"[+\-−]?[0-9][0-9.,]*")
_UNIT = re.compile(r" ?(?:pp|min|ms|s|h|m|km|GB|MB|KB|dpi|pt|px|dB)(?![A-Za-z])")
_NO_LINE_END = "（【《〈“‘〔"
_NO_LINE_START = "）】》〉”’〕、。，；：！？%‰"

NOTE_PT = 8.8
TITLE_PT = 10.5
LINE_SPACING = 1.6


def _seg(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for ch in text:
        k = 1 if ord(ch) < 128 else 0
        if out and out[-1][0] == k:
            out[-1] = (k, out[-1][1] + ch)
        else:
            out.append((k, ch))
    return out


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(text):
        m = _LATIN_TOKEN.match(text, i)
        if m and m.end() > i:
            tok = m.group(0)
            end = m.end()
            if end < len(text) and text[end] in "%‰℃":
                tok += text[end]
                end += 1
            # 数字与紧随其后的短单位（pp / min / GB / km …）不拆
            if _NUMBER.fullmatch(tok):
                um = _UNIT.match(text, end)
                if um:
                    tok += um.group(0)
                    end = um.end()
                # 数字区间（0 至 5）整体不拆行
                rm = re.match(r" ?至 ?[+\-−]?[0-9][0-9.,]*", text[end:])
                if rm:
                    tok += rm.group(0)
                    end += rm.end()
            i = end
            out.append(tok)
        else:
            out.append(text[i])
            i += 1
    return out


def _mk_probe(fig, fp):
    """量字宽：两端加哨兵字做差，避免纯空格串 extent 宽为 0 把全角空格吞掉。"""
    p = fig.text(0, -40, "", fontproperties=fp)
    ren = fig.canvas.get_renderer()

    def ext(s: str) -> float:
        p.set_text(s)
        return p.get_window_extent(renderer=ren).width * 72 / fig.dpi

    def width_pt(s: str) -> float:
        if not s:
            return 0.0
        return ext("x" + s + "x") - ext("xx")

    return p, width_pt


def _wrap(fig, text: str, avail_pt: float, cjk_fp, latin_fp) -> list[str]:
    p0, w0 = _mk_probe(fig, cjk_fp)
    p1, w1 = _mk_probe(fig, latin_fp)
    w = {0: w0, 1: w1}

    def width(s: str) -> float:
        return sum(w[k](seg) for k, seg in _seg(s))

    lines, cur = [], ""
    for tok in _tokens(text):
        cand = cur + tok
        if cur and width(cand) > avail_pt:
            if cur[-1] in _NO_LINE_END and len(cur) > 1:
                lines.append(cur[:-1])
                cur = cur[-1] + tok
            else:
                lines.append(cur)
                cur = tok
        else:
            cur = cand
    if cur:
        lines.append(cur)
    for i in range(1, len(lines)):
        while lines[i] and lines[i][0] in _NO_LINE_START and width(lines[i - 1] + lines[i][0]) <= avail_pt * 1.02:
            lines[i - 1] += lines[i][0]
            lines[i] = lines[i][1:]
    p0.remove()
    p1.remove()
    return lines


def _draw(fig, x0: float, y: float, text: str, cjk_fp, latin_fp, color: str) -> None:
    p0, w0 = _mk_probe(fig, cjk_fp)
    p1, w1 = _mk_probe(fig, latin_fp)
    w = {0: w0, 1: w1}
    fw = fig.get_figwidth() * 72
    x = x0
    for k, seg in _seg(text):
        fig.text(x, y, seg, fontproperties=(cjk_fp if k == 0 else latin_fp),
                 ha="left", va="bottom", color=color)
        x += w[k](seg) / fw
    p0.remove()
    p1.remove()


def size_pt(fig, text: str, cjk_fp, latin_fp, rotation: int = 0) -> float:
    """返回混排文本在图坐标下的长度（rotation=90 时是高度方向）。"""
    p0, w0 = _mk_probe(fig, cjk_fp)
    p1, w1 = _mk_probe(fig, latin_fp)
    w = {0: w0, 1: w1}
    total = sum(w[k](seg) for k, seg in _seg(text))
    denom = (fig.get_figwidth() * 72) if rotation in (0, 180) else (fig.get_figheight() * 72)
    p0.remove()
    p1.remove()
    return total / denom


def mix(fig, x: float, y: float, text: str, cjk_fp, latin_fp,
        color: str = "#262626", ha: str = "left", rotation: int = 0) -> None:
    """在任意位置按段混排一段文字：中文走 cjk_fp、西文与数字走 latin_fp。

    轴标签、刻度、图例、色标标题这些用 set_label / set_xticklabels 做不到混排的地方，
    一律改用这个函数直接画。rotation=90 时沿 y 方向向上递推。
    """
    p0, w0 = _mk_probe(fig, cjk_fp)
    p1, w1 = _mk_probe(fig, latin_fp)
    w = {0: w0, 1: w1}
    total = sum(w[k](seg) for k, seg in _seg(text))
    horizontal = rotation in (0, 180)
    denom = (fig.get_figwidth() if horizontal else fig.get_figheight()) * 72
    if ha == "center":
        if horizontal:
            x -= (total / denom) / 2
        else:
            y -= (total / denom) / 2
    elif ha == "right":
        if horizontal:
            x -= total / denom
        else:
            y -= total / denom
    for k, seg in _seg(text):
        fp = cjk_fp if k == 0 else latin_fp
        if horizontal:
            fig.text(x, y, seg, fontproperties=fp, ha="left", va="bottom", color=color)
            x += w[k](seg) / denom
        else:
            fig.text(x, y, seg, fontproperties=fp, rotation=90, ha="left", va="bottom", color=color)
            y += w[k](seg) / denom
    p0.remove()
    p1.remove()


def _draw_title(fig, y: float, no: int, title: str, cjk_fp, latin_fp,
                color: str = "#1a1a1a") -> None:
    p0, w0 = _mk_probe(fig, cjk_fp)
    p1, w1 = _mk_probe(fig, latin_fp)
    w = {0: w0, 1: w1}
    em = cjk_fp.get_size_in_points()
    pieces: list[tuple[str | None, float]] = [("图", w0("图")), (None, 0.14 * em),
                                              (str(no), w1(str(no))), (None, 0.72 * em)]
    for k, seg in _seg(title):
        pieces.append((seg, w[k](seg)))
    total = sum(v for _, v in pieces)
    fw = fig.get_figwidth() * 72
    x = 0.5 - total / (2 * fw)
    for seg, adv in pieces:
        if seg is not None:
            fp = cjk_fp if (seg == "图" or not seg.isascii()) else latin_fp
            fig.text(x, y, str(seg), fontproperties=fp, ha="left", va="bottom", color=color)
        x += adv / fw
    p0.remove()
    p1.remove()


def add_caption(fig, no: int, title: str, notes: list[str],
                lb: float, rb: float, pad: float = 0.20, gap: float = 0.10) -> None:
    """在图下写图题与图注，并按注行数反推所需下边距（自动 subplots_adjust）。"""
    body = "；".join(n.strip().rstrip("。") for n in notes) + "。"
    cjk_n = font_manager.FontProperties(family="SimSun", size=NOTE_PT)
    lat_n = font_manager.FontProperties(family="Times New Roman", size=NOTE_PT)
    cjk_t = font_manager.FontProperties(family="SimHei", size=TITLE_PT)
    lat_t = font_manager.FontProperties(family="Times New Roman", size=TITLE_PT)

    avail_pt = fig.get_figwidth() * (rb - lb) * 72 * 0.99
    lines = _wrap(fig, "　　" + body, avail_pt, cjk_n, lat_n)
    fig_h = fig.get_figheight()
    h_notes = len(lines) * NOTE_PT * LINE_SPACING / 72
    need = pad + h_notes + gap + TITLE_PT / 72 + 0.05
    sp = fig.subplotpars
    fig.subplots_adjust(bottom=max(need / fig_h, sp.bottom), left=sp.left,
                        right=sp.right, top=sp.top, wspace=sp.wspace, hspace=sp.hspace)
    for i, ln in enumerate(lines):
        y_pt = (pad * 72) + (len(lines) - 1 - i) * NOTE_PT * LINE_SPACING
        _draw(fig, lb, y_pt / (fig_h * 72), ln, cjk_n, lat_n, "#262626")
    _draw_title(fig, (pad + h_notes + gap) / fig_h, no, title, cjk_t, lat_t)




