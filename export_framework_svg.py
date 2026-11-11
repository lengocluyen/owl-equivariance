"""Export the editable Figure 1 SVG as a vector PDF for standard LaTeX.

Requirements: svglib, reportlab, and matplotlib (for its DejaVu math font).
No shell escape or LaTeX SVG package is needed. Geometry remains vector and
the Arial and DejaVu fonts are embedded.
The SVG itself is the editable source of truth.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

from matplotlib import font_manager
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from svglib.svglib import register_font, svg2rlg


def register_arial(font_dir: Path) -> None:
    fonts = {
        "Arial": "arial.ttf",
        "Arial-Bold": "arialbd.ttf",
        "Arial-Italic": "ariali.ttf",
        "Arial-BoldItalic": "arialbi.ttf",
    }
    missing = [filename for filename in fonts.values() if not (font_dir / filename).is_file()]
    if missing:
        raise SystemExit(
            f"Arial font files missing from {font_dir}: {missing}. "
            "Pass --font-dir with the directory containing these fonts."
        )
    for name, filename in fonts.items():
        pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    pdfmetrics.registerFontFamily(
        "Arial", normal="Arial", bold="Arial-Bold",
        italic="Arial-Italic", boldItalic="Arial-BoldItalic",
    )
    # svglib has its own mapping in addition to ReportLab's font registry.
    register_font("Arial", str(font_dir / "arial.ttf"), rlgFontName="Arial")
    register_font("Arial", str(font_dir / "arialbd.ttf"), weight="bold", rlgFontName="Arial-Bold")
    register_font("Arial", str(font_dir / "ariali.ttf"), style="italic", rlgFontName="Arial-Italic")
    register_font("Arial", str(font_dir / "arialbi.ttf"), weight="bold", style="italic", rlgFontName="Arial-BoldItalic")
    math_path = font_manager.findfont("DejaVu Sans", fallback_to_default=False)
    pdfmetrics.registerFont(TTFont("FigureMath", math_path))
    register_font("DejaVu Sans", math_path, rlgFontName="FigureMath")


def check_text(svg_path: Path) -> None:
    """Reject missing glyphs and text extending beyond declared layout regions.

    Optional data-text-region attributes constrain labels within a local
    region. All other text is checked against the SVG viewBox.
    """
    root = ET.parse(svg_path).getroot()
    errors: list[str] = []
    view_box = tuple(float(value) for value in root.attrib["viewBox"].split())
    default_bounds = (view_box[0], view_box[1], view_box[0] + view_box[2], view_box[1] + view_box[3])
    if root.findall(".//{http://www.w3.org/2000/svg}image"):
        raise ValueError("Raster images are not allowed in this vector figure.")

    def visit(node: ET.Element, inherited: dict[str, str]) -> None:
        style = inherited | node.attrib
        if node.tag.endswith("}text"):
            text = "".join(node.itertext())
            family = style.get("font-family", "Arial").split(",")[0]
            name = "FigureMath" if family == "DejaVu Sans" else "Arial"
            if name == "Arial" and style.get("font-weight") == "bold":
                name = "Arial-Bold"
            font = pdfmetrics.getFont(name)
            missing = [char for char in text if ord(char) not in font.face.charToGlyph]
            if missing:
                raise ValueError(f"Unmapped glyphs in {text!r}: {missing}")
            size = float(style.get("font-size", "26"))
            width = pdfmetrics.stringWidth(text, name, size)
            x, y = float(style["x"]), float(style["y"])
            if style.get("text-anchor") == "middle":
                x -= width / 2
            elif style.get("text-anchor") == "end":
                x -= width
            bounds = default_bounds
            if "data-text-region" in style:
                bounds = tuple(float(value) for value in style["data-text-region"].split(","))
            left, top, right, bottom = bounds
            if size < 26:
                errors.append(f"{text!r}: font size {size} is below the 26 px design minimum")
            ascent = font.face.ascent / 1000 * size
            descent = font.face.descent / 1000 * size
            if x < left or x + width > right or y - ascent < top or y - descent > bottom:
                errors.append(f"{text!r}: text bounds ({x:.1f}, {y - ascent:.1f}, {x + width:.1f}, {y - descent:.1f}) exceed {bounds}")
        for child in node:
            visit(child, style)

    visit(root, {})
    if errors:
        raise ValueError("Text exceeds layout bounds:\n" + "\n".join(errors))
    print("PASS: editable vector source, glyph coverage, and text bounds")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, default=Path("C:/Windows/Fonts"))
    parser.add_argument(
        "--svg", type=Path,
        default=Path(__file__).parent / "figures/semantic_consistency_framework_visual.svg",
    )
    parser.add_argument("--output", type=Path, help="Default: the input SVG with a .pdf suffix.")
    args = parser.parse_args()
    register_arial(args.font_dir)
    check_text(args.svg)
    drawing = svg2rlg(str(args.svg))
    if drawing is None:
        raise SystemExit(f"SVG parsing failed: {args.svg}")
    output = args.output or args.svg.with_suffix(".pdf")
    renderPDF.drawToFile(
        drawing, str(output),
        title="Semantic-consistency evaluation framework for OWL reasoning",
    )
    print(f"Vector PDF: {output}")
    print(f"Editable source: {args.svg}")


if __name__ == "__main__":
    main()
