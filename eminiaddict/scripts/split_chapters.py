"""Split the extracted book text into per-chapter files for rule extraction.

Reads data/book_text.txt (gitignored), splits by the '===== PAGE N =====' markers
using a chapter -> PDF-page-start map (book page + 20 offset), writes
data/chapters/chNN.txt (gitignored, copyrighted). Run from eminiaddict/.
"""
import re, os

txt = open("data/book_text.txt", encoding="utf-8").read()
parts = re.split(r'===== PAGE (\d+) =====', txt)
pages = {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}

chaps = [
    (1, 21, "Todays Trading Environment"),
    (2, 29, "Inside the Hidden Market (Fibs & the Measured Move)"),
    (3, 47, "Drawing a Road Map (pivots, gaps, trends)"),
    (4, 59, "More Tools for Trading Power (time, tape, DOM)"),
    (5, 73, "The 90 Percent Factor - Executing Your Trade"),
    (6, 89, "Three Types of Trade Setups"),
    (7, 103, "Using Multiple Time Frames to Trade"),
    (8, 113, "Three Entry Strategies for Retracements"),
    (9, 123, "Seasonality and Best Times to Trade"),
    (10, 133, "Tools for the NYSE"),
    (11, 143, "Tick Extremes and Divergences"),
    (12, 155, "Profiting from Gap Fills"),
    (13, 167, "How to Manage Positions and Take Profits"),
    (14, 177, "Risk Management (Advanced Trade Management)"),
    (15, 185, "The Inner Trader"),
    (16, 199, "The Trading Plan"),
]
starts = [c[1] for c in chaps] + [213]
os.makedirs("data/chapters", exist_ok=True)
for idx, (num, start, title) in enumerate(chaps):
    end = starts[idx + 1] - 1
    body = [f"[PDF p{p}]\n" + pages[p] for p in range(start, end + 1) if p in pages]
    out = f"data/chapters/ch{num:02d}.txt"
    open(out, "w", encoding="utf-8").write(
        f"CHAPTER {num}: {title}\nPDF pages {start}-{end}\n\n" + "\n".join(body))
    print(f"ch{num:02d} p{start}-{end}  {len(''.join(body)):>6} chars  {title}")
