"""render_indicator_doc_pdf.py -- generic NT8 indicator doc (.md) -> shareable PDF.

Same markdown -> PDF engine as render_note_pdf.py (reused via import), but with a
neutral header/footer instead of the MC Setup Research Notes framing -- for
documenting NinjaScript indicators to share with collaborators (e.g. Thomas).

Run: python scripts/render_indicator_doc_pdf.py docs/nt8_indicators/HighVolumePivot.md
Out: same path with .pdf, AND a copy in EXPORT_DIR (off-repo shareable folder).
"""
from __future__ import annotations
import sys, shutil
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_note_pdf import parse, inline  # reuse the markdown block parser

_ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = Path("C:/Users/Admin/Documents/NT8_Indicator_Docs")
_FONTS = Path("C:/Windows/Fonts")
BLUE = (31, 95, 168)
GREY = (90, 90, 90)
DARK = (20, 20, 20)


class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "", 8); self.set_text_color(*GREY)
        self.cell(0, 5, "NT8 INDICATOR DOCUMENTATION", 0, 0, "L")
        self.cell(0, 5, f"Generated {datetime.now():%Y-%m-%d}", 0, 1, "R")
        self.set_draw_color(*BLUE); self.set_line_width(0.4)
        self.line(10, 16, 200, 16); self.ln(5)

    def footer(self):
        self.set_y(-12); self.set_font("Arial", "I", 7); self.set_text_color(*GREY)
        self.cell(0, 5, f"myquant / nt8 indicators   Page {self.page_no()}", 0, 0, "C")


def render(md_path: Path, out_path: Path):
    blocks = parse(md_path.read_text(encoding="utf-8"))
    pdf = PDF()
    pdf.add_font("Arial", "", str(_FONTS / "arial.ttf"))
    pdf.add_font("Arial", "B", str(_FONTS / "arialbd.ttf"))
    pdf.add_font("Arial", "I", str(_FONTS / "ariali.ttf"))
    pdf.set_auto_page_break(True, 14)
    pdf.add_page()

    for kind, payload in blocks:
        pdf.set_x(pdf.l_margin)
        if kind == "h":
            lvl, txt = payload
            if lvl == 1:
                pdf.set_font("Arial", "B", 16); pdf.set_text_color(*BLUE)
                pdf.multi_cell(0, 8, inline(txt)); pdf.ln(1)
            elif lvl == 2:
                pdf.ln(2); pdf.set_font("Arial", "B", 12); pdf.set_text_color(*BLUE)
                pdf.multi_cell(0, 6.5, inline(txt)); pdf.set_text_color(*DARK)
            else:
                pdf.ln(1); pdf.set_font("Arial", "B", 10.5); pdf.set_text_color(*BLUE)
                pdf.multi_cell(0, 5.5, inline(txt)); pdf.set_text_color(*DARK)
        elif kind == "p":
            low = payload.lower()
            if low.startswith("for:") or low.startswith("date:") or low.startswith("platform:") \
                    or low.startswith("file in repo:") or low.startswith("source:"):
                pdf.set_font("Arial", "", 9); pdf.set_text_color(*GREY)
                pdf.multi_cell(0, 4.6, inline(payload), markdown=True); pdf.set_text_color(*DARK)
            else:
                pdf.set_font("Arial", "", 10); pdf.set_text_color(*DARK)
                pdf.multi_cell(0, 5, inline(payload), markdown=True); pdf.ln(1)
        elif kind == "ul":
            pdf.set_font("Arial", "", 10)
            for it in payload:
                pdf.set_x(pdf.l_margin + 2)
                pdf.multi_cell(0, 5, "-  " + inline(it), markdown=True)
            pdf.ln(1)
        elif kind == "quote":
            pdf.ln(0.5); pdf.set_fill_color(245, 245, 228); pdf.set_font("Arial", "", 10)
            pdf.set_text_color(*DARK)
            pdf.multi_cell(0, 5, inline(payload), fill=True, markdown=True); pdf.ln(0.5)
        elif kind == "table":
            rows = payload
            ncols = max(len(r) for r in rows)
            rows = [r + [""] * (ncols - len(r)) for r in rows]
            aligns = tuple(["LEFT"] * ncols)
            colw = [min(55, max(12, max(len(inline(r[c])) for r in rows))) for c in range(ncols)]
            total = sum(colw)
            colw = [w * 190 / total for w in colw]
            pdf.set_font("Arial", "", 8.3); pdf.set_text_color(*DARK)
            from fpdf.fonts import FontFace
            from fpdf.enums import TableCellFillMode
            head_style = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=BLUE)
            with pdf.table(width=190, col_widths=tuple(colw), text_align=aligns, markdown=True,
                           headings_style=head_style, cell_fill_color=(238, 242, 248),
                           cell_fill_mode=TableCellFillMode.ROWS, line_height=4.6,
                           first_row_as_headings=True, borders_layout="MINIMAL") as table:
                for r in rows:
                    trow = table.row()
                    for c in r:
                        trow.cell(inline(c))
            pdf.ln(2)
        elif kind == "code":
            pdf.ln(0.5); pdf.set_font("Courier", "", 8.5)
            pdf.set_fill_color(244, 244, 240); pdf.set_text_color(*DARK)
            for cl in payload.split("\n"):
                cl = cl.encode("latin-1", "replace").decode("latin-1")
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 4.2, cl if cl.strip() else " ", fill=True)
            pdf.set_font("Arial", "", 10); pdf.ln(1.5)
        elif kind == "hr":
            pdf.ln(1)

    pdf.output(str(out_path))
    print(f"PDF: {out_path}")


def _export(pdf_path: Path):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_path, EXPORT_DIR / pdf_path.name)
    print(f"  -> exported to {EXPORT_DIR / pdf_path.name}")


def main():
    if len(sys.argv) < 2:
        print("usage: render_indicator_doc_pdf.py <doc.md>"); return 1
    md = Path(sys.argv[1])
    if not md.is_absolute():
        md = _ROOT / md
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else md.with_suffix(".pdf")
    render(md, out); _export(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
