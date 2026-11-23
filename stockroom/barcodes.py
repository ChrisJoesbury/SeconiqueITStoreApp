from io import BytesIO

from barcode import Code128
from barcode.writer import SVGWriter


def barcode_svg(value):
    """Return an inline SVG for a Code 128 barcode, without an XML declaration."""
    buffer = BytesIO()
    code = Code128(str(value), writer=SVGWriter())
    code.write(
        buffer,
        options={
            "module_width": 0.25,
            "module_height": 8,
            "quiet_zone": 1.5,
            "write_text": False,
            "font_size": 0,
        },
    )
    svg = buffer.getvalue().decode("utf-8")
    if "?>" in svg:
        svg = svg.split("?>", 1)[1]
    return svg.strip()
