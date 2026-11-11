"""Render presentation-only SVG/PDF figures without scientific recomputation.

The two schematic SVGs are editable source assets. The metric panels read the
existing six-row figure trace verbatim: no predictions are loaded or aggregated,
no estimates are fitted, and no uncertainty or new scientific result is computed.
Only geometric placement and display rounding are performed.

Requirements: Python, reportlab, and Arial/Segoe UI Symbol TrueType fonts.
The deliberately small SVG vocabulary makes the vector export auditable.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

ROOT = Path(__file__).resolve().parent
NS = "http://www.w3.org/2000/svg"
EXPECTED_MODELS = ["Gemma", "Llama", "Mistral", "GPT-OSS-120B", "Qwen", "GPT-OSS-20B"]
METRICS = ["answer_accuracy", "robust_orbit_accuracy", "proof_valid_orbit_accuracy"]


def register_fonts(font_dir: Path) -> None:
    for name, filename in [("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"),
                           ("FigureSymbol", "seguisym.ttf")]:
        pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))


def font_name(style: dict[str, str]) -> str:
    if style.get("font-family", "Arial") == "Segoe UI Symbol":
        return "FigureSymbol"
    return "Arial-Bold" if style.get("font-weight") == "bold" else "Arial"


def export_svg(source: Path) -> None:
    """Export simple absolute-coordinate SVG shapes, rejecting unsupported input."""
    root = ET.parse(source).getroot()
    vx, vy, width, height = map(float, root.attrib["viewBox"].split())
    if vx != 0 or vy != 0:
        raise ValueError("Only zero-origin viewBoxes are supported")
    output = source.with_suffix(".pdf")
    pdf = canvas.Canvas(str(output), pagesize=(width * 0.75, height * 0.75),
                        initialFontName="Arial", initialFontSize=28)
    pdf.scale(0.75, 0.75)
    pdf.setTitle(root.findtext(f"{{{NS}}}title") or source.stem)
    pdf.setAuthor("Le Ngoc Luyen")
    text_count = 0
    allowed = {"svg", "g", "rect", "line", "polyline", "polygon", "circle", "ellipse", "text", "title", "desc"}

    def paint(node: ET.Element, inherited: dict[str, str]) -> None:
        nonlocal text_count
        tag = node.tag.rsplit("}", 1)[-1]
        if tag not in allowed:
            raise ValueError(f"Unsupported SVG element: {tag}")
        style = inherited | node.attrib
        if "transform" in node.attrib or "style" in node.attrib:
            raise ValueError("Use absolute coordinates and presentation attributes")
        if tag in {"title", "desc"}:
            return
        if tag in {"svg", "g"}:
            for child in node:
                paint(child, style)
            return
        pdf.saveState()
        fill = style.get("fill", "#000000")
        stroke = style.get("stroke", "none")
        has_fill, has_stroke = fill != "none", stroke != "none"
        if has_fill:
            pdf.setFillColor(HexColor(fill))
        if has_stroke:
            pdf.setStrokeColor(HexColor(stroke))
        pdf.setLineWidth(float(style.get("stroke-width", "1")))
        pdf.setLineCap({"butt": 0, "round": 1, "square": 2}.get(style.get("stroke-linecap", "butt"), 0))
        dash = style.get("stroke-dasharray", "none")
        if dash != "none":
            pdf.setDash([float(n) for n in dash.replace(",", " ").split()])
        if tag == "text":
            if list(node):
                raise ValueError("Use separate text elements, not nested tspans")
            label = node.text or ""
            name = font_name(style)
            size = float(style.get("font-size", "28"))
            if size < 26:
                raise ValueError(f"Text below 26-unit design minimum: {label}")
            font = pdfmetrics.getFont(name)
            missing = [c for c in label if ord(c) not in font.face.charToGlyph]
            if missing:
                raise ValueError(f"Missing glyphs {missing} in {label}")
            x, y = float(style["x"]), float(style["y"])
            text_width = pdfmetrics.stringWidth(label, name, size)
            if style.get("text-anchor") == "middle":
                x -= text_width / 2
            elif style.get("text-anchor") == "end":
                x -= text_width
            bounds = [0, 0, width, height]
            if "data-text-region" in style:
                bounds = list(map(float, style["data-text-region"].split(",")))
            left, top, right, bottom = bounds
            if (x < left - 0.01 or x + text_width > right + 0.01
                or y - font.face.ascent * size / 1000 < top - 0.01
                or y - font.face.descent * size / 1000 > bottom + 0.01):
                raise ValueError(f"Text outside layout region: {label!r} ({x:.1f}, {y:.1f}, w={text_width:.1f}) versus {bounds}")
            pdf.setFont(name, size)
            pdf.drawString(x, height - y, label)
            text_count += 1
        elif tag == "rect":
            x, y = float(style["x"]), float(style["y"])
            w, h = float(style["width"]), float(style["height"])
            radius = float(style.get("rx", "0"))
            if radius:
                pdf.roundRect(x, height - y - h, w, h, radius, stroke=int(has_stroke), fill=int(has_fill))
            else:
                pdf.rect(x, height - y - h, w, h, stroke=int(has_stroke), fill=int(has_fill))
        elif tag == "line":
            if has_stroke:
                pdf.line(float(style["x1"]), height - float(style["y1"]),
                         float(style["x2"]), height - float(style["y2"]))
        elif tag in {"circle", "ellipse"}:
            cx, cy = float(style["cx"]), float(style["cy"])
            rx = float(style.get("r", style.get("rx", "0")))
            ry = float(style.get("r", style.get("ry", "0")))
            pdf.ellipse(cx-rx, height-cy-ry, cx+rx, height-cy+ry,
                        stroke=int(has_stroke), fill=int(has_fill))
        else:
            numbers = list(map(float, style["points"].replace(",", " ").split()))
            if len(numbers) < 4 or len(numbers) % 2:
                raise ValueError("Malformed polygon/polyline")
            path = pdf.beginPath()
            path.moveTo(numbers[0], height-numbers[1])
            for index in range(2, len(numbers), 2):
                path.lineTo(numbers[index], height-numbers[index+1])
            if tag == "polygon":
                path.close()
            pdf.drawPath(path, stroke=int(has_stroke), fill=int(has_fill))
        pdf.restoreState()

    paint(root, {})
    pdf.showPage()
    pdf.save()
    print(f"PASS: {source.name}: {text_count} bounded text labels; vector PDF exported")


def metric_panels() -> Path:
    data = ROOT / "figures/figure_data/evaluation_ladder.csv"
    digest_before = hashlib.sha256(data.read_bytes()).hexdigest()
    with data.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if [row["model"] for row in rows] != EXPECTED_MODELS:
        raise ValueError("Unexpected figure-trace rows/order")
    for row in rows:
        for metric in METRICS:
            if not Decimal(0) <= Decimal(row[metric]) <= Decimal(1):
                raise ValueError("Expected an existing proportion in [0,1]")
    svg = [f'<svg xmlns="{NS}" viewBox="0 0 1500 790" width="1500" height="790">',
           '<title>Answer and evidence measures on distinct populations</title>',
           '<desc>Existing descriptive proportions copied from evaluation_ladder.csv; no new estimates.</desc>',
           '<rect x="0" y="0" width="1500" height="790" fill="#ffffff"/>',
           '<g font-family="Arial" font-size="28" fill="#172b42">']

    def text(x, y, label, **attrs):
        attrs_text = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        svg.append(f'<text x="{x}" y="{y}" {attrs_text}>{escape(label)}</text>')

    panel_starts = [240, 660, 1080]
    panel_titles = ["(a) Answer accuracy", "(b) All-condition", "(c) Correct + supported"]
    panel_subtitles = ["Individual variants", "answer correctness", "under every condition"]
    denominators = ["16,060 variants/model", "1,460 families/model", "730 entailed families/model"]
    colors = ["#2875a5", "#197b76", "#7160a7"]
    for col, (left, metric) in enumerate(zip(panel_starts, METRICS)):
        text(left, 45, panel_titles[col], font_weight="bold", font_size="30")
        text(left, 87, panel_subtitles[col])
        text(left, 137, denominators[col], font_size="26", fill="#4d5d70")
        svg.append(f'<line x1="{left}" y1="160" x2="{left+375}" y2="160" stroke="#c9d3dd" stroke-width="2"/>')
        for tick in [0, 0.25, 0.5, 0.75, 1]:
            x = left + 280*tick
            svg.append(f'<line x1="{x}" y1="205" x2="{x}" y2="645" stroke="#e4e9ef" stroke-width="1.5"/>')
            text(x, 684, f"{tick:.2f}", text_anchor="middle", font_size="26", fill="#4d5d70")
        if col == 1:
            svg.append(f'<line x1="{left+140}" y1="195" x2="{left+140}" y2="645" stroke="#45566b" stroke-width="2.5" stroke-dasharray="8 6"/>')
        for i, row in enumerate(rows):
            y = 236 + i*70
            value = Decimal(row[metric])
            bar_width = value * Decimal(280)
            svg.append(f'<rect x="{left}" y="{y-19}" width="{bar_width}" height="34" fill="{colors[col]}" data-model="{escape(row["model"])}" data-metric="{metric}" data-value="{row[metric]}"/>')
            text(float(Decimal(left)+bar_width)+10, y+8, f"{value:.3f}", font_size="27")
        text(left+140, 727, "Proportion", text_anchor="middle", font_size="26")
    for i, model in enumerate(EXPECTED_MODELS):
        text(210, 244+i*70, model, text_anchor="end", font_size="27")
    svg.append('<line x1="270" y1="768" x2="325" y2="768" stroke="#45566b" stroke-width="2.5" stroke-dasharray="8 6"/>')
    text(340, 777, "0.500 constant-label reference in (b)", font_size="26")
    text(1465, 777, "Descriptive values; no uncertainty intervals", text_anchor="end", font_size="26", fill="#4d5d70")
    svg.append('</g></svg>')
    output = ROOT / "figures/evaluation_panels.svg"
    output.write_text("\n".join(svg)+"\n", encoding="utf-8")
    if hashlib.sha256(data.read_bytes()).hexdigest() != digest_before:
        raise AssertionError("Source trace changed")
    print(f"Read-only source trace SHA256: {digest_before}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, default=Path("C:/Windows/Fonts"))
    parser.add_argument("--metric-panels", action="store_true", help="Redraw only the existing metric trace")
    parser.add_argument("--svg", type=Path, action="append", default=[])
    args = parser.parse_args()
    register_fonts(args.font_dir)
    sources = args.svg
    if args.metric_panels:
        sources.append(metric_panels())
    if not sources:
        parser.error("Specify --metric-panels or --svg")
    for source in sources:
        export_svg(source)


if __name__ == "__main__":
    main()
