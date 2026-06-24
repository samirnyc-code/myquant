"""render_note_pdf.py — generic MC Setup Research Note (.md) -> Keystone-style PDF.

Parses one of the docs/research_notes/*.md notes (headings, tables, blockquotes,
bullet lists, **bold**, the Series/Confidence/TL;DR header) and typesets it in the
house style: blue section headers, banded tables, confidence banner, page header/
footer. Unicode-safe (Arial TTF). One tool for every note in the series.

Run one:  python scripts/render_note_pdf.py docs/research_notes/0001_pb_scalein_mc.md
Run all:  python scripts/render_note_pdf.py --all
Out:  same path with .pdf, AND a copy in EXPORT_DIR (the off-repo shareable folder).
"""
from __future__ import annotations
import sys, re, shutil
from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace
from fpdf.enums import TableCellFillMode

_ROOT = Path(__file__).resolve().parents[1]
_NOTES_DIR = _ROOT / "docs" / "research_notes"
# Off-repo, friend-shareable copy. Every render is mirrored here.
EXPORT_DIR = Path("C:/Users/Admin/Documents/MC_Setup_Research_Notes")
_FONTS = Path("C:/Windows/Fonts")
BLUE = (31, 95, 168)
GREY = (90, 90, 90)
DARK = (20, 20, 20)
CONF = {  # confidence-level banner colours: (fill, text)
    "high":   ((224, 240, 224), (25, 105, 40)),
    "medium": ((250, 240, 205), (120, 80, 0)),
    "low":    ((245, 224, 224), (150, 40, 40)),
}


_GLYPH = {"≫": ">>", "≪": "<<", "✅": " [+]", "❌": " [-]",
          "⭐": "*", "⚠": "!", "️": "",
          "🟢": "[G]", "🟡": "[Y]", "🔴": "[R]"}


def inline(t: str) -> str:
    """Strip code backticks and single-asterisk italics; keep **bold** for markdown.
    Replace glyphs Arial can't render with ASCII."""
    t = t.replace("`", "")
    for k, v in _GLYPH.items():
        t = t.replace(k, v)
    t = t.replace("**", "\x00").replace("*", "").replace("\x00", "**")
    return t.strip()


def parse(md: str):
    """Markdown -> list of (kind, payload) blocks."""
    lines = md.split("\n")
    blocks, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        if ln.lstrip().startswith("```"):                    # fenced code block
            i += 1
            code = []
            while i < n and not lines[i].lstrip().startswith("```"):
                code.append(lines[i]); i += 1
            i += 1                                            # skip closing fence
            blocks.append(("code", "\n".join(code)))
            continue
        if ln.lstrip().startswith("|"):                      # table
            tbl = []
            while i < n and lines[i].lstrip().startswith("|"):
                tbl.append(lines[i]); i += 1
            rows = []
            for r in tbl:
                cells = [c.strip() for c in r.strip().strip("|").split("|")]
                rows.append(cells)
            rows = [r for r in rows if not all(set(c) <= set("-: ") for c in r)]
            if rows:
                blocks.append(("table", rows))
        elif ln.startswith("#"):                             # heading
            lvl = len(ln) - len(ln.lstrip("#"))
            blocks.append(("h", (lvl, ln.lstrip("#").strip())))
            i += 1
        elif ln.lstrip().startswith(">"):                    # blockquote
            q = []
            while i < n and lines[i].lstrip().startswith(">"):
                q.append(lines[i].lstrip()[1:].strip()); i += 1
            blocks.append(("quote", "\n".join(q).strip()))
        elif re.match(r"\s*[-*] ", ln):                      # bullet list
            items = []
            while i < n and re.match(r"\s*[-*] ", lines[i]):
                items.append(re.sub(r"\s*[-*] ", "", lines[i], count=1).strip()); i += 1
            blocks.append(("ul", items))
        elif ln.strip() == "---":
            blocks.append(("hr", None)); i += 1
        else:                                                # paragraph
            para = []
            while i < n and lines[i].strip() and not lines[i].lstrip().startswith(("|", "#", ">", "---", "```")) \
                    and not re.match(r"\s*[-*] ", lines[i]):
                para.append(lines[i].strip()); i += 1
            blocks.append(("p", " ".join(para)))
    return blocks


class PDF(FPDF):
    note_tag = "MC SETUP RESEARCH NOTES"

    def header(self):
        self.set_font("Arial", "", 8); self.set_text_color(*GREY)
        self.cell(0, 5, self.note_tag, 0, 0, "L")
        self.cell(0, 5, f"Generated {datetime.now():%Y-%m-%d}", 0, 1, "R")
        self.set_draw_color(*BLUE); self.set_line_width(0.4)
        self.line(10, 16, 200, 16); self.ln(5)

    def footer(self):
        self.set_y(-12); self.set_font("Arial", "I", 7); self.set_text_color(*GREY)
        self.cell(0, 5, f"MC Setup Research Notes - in-sample, not investment advice.   Page {self.page_no()}",
                  0, 0, "C")


def render(md_path: Path, out_path: Path):
    blocks = parse(md_path.read_text(encoding="utf-8"))
    pdf = PDF()
    pdf.add_font("Arial", "", str(_FONTS / "arial.ttf"))
    pdf.add_font("Arial", "B", str(_FONTS / "arialbd.ttf"))
    pdf.add_font("Arial", "I", str(_FONTS / "ariali.ttf"))
    pdf.set_auto_page_break(True, 14)
    pdf.add_page()

    for kind, payload in blocks:
        pdf.set_x(pdf.l_margin)                              # full width for every block
        if kind == "h":
            lvl, txt = payload
            if lvl == 1:                                     # title
                pdf.set_font("Arial", "B", 15); pdf.set_text_color(*BLUE)
                pdf.multi_cell(0, 7, inline(txt)); pdf.ln(1)
            elif lvl == 2:
                pdf.ln(1.5); pdf.set_font("Arial", "B", 11.5); pdf.set_text_color(*BLUE)
                pdf.multi_cell(0, 6, inline(txt)); pdf.set_text_color(*DARK)
            else:
                pdf.ln(0.8); pdf.set_font("Arial", "B", 10); pdf.set_text_color(*BLUE)
                pdf.multi_cell(0, 5.2, inline(txt)); pdf.set_text_color(*DARK)
        elif kind == "p":
            low = payload.lower()
            if low.startswith("**series:"):
                pdf.set_font("Arial", "", 8.5); pdf.set_text_color(*GREY)
                pdf.multi_cell(0, 4.4, inline(payload)); pdf.set_text_color(*DARK)
            elif low.startswith("**confidence:"):
                body = inline(payload).split(":", 1)[1].strip()
                lvl = next((k for k in CONF if body.lower().lstrip().startswith(k)), "medium")
                fill, tcol = CONF[lvl]
                pdf.ln(0.5); pdf.set_fill_color(*fill); pdf.set_text_color(*tcol)
                pdf.set_font("Arial", "B", 9)
                pdf.multi_cell(0, 4.6, "CONFIDENCE: " + body, fill=True, markdown=True)
                pdf.set_text_color(*DARK); pdf.ln(0.5)
            elif low.startswith("**tl;dr:"):
                pdf.ln(0.5); pdf.set_fill_color(238, 242, 248)
                pdf.set_font("Arial", "", 9.5)
                pdf.multi_cell(0, 4.7, inline(payload), fill=True, markdown=True); pdf.ln(0.5)
            else:
                pdf.set_font("Arial", "", 9.5); pdf.set_text_color(*DARK)
                pdf.multi_cell(0, 4.7, inline(payload), markdown=True); pdf.ln(0.5)
        elif kind == "ul":
            pdf.set_font("Arial", "", 9.5)
            for it in payload:
                pdf.set_x(pdf.l_margin + 2)
                pdf.multi_cell(0, 4.6, "-  " + inline(it), markdown=True)
            pdf.ln(0.5)
        elif kind == "quote":
            pdf.ln(0.5); pdf.set_fill_color(245, 245, 228); pdf.set_font("Arial", "", 9.5)
            pdf.set_text_color(*DARK)
            pdf.multi_cell(0, 4.7, inline(payload), fill=True, markdown=True); pdf.ln(0.5)
        elif kind == "table":
            rows = payload
            ncols = max(len(r) for r in rows)
            rows = [r + [""] * (ncols - len(r)) for r in rows]
            aligns = tuple(["LEFT"] + ["CENTER"] * (ncols - 1))
            # weight each column by its longest cell so wide text columns get the
            # room and numeric columns stay tight (avoids "no space" overflow).
            # Cap each column's weight so one very long cell can't starve the
            # others below a renderable width (fpdf raises if a col < ~1 char).
            colw = [min(32, max(3, max(len(inline(r[c])) for r in rows))) for c in range(ncols)]
            pdf.set_font("Arial", "", 7.4); pdf.set_text_color(*DARK)
            head_style = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=BLUE)
            with pdf.table(width=190, col_widths=tuple(colw), text_align=aligns, markdown=True,
                           headings_style=head_style, cell_fill_color=(238, 242, 248),
                           cell_fill_mode=TableCellFillMode.ROWS, line_height=4.2,
                           first_row_as_headings=True, borders_layout="MINIMAL") as table:
                for r in rows:
                    trow = table.row()
                    for c in r:
                        trow.cell(inline(c))
            pdf.ln(1)
        elif kind == "code":                                 # monospace, literal
            pdf.ln(0.5); pdf.set_font("Courier", "", 7.5)
            pdf.set_fill_color(244, 244, 240); pdf.set_text_color(*DARK)
            cmap = {"🟢": "[G]", "🟡": "[Y]", "🔴": "[R]"}
            for cl in payload.split("\n"):
                for k, v in cmap.items():
                    cl = cl.replace(k, v)
                # Courier is a latin-1 core font: drop anything it can't encode
                cl = cl.encode("latin-1", "replace").decode("latin-1")
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 3.7, cl if cl.strip() else " ", fill=True)
            pdf.set_font("Arial", "", 9.5); pdf.ln(1)
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
        print("usage: render_note_pdf.py <note.md> | --all"); return 1

    if sys.argv[1] == "--all":
        notes = sorted(p for p in _NOTES_DIR.glob("[0-9]*.md"))
        for md in notes:
            out = md.with_suffix(".pdf")
            render(md, out); _export(out)
        readme = _NOTES_DIR / "README.md"
        if readme.exists():                              # keep the index alongside
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(readme, EXPORT_DIR / "README.md")
            print(f"  -> exported index to {EXPORT_DIR / 'README.md'}")
        print(f"\nRendered {len(notes)} notes to {_NOTES_DIR} and {EXPORT_DIR}")
        return 0

    md = Path(sys.argv[1])
    if not md.is_absolute():
        md = _ROOT / md
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else md.with_suffix(".pdf")
    render(md, out); _export(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
