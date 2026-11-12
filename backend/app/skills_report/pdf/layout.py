"""
A small box layout + pagination engine that mirrors what @react-pdf/layout (v3.13, yoga based) does for the skills
report document tree.

Only the subset of flexbox used by the report is supported: column/row flex direction, padding, margin, border widths,
gap, fixed width/height, `flex: 1` in rows, `alignItems` (stretch/flex-start/center), absolute positioning (top/bottom,
width 100%), images sized by aspect ratio and text measured with the textkit port.

The pagination (`paginate`) is a port of react-pdf's `splitNodes`/`splitView`/`splitText`/`shouldBreak` and honours
the `wrap`, `break`, `minPresenceAhead` and `fixed` props as well as text orphans/widows.
"""
import copy
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.skills_report.pdf.text_kit import Fragment, Line, layout_text, lines_height, lines_width

SAFETY_THRESHOLD = 0.001
_IMAGE_SAFETY_HEIGHT = 10


@dataclass
class ImageData:
    data: bytes
    width: int
    height: int

    @property
    def ratio(self) -> float:
        return self.width / self.height


@dataclass
class Box:
    top: float = 0
    left: float = 0
    width: float = 0
    height: float = 0
    padding_top: float = 0
    padding_right: float = 0
    padding_bottom: float = 0
    padding_left: float = 0
    margin_top: float = 0
    margin_right: float = 0
    margin_bottom: float = 0
    margin_left: float = 0
    border_top_width: float = 0
    border_right_width: float = 0
    border_bottom_width: float = 0
    border_left_width: float = 0


# Fragments of a dynamic text node (e.g. page numbers), resolved per page
DynamicTextRender = Callable[[int, Optional[int]], list[Fragment]]


@dataclass
class Node:
    type: str  # page | view | text | image
    style: dict = field(default_factory=dict)
    props: dict = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)
    fragments: Optional[list[Fragment]] = None
    render: Optional[DynamicTextRender] = None
    image: Optional[ImageData] = None
    lines: Optional[list[Line]] = None
    box: Box = field(default_factory=Box)

    def clone(self, style: Optional[dict] = None, props: Optional[dict] = None,
              children: Optional[list["Node"]] = None, **changes) -> "Node":
        node = copy.copy(self)
        node.style = dict(self.style if style is None else style)
        node.props = dict(self.props if props is None else props)
        node.children = list(self.children if children is None else children)
        node.box = copy.copy(self.box)
        for key, value in changes.items():
            setattr(node, key, value)
        return node


# Element factories named after the react-pdf primitives, to keep the document tree close to the JSX source
# pylint: disable=invalid-name

def View(style: Optional[dict] = None, children: Optional[list[Optional[Node]]] = None, **props) -> Node:
    return Node("view", style=dict(style or {}), props=props, children=[c for c in (children or []) if c is not None])


def Text(style: Optional[dict] = None, fragments: Optional[list[Fragment]] = None,
         render: Optional[DynamicTextRender] = None, **props) -> Node:
    return Node("text", style=dict(style or {}), props=props, fragments=list(fragments or []), render=render)


def Image(image: ImageData, style: Optional[dict] = None, **props) -> Node:
    return Node("image", style=dict(style or {}), props=props, image=image)

# pylint: enable=invalid-name


# ----------------------------------------------------------------------------------------------------------------------
# Layout
# ----------------------------------------------------------------------------------------------------------------------

def _s(node: Node, name: str, default: float = 0) -> float:
    value = node.style.get(name)
    return default if value is None else value


def _apply_box_model(node: Node):
    b = node.box
    b.padding_top, b.padding_right = _s(node, "paddingTop"), _s(node, "paddingRight")
    b.padding_bottom, b.padding_left = _s(node, "paddingBottom"), _s(node, "paddingLeft")
    b.margin_top, b.margin_right = _s(node, "marginTop"), _s(node, "marginRight")
    b.margin_bottom, b.margin_left = _s(node, "marginBottom"), _s(node, "marginLeft")
    b.border_top_width, b.border_right_width = _s(node, "borderTopWidth"), _s(node, "borderRightWidth")
    b.border_bottom_width, b.border_left_width = _s(node, "borderBottomWidth"), _s(node, "borderLeftWidth")


def _horizontal_insets(node: Node) -> float:
    b = node.box
    return b.padding_left + b.padding_right + b.border_left_width + b.border_right_width


def _vertical_insets(node: Node) -> float:
    b = node.box
    return b.padding_top + b.padding_bottom + b.border_top_width + b.border_bottom_width


def _is_absolute(node: Node) -> bool:
    return node.style.get("position") == "absolute"


class LayoutContext:
    def __init__(self, page_height: float, page_padding_top: float, page_padding_bottom: float):
        self.page_height = page_height
        self.page_padding_top = page_padding_top
        self.page_padding_bottom = page_padding_bottom


def _ensure_text_lines(node: Node, content_width: float):
    if node.lines is None:
        node.lines = layout_text(node.fragments or [], content_width)


def _measure_intrinsic_width(node: Node, available_width: float, ctx: LayoutContext) -> float:
    """Width of a node whose width is not stretched (yoga measure with MeasureMode.AtMost)."""
    if "width" in node.style:
        return node.style["width"]
    _apply_box_model(node)
    if node.type == "text":
        _ensure_text_lines(node, available_width - _horizontal_insets(node))
        return min(available_width, lines_width(node.lines) + _horizontal_insets(node))
    if node.type == "image":
        return _image_size(node, None, available_width, ctx)[0]
    if node.style.get("flexDirection") == "row":
        children = [c for c in node.children if not _is_absolute(c)]
        gap = _s(node, "gap")
        inner = available_width - _horizontal_insets(node)
        total = 0.0
        for i, child in enumerate(children):
            _apply_box_model(child)
            total += child.box.margin_left + child.box.margin_right + \
                _measure_intrinsic_width(child, inner - child.box.margin_left - child.box.margin_right, ctx)
            if i < len(children) - 1:
                total += gap
        return min(available_width, total + _horizontal_insets(node))
    widths = []
    inner = available_width - _horizontal_insets(node)
    for child in node.children:
        if _is_absolute(child):
            continue
        _apply_box_model(child)
        widths.append(child.box.margin_left + child.box.margin_right +
                      _measure_intrinsic_width(child, inner - child.box.margin_left - child.box.margin_right, ctx))
    return min(available_width, max(widths, default=0) + _horizontal_insets(node))


def _image_size(node: Node, exact_width: Optional[float], available_width: float,
                ctx: LayoutContext) -> tuple[float, float]:
    """Port of react-pdf's measureImage for the measure modes the report uses. Returns the border-box size."""
    b = node.box
    pad_h = b.padding_left + b.padding_right
    pad_v = b.padding_top + b.padding_bottom
    ratio = node.image.ratio if node.image else 1
    page_area = ctx.page_height - ctx.page_padding_top - ctx.page_padding_bottom - b.margin_top - b.margin_bottom - \
        _IMAGE_SAFETY_HEIGHT
    width = node.style.get("width")
    height = node.style.get("height")
    if width is not None and height is not None:
        return width, height
    if height is not None:
        # height: Exactly, width: AtMost
        content_height = height - pad_v
        content_width = min(content_height * ratio, available_width - pad_h)
        return content_width + pad_h, height
    if width is not None or exact_width is not None:
        w = width if width is not None else exact_width
        content_width = w - pad_h
        max_height = node.style.get("maxHeight")
        if max_height is not None:
            # width: Exactly, height: AtMost
            content_height = min(max_height - pad_v, page_area, content_width / ratio)
        else:
            content_height = min(page_area, content_width / ratio)
        return w, content_height + pad_v
    # width AtMost, height undefined -> treat as width exact on the available width
    content_width = available_width - pad_h
    return available_width, min(page_area, content_width / ratio) + pad_v


def _shrink(sizes: list[float], minimums: list[float], overflow: float) -> list[float]:
    """
    Yoga flex shrink: react-pdf sets `flexShrink` to 1 on every node (`setFlexShrink(value || 1)`), so overflowing
    children shrink proportionally to their flex basis (their natural size), but not below their padding + border.
    """
    total = sum(sizes)
    if overflow <= 0 or total <= 0:
        return sizes
    return [max(size - overflow * size / total, minimum) for size, minimum in zip(sizes, minimums)]


def layout_node(node: Node, width: float, ctx: LayoutContext, forced_height: Optional[float] = None):
    """
    Lay out `node` with the given border-box width; sets node.box.width/height and the children's top/left.
    `forced_height` is the height imposed by the parent (cross axis stretch or flex shrink).
    """
    _apply_box_model(node)
    node.box.width = width
    definite_height = forced_height if forced_height is not None else node.style.get("height")
    if node.type == "page":
        # The page is laid out with an auto height before pagination (react-pdf omits the page box height), and the
        # split parts always fit the page afterwards: the page never shrinks its content.
        definite_height = None
    if node.type == "text":
        _ensure_text_lines(node, width - _horizontal_insets(node))
        node.box.height = definite_height if definite_height is not None else \
            lines_height(node.lines) + _vertical_insets(node)
        return
    if node.type == "image":
        w, h = _image_size(node, width, width, ctx)
        node.box.width = w if "width" in node.style or "height" in node.style else width
        node.box.height = h
        return

    inner_width = width - _horizontal_insets(node)
    flow_children = [c for c in node.children if not _is_absolute(c)]
    gap = _s(node, "gap")
    gaps = gap * max(0, len(flow_children) - 1)
    align_items = node.style.get("alignItems", "stretch")
    top0 = node.box.padding_top + node.box.border_top_width
    left0 = node.box.padding_left + node.box.border_left_width

    if node.style.get("flexDirection") == "row":
        # main axis: fixed / intrinsic widths first, then flex children share the remaining space, or shrink
        widths: list[Optional[float]] = []
        used = 0.0
        for child in flow_children:
            _apply_box_model(child)
            margins = child.box.margin_left + child.box.margin_right
            if child.style.get("flex"):
                widths.append(None)
            elif "width" in child.style:
                widths.append(child.style["width"])
            elif child.type == "image" and "height" in child.style:
                widths.append(_image_size(child, None, inner_width - margins, ctx)[0])
            else:
                widths.append(_measure_intrinsic_width(child, inner_width - margins, ctx))
            used += margins + (widths[-1] or 0)
        used += gaps
        flex_total = sum(c.style.get("flex") or 0 for c in flow_children)
        remaining = max(0.0, inner_width - used)
        for i, child in enumerate(flow_children):
            if widths[i] is None:
                widths[i] = remaining * (child.style.get("flex") or 0) / flex_total if flex_total else 0
        if used > inner_width:
            widths = _shrink(widths, [_horizontal_insets(c) for c in flow_children], used - inner_width)
        for child, w in zip(flow_children, widths):
            layout_node(child, w, ctx)
        if definite_height is not None:
            node.box.height = definite_height
            content_height = node.box.height - _vertical_insets(node)
        else:
            content_height = max((c.box.margin_top + c.box.height + c.box.margin_bottom for c in flow_children),
                                 default=0)
            node.box.height = content_height + _vertical_insets(node)
        x = left0
        for i, (child, w) in enumerate(zip(flow_children, widths)):
            if align_items == "stretch" and "height" not in child.style and child.type != "image":
                layout_node(child, w, ctx,
                            forced_height=content_height - child.box.margin_top - child.box.margin_bottom)
            child_outer = child.box.margin_top + child.box.height + child.box.margin_bottom
            offset = (content_height - child_outer) / 2 if align_items == "center" else 0
            child.box.top = top0 + offset + child.box.margin_top
            child.box.left = x + child.box.margin_left
            x += child.box.margin_left + w + child.box.margin_right
            if i < len(flow_children) - 1:
                x += gap
    else:
        child_widths = []
        for child in flow_children:
            _apply_box_model(child)
            margins = child.box.margin_left + child.box.margin_right
            if "width" in child.style:
                child_width = child.style["width"]
                if isinstance(child_width, str) and child_width.endswith("%"):
                    child_width = inner_width * float(child_width[:-1]) / 100
            elif align_items == "stretch":
                child_width = inner_width - margins
            else:
                child_width = _measure_intrinsic_width(child, inner_width - margins, ctx)
            layout_node(child, child_width, ctx)
            child_widths.append(child_width)
        if definite_height is not None:
            inner_height = definite_height - _vertical_insets(node)
            used = sum(c.box.margin_top + c.box.height + c.box.margin_bottom for c in flow_children) + gaps
            if used > inner_height:
                heights = _shrink([c.box.height for c in flow_children],
                                  [_vertical_insets(c) for c in flow_children], used - inner_height)
                for child, child_width, h in zip(flow_children, child_widths, heights):
                    if child.type != "image":
                        layout_node(child, child_width, ctx, forced_height=h)
        y = top0
        for i, child in enumerate(flow_children):
            margins = child.box.margin_left + child.box.margin_right
            child.box.top = y + child.box.margin_top
            offset = (inner_width - margins - child.box.width) / 2 if align_items == "center" else 0
            child.box.left = left0 + child.box.margin_left + offset
            y += child.box.margin_top + child.box.height + child.box.margin_bottom
            if i < len(flow_children) - 1:
                y += gap
        node.box.height = definite_height if definite_height is not None else y - top0 + _vertical_insets(node)

    for child in node.children:
        if not _is_absolute(child):
            continue
        _apply_box_model(child)
        child_width = child.style.get("width", width)
        if isinstance(child_width, str) and child_width.endswith("%"):
            child_width = width * float(child_width[:-1]) / 100
        layout_node(child, child_width, ctx)
        if "top" in child.style:
            child.box.top = child.style["top"] + child.box.margin_top
        elif "bottom" in child.style:
            child.box.top = node.box.height - child.style["bottom"] - child.box.height - child.box.margin_bottom
        child.box.left = child.style.get("left", 0) + child.box.margin_left


def _resolve_dynamic(node: Node, page_number: int, total_pages: Optional[int]) -> Node:
    if node.render is not None:
        return node.clone(fragments=node.render(page_number, total_pages), lines=None)
    if not node.children:
        return node
    return node.clone(children=[_resolve_dynamic(c, page_number, total_pages) for c in node.children])


def layout_page(page: Node, ctx: LayoutContext) -> Node:
    layout_node(page, page.style["width"], ctx)
    page.box.height = page.style["height"]
    # absolutely positioned children with `bottom` depend on the final page height
    for child in page.children:
        if _is_absolute(child) and "bottom" in child.style:
            child.box.top = page.box.height - child.style["bottom"] - child.box.height - child.box.margin_bottom
    return page


# ----------------------------------------------------------------------------------------------------------------------
# Pagination (port of @react-pdf/layout splitNodes & co.)
# ----------------------------------------------------------------------------------------------------------------------

def _is_fixed(node: Node) -> bool:
    return node.props.get("fixed") is True


def _get_wrap(node: Node) -> bool:
    if node.type == "image":
        return False
    wrap = node.props.get("wrap")
    return True if wrap is None else wrap


def _get_break(node: Node) -> bool:
    return node.props.get("break") or False


def _get_min_presence_ahead(node: Node) -> float:
    return node.props.get("minPresenceAhead") or 0


def _should_break(child: Node, future_elements: list[Node], height: float) -> bool:
    if _is_fixed(child):
        return False
    should_split = height < child.box.top + child.box.height
    can_wrap = _get_wrap(child)
    after_min_presence_ahead = child.box.top + child.box.height + child.box.margin_bottom + \
        _get_min_presence_ahead(child)
    non_fixed = [n for n in future_elements if not n.props.get("fixed")]
    furthest_end = max((n.box.top + n.box.height for n in non_fixed), default=float("-inf"))
    end_of_presence = min(after_min_presence_ahead, furthest_end)
    breaking_improves_presence = child.box.top > child.box.margin_top
    return _get_break(child) or (should_split and not can_wrap) or \
        (not should_split and end_of_presence > height and breaking_improves_presence)


def _line_index_at_height(node: Node, height: float) -> int:
    y = 0.0
    if not node.lines:
        return 0
    for i, line in enumerate(node.lines):
        if y + line.box.height > height:
            return i
        y += line.box.height
    return len(node.lines)


def _height_at_line_index(node: Node, index: int) -> float:
    counter = 0.0
    if not node.lines:
        return counter
    for i in range(index):
        if i >= len(node.lines):
            break
        counter += node.lines[i].box.height
    return counter


def _get_line_break(node: Node, height: float) -> int:
    top = node.box.top or 0
    widows = node.props.get("widows", 2)
    orphans = node.props.get("orphans", 2)
    lines_quantity = len(node.lines)
    sliced_line = _line_index_at_height(node, height - top)
    if sliced_line == 0:
        return 0
    if lines_quantity < orphans:
        return lines_quantity
    if sliced_line < orphans or lines_quantity < orphans + widows:
        return 0
    if lines_quantity == orphans + widows:
        return orphans
    if lines_quantity - sliced_line < widows:
        return lines_quantity - widows
    return sliced_line


def _split_text(node: Node, height: float) -> tuple[Optional[Node], Optional[Node]]:
    sliced_line_index = _get_line_break(node, height)
    current_style = {**node.style, "marginBottom": 0, "paddingBottom": 0, "borderBottomWidth": 0}
    next_style = {**node.style, "marginTop": 0, "paddingTop": 0, "borderTopWidth": 0}
    current = node.clone(style=current_style, lines=node.lines[:sliced_line_index])
    nxt = node.clone(style=next_style, lines=node.lines[sliced_line_index:])
    nxt.box.top = 0
    return current, nxt


def _split_view_node(node: Node, height: float) -> tuple[Node, Node]:
    node_top = node.box.top or 0
    current_style = {**node.style, "marginBottom": 0, "paddingBottom": 0, "borderBottomWidth": 0,
                     "height": height - node_top}
    current = node.clone(style=current_style)
    next_style = {**node.style, "marginTop": 0, "paddingTop": 0, "borderTopWidth": 0}
    if "height" in node.style:
        next_style["height"] = node.box.height - (height - node_top)
    nxt = node.clone(style=next_style)
    nxt.box.top = 0
    return current, nxt


def _split_view(node: Node, height: float, content_area: float) -> tuple[Node, Node]:
    current_node, next_node = _split_view_node(node, height)
    available_height = height - (node.box.top or 0)
    current_children, next_children = split_nodes(available_height, content_area, node.children)
    current_node.children = current_children
    next_node.children = next_children
    return current_node, next_node


def _split(node: Node, height: float, content_area: float):
    if node.type == "text":
        return _split_text(node, height)
    return _split_view(node, height, content_area)


def split_nodes(height: float, content_area: float, nodes: list[Node]) -> tuple[list[Node], list[Node]]:
    current_children: list[Node] = []
    next_children: list[Node] = []
    for i, child in enumerate(nodes):
        future_nodes = nodes[i + 1:]
        future_fixed_nodes = [n for n in future_nodes if _is_fixed(n)]
        node_top = child.box.top or 0
        node_height = child.box.height
        is_outside = height <= node_top
        should_break = _should_break(child, future_nodes, height)
        should_split = height + SAFETY_THRESHOLD < node_top + node_height
        can_wrap = _get_wrap(child)
        fits_inside_page = node_height <= content_area

        if _is_fixed(child):
            next_children.append(child)
            current_children.append(child)
            continue
        if is_outside:
            nxt = child.clone()
            nxt.box.top = child.box.top - height
            next_children.append(nxt)
            continue
        if not fits_inside_page and not can_wrap:
            current_children.append(child)
            next_children.extend(future_nodes)
            break
        if should_break:
            nxt = child.clone(props={**child.props, "wrap": True, "break": False})
            nxt.box.top = child.box.top - height
            current_children.extend(future_fixed_nodes)
            next_children.extend([nxt, *future_nodes])
            break
        if should_split:
            current_child, next_child = _split(child, height, content_area)
            if child.children and current_child is not None and not current_child.children and \
                    child.type != "text":
                if not current_children:
                    current_children.extend([child, *future_fixed_nodes])
                    next_children.extend(future_nodes)
                else:
                    nxt = child.clone()
                    nxt.box.top = child.box.top - height
                    current_children.extend(future_fixed_nodes)
                    next_children.extend([nxt, *future_nodes])
                break
            if current_child is not None:
                current_children.append(current_child)
            if next_child is not None:
                next_children.append(next_child)
            continue
        current_children.append(child)
    return current_children, next_children


def paginate(page: Node, ctx: LayoutContext) -> list[Node]:
    """Split the (laid out) page into as many pages as needed and resolve the dynamic (page number) nodes."""
    pages: list[Node] = []
    wrap_area = page.style["height"] - _s(page, "paddingBottom")
    content_area = page.style["height"] - _s(page, "paddingBottom") - _s(page, "paddingTop")
    current = page
    page_number = 1
    while current is not None:
        dynamic_page = layout_page(_resolve_dynamic(current, page_number, None), ctx)
        current_children, next_children = split_nodes(wrap_area, content_area, dynamic_page.children)
        pages.append(layout_page(current.clone(children=current_children), ctx))
        if not next_children or all(_is_fixed(n) for n in next_children):
            current = None
        else:
            current = layout_page(current.clone(children=next_children), ctx)
            page_number += 1
    total = len(pages)
    return [layout_page(_resolve_dynamic(p, i + 1, total), ctx) for i, p in enumerate(pages)]
