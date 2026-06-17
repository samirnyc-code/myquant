"""
Fix double-encoded (mojibake) characters in bar_analysis.py.

Root cause: PowerShell in Session 12 read the UTF-8 file as cp1252,
then wrote it back as UTF-8, double-encoding every non-ASCII character.

Strategy: scan text for contiguous non-ASCII runs, try to decode each
run back via cp1252-bytes -> UTF-8. Replace runs that round-trip cleanly.
Correctly-encoded chars added since then (±, …) are single-codepoint and
won't match any multi-char mojibake run, so they're safe.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ── cp1252 byte mapper (handles the 5 undefined positions too) ────────────────

_CP1252_UNDEFINED = {0x81, 0x8D, 0x8F, 0x90, 0x9D}

def char_to_cp1252_byte(ch: str) -> int | None:
    """Map a Unicode char back to its cp1252 byte value.
    Returns None if the char cannot be represented in cp1252."""
    cp = ord(ch)
    if cp <= 0x7F:
        return cp                          # ASCII: identity
    if cp in _CP1252_UNDEFINED:
        return cp                          # Python maps undefined positions to U+00XX
    try:
        b = ch.encode("cp1252")
        return b[0] if len(b) == 1 else None
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None


def try_decode_run(chars: str) -> str | None:
    """Try to reverse-decode a run of non-ASCII chars as a mojibake sequence.
    Returns the original Unicode string if it round-trips, else None."""
    raw = bytearray()
    for ch in chars:
        b = char_to_cp1252_byte(ch)
        if b is None:
            return None
        raw.append(b)
    try:
        decoded = raw.decode("utf-8")
        # Only accept if the result is shorter (proving it was a multi-byte sequence)
        # and doesn't contain replacement chars
        if len(decoded) < len(chars) and "�" not in decoded:
            return decoded
    except UnicodeDecodeError:
        pass
    return None


# ── Process file ──────────────────────────────────────────────────────────────

with open("bar_analysis.py", "r", encoding="utf-8-sig") as f:
    text = f.read()

result = []
i = 0
replacements = 0

while i < len(text):
    ch = text[i]
    if ord(ch) <= 0x7F:
        result.append(ch)
        i += 1
        continue

    # Collect a contiguous run of non-ASCII chars (up to 12 chars — longest
    # emoji sequence after double-encoding is ~4 UTF-8 bytes × 3 chars each = 12)
    j = i
    while j < len(text) and ord(text[j]) > 0x7F:
        j += 1
    run = text[i:j]

    # Try to decode the full run, then progressively shorter prefixes
    decoded = None
    end = j
    for length in range(len(run), 0, -1):
        attempt = try_decode_run(run[:length])
        if attempt is not None:
            decoded = attempt
            end = i + length
            break

    if decoded is not None:
        result.append(decoded)
        replacements += 1
        i = end
    else:
        # Can't decode — keep as-is (e.g. the correctly-added ± U+00B1)
        result.append(ch)
        i += 1

fixed = "".join(result)

with open("bar_analysis.py", "w", encoding="utf-8") as f:
    f.write(fixed)

print(f"Done. {replacements} mojibake runs replaced.")
