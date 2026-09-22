"""Render specific PDF pages of the Halsey book to PNG for diagram review.

Usage: python scripts/render_pages.py 140 141 74 76 ...
Outputs figures/page_XXX.png at 200 DPI.
"""
import sys, fitz  # PyMuPDF

PDF = "data/halsey_measured_move.pdf"
OUT = "figures"
DPI = 200


def main(pages):
    doc = fitz.open(PDF)
    zoom = DPI / 72.0
    mat = fitz.Matrix(zoom, zoom)
    for p in pages:
        idx = p - 1
        if idx < 0 or idx >= len(doc):
            print(f"skip {p}: out of range (1..{len(doc)})")
            continue
        pix = doc[idx].get_pixmap(matrix=mat)
        path = f"{OUT}/page_{p:03d}.png"
        pix.save(path)
        print(f"wrote {path} ({pix.width}x{pix.height})")


if __name__ == "__main__":
    pages = [int(x) for x in sys.argv[1:]] or [140]
    main(pages)
