"""
Render the laid out (and paginated) skills report pages to PDF with reportlab.

Glyphs are drawn one by one at the positions computed by the textkit port (kerning, justification), like react-pdf
does, instead of letting reportlab lay out the strings.
"""
import io
from functools import lru_cache

from reportlab.lib.colors import HexColor, black
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from app.skills_report.pdf.layout import Node
from app.skills_report.pdf.text_kit import FontFace


@lru_cache(maxsize=None)
def _register_font(path: str, name: str) -> str:
    pdfmetrics.registerFont(TTFont(name, path))
    return name


def _color(value: str):
    if not value or value == "black":
        return black
    return HexColor(value)


class _PageRenderer:
    def __init__(self, canvas: Canvas, page_height: float):
        self.c = canvas
        self.page_height = page_height

    def _y(self, top: float) -> float:
        return self.page_height - top

    def render(self, node: Node, abs_left: float, abs_top: float):
        left = abs_left + node.box.left
        top = abs_top + node.box.top
        if node.type == "page":
            left, top = 0, 0
        if node.type in ("view", "page"):
            self._render_borders(node, left, top)
            for child in node.children:
                self.render(child, left, top)
        elif node.type == "text":
            self._render_text(node, left, top)
        elif node.type == "image":
            self._render_image(node, left, top)

    def _render_borders(self, node: Node, left: float, top: float):
        b = node.box
        color = _color(node.style.get("borderColor", "black"))
        rects = []
        if b.border_top_width:
            rects.append((left, top, b.width, b.border_top_width))
        if b.border_bottom_width:
            rects.append((left, top + b.height - b.border_bottom_width, b.width, b.border_bottom_width))
        if b.border_left_width:
            rects.append((left, top, b.border_left_width, b.height))
        if b.border_right_width:
            rects.append((left + b.width - b.border_right_width, top, b.border_right_width, b.height))
        if not rects:
            return
        self.c.saveState()
        self.c.setFillColor(color)
        for x, y, w, h in rects:
            self.c.rect(x, self._y(y + h), w, h, stroke=0, fill=1)
        self.c.restoreState()

    def _render_image(self, node: Node, left: float, top: float):
        if not node.image:
            return
        b = node.box
        x = left + b.padding_left
        y = top + b.padding_top
        w = b.width - b.padding_left - b.padding_right
        h = b.height - b.padding_top - b.padding_bottom
        if node.style.get("objectFit") == "contain":
            ratio = node.image.ratio
            if w / h > ratio:
                fitted_w, fitted_h = h * ratio, h
            else:
                fitted_w, fitted_h = w, w / ratio
            x += (w - fitted_w) / 2
            y += (h - fitted_h) / 2
            w, h = fitted_w, fitted_h
        self.c.drawImage(ImageReader(io.BytesIO(node.image.data)), x, self._y(y + h), w, h, mask="auto")

    def _render_text(self, node: Node, left: float, top: float):
        if not node.lines:
            return
        b = node.box
        initial_y = node.lines[0].box.y
        origin_x = left + b.padding_left
        origin_y = top + b.padding_top - initial_y
        for line in node.lines:
            x = origin_x + line.box.x
            baseline = origin_y + line.box.y + line.ascent
            for run in line.runs:
                font: FontFace = run.attributes.font
                font_name = _register_font(font.path, font.reportlab_name)
                text = self.c.beginText()
                text.setFont(font_name, run.attributes.font_size)
                text.setFillColor(_color(run.attributes.color))
                for glyph, position in zip(run.glyphs, run.positions):
                    if glyph.chars:
                        text.setTextOrigin(x + position.x_offset, self._y(baseline) + position.y_offset)
                        text.textOut(glyph.chars)
                    x += position.x_advance
                self.c.drawText(text)


def render_pdf(pages: list[Node], title: str, author: str) -> bytes:
    buffer = io.BytesIO()
    # invariant=1: deterministic output (no creation date / random document id), the same input gives the same bytes
    canvas = Canvas(buffer, invariant=1, pageCompression=1)
    canvas.setTitle(title)
    canvas.setAuthor(author)
    canvas.setCreator(author)
    for page in pages:
        width, height = page.style["width"], page.style["height"]
        canvas.setPageSize((width, height))
        _PageRenderer(canvas, height).render(page, 0, 0)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()
