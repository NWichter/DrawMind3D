"""Minimal PDF writer for test fixtures.

Writing the few bytes of PDF a test needs is cheaper than depending on a PDF
authoring library, and it lets the fixtures exercise the same ToUnicode
mapping that real CAD exports use for symbols such as the diameter sign.
"""

from __future__ import annotations

from pathlib import Path

# Codes outside WinAnsi are assigned from here upwards and resolved through
# the ToUnicode map, which is how CAD exporters encode engineering symbols.
_CUSTOM_CODE_START = 0x01


def _encode(text: str, codes: dict[str, int]) -> bytes:
    out = bytearray()
    for char in text:
        if char in codes:
            out.append(codes[char])
            continue
        try:
            out.extend(char.encode("cp1252"))
            codes[char] = char.encode("cp1252")[0]
        except UnicodeEncodeError:
            code = _CUSTOM_CODE_START + sum(1 for c in codes if ord(c) > 0xFF)
            codes[char] = code
            out.append(code)
    return bytes(out)


def _escape(data: bytes) -> bytes:
    for old, new in ((b"\\", b"\\\\"), (b"(", b"\\("), (b")", b"\\)")):
        data = data.replace(old, new)
    return data


def _tounicode_cmap(codes: dict[str, int]) -> str:
    entries = "".join(f"<{code:02X}> <{ord(char):04X}>\n" for char, code in codes.items())
    return (
        "/CIDInit /ProcSet findresource begin\n"
        "12 dict begin\nbegincmap\n"
        "/CMapName /DrawMind-Test def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
        f"{len(codes)} beginbfchar\n{entries}endbfchar\n"
        "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend"
    )


def build_text_pdf(
    path: str | Path,
    items: list[tuple[tuple[float, float], str, float]],
    width: float = 595,
    height: float = 842,
    strokes: list[tuple[tuple[float, float], tuple[float, float]]] | None = None,
    stroke_width: float = 0.5,
    rotate: int = 0,
    cropbox: tuple[float, float, float, float] | None = None,
) -> Path:
    """Write a single-page PDF containing the given text and line art.

    Args:
        path: Destination file
        items: ((x, y), text, font_size) with y measured from the top edge
        width: Page width in points
        height: Page height in points
        strokes: ((x0, y0), (x1, y1)) segments, y measured from the top edge
        stroke_width: Line width used for the segments
        rotate: Page rotation in degrees
        cropbox: Optional (left, bottom, right, top) crop box in PDF units

    Returns:
        The path written
    """
    codes: dict[str, int] = {}
    parts = []
    for (x, y), text, size in items:
        encoded = _escape(_encode(text, codes))
        parts.append(b"BT /F1 %.2f Tf %.2f %.2f Td (%s) Tj ET" % (size, x, height - y, encoded))

    for (x0, y0), (x1, y1) in strokes or []:
        parts.append(
            b"%.2f w %.2f %.2f m %.2f %.2f l S" % (stroke_width, x0, height - y0, x1, height - y1)
        )

    content = b"\n".join(parts)
    crop = b"/CropBox [%.2f %.2f %.2f %.2f] " % cropbox if cropbox else b""

    differences = " ".join(
        f"{code} /uni{ord(char):04X}" for char, code in codes.items() if ord(char) > 0xFF
    )
    cmap = _tounicode_cmap(codes).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Rotate %d "
        b"%s/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        % (width, height, rotate, crop),
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding 7 0 R /ToUnicode 6 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(cmap), cmap),
        b"<< /Type /Encoding /BaseEncoding /WinAnsiEncoding /Differences [%s] >>"
        % differences.encode("ascii"),
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)

    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )

    path = Path(path)
    path.write_bytes(bytes(out))
    return path
