"""
Python port of the parts of @react-pdf/textkit (v4.4.1) used by the skills report.

The frontend renders the report with @react-pdf/renderer. To produce the same line breaks (and therefore the same
pagination) the backend reproduces textkit's text pipeline:

  fragments -> split paragraphs -> runs (fragments + script boundaries) -> glyphs (OpenType shaping, HarfBuzz instead of
  fontkit) -> syllables (`hyphen` en-us patterns) -> Knuth & Plass nodes -> line breaking (with best-fit fallback)
  -> lines (+ inserted hyphens) -> remove new line / overflow / justification / finalize.

Function and variable names follow the JS source to make it easy to compare both implementations.
Only left/center/right alignment and the attributes used by the report are supported.
"""
# pylint: disable=no-member,too-many-locals,too-many-branches,too-many-statements
import math
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Optional

import uharfbuzz as hb  # pylint: disable=no-member
from fontTools.ttLib import TTFont
from fontTools import unicodedata as ft_unicodedata

from app.skills_report.pdf.hyphenation import word_syllables

# ----------------------------------------------------------------------------------------------------------------------
# Fonts & shaping
# ----------------------------------------------------------------------------------------------------------------------

# fontkit applies these features by default for horizontal latin text (DefaultShaper + GSUB/GPOS defaults)
_SHAPING_FEATURES = {"ccmp": True, "locl": True, "rlig": True, "mark": True, "mkmk": True, "calt": True, "clig": True,
                     "liga": True, "rclt": True, "curs": True, "kern": True}


class FontFace:
    """A TrueType font file, with the metrics textkit uses (fontkit reads them from the `hhea` table)."""

    def __init__(self, path: str, reportlab_name: str):
        self.path = path
        self.reportlab_name = reportlab_name
        tt = TTFont(path, lazy=True)
        self.units_per_em: int = tt["head"].unitsPerEm
        self.ascent: int = tt["hhea"].ascent
        self.descent: int = tt["hhea"].descent
        self.line_gap: int = tt["hhea"].lineGap
        self._cmap: dict[int, str] = tt.getBestCmap()
        glyph_order = tt.getGlyphOrder()
        self._glyph_id_by_name = {name: i for i, name in enumerate(glyph_order)}
        hmtx = tt["hmtx"]
        self._advance_by_name = {name: hmtx[name][0] for name in glyph_order}
        tt.close()
        blob = hb.Blob.from_file_path(path)
        self._hb_face = hb.Face(blob)
        self._hb_font = hb.Font(self._hb_face)

    def has_glyph_for_code_point(self, code_point: int) -> bool:
        return code_point in self._cmap

    def glyph_for_code_point(self, code_point: int) -> "Glyph":
        name = self._cmap.get(code_point, ".notdef")
        return Glyph(id=self._glyph_id_by_name.get(name, 0), code_points=(code_point,), chars=chr(code_point),
                     advance_width=self._advance_by_name.get(name, 0))

    def layout(self, text: str) -> tuple[list["Glyph"], list["Position"], list[int]]:
        """Shape `text` (LTR). Returns glyphs, positions (font units) and the char -> glyph index mapping."""
        if not text:
            return [], [], []
        buf = hb.Buffer()
        buf.add_codepoints([ord(c) for c in text])
        buf.direction = "ltr"
        buf.guess_segment_properties()
        hb.shape(self._hb_font, buf, _SHAPING_FEATURES)
        infos = buf.glyph_infos
        positions = buf.glyph_positions
        clusters = [info.cluster for info in infos]
        glyphs: list[Glyph] = []
        result_positions: list[Position] = []
        for i, info in enumerate(infos):
            cluster = info.cluster
            is_first_of_cluster = i == 0 or clusters[i - 1] != cluster
            if is_first_of_cluster:
                next_cluster = next((c for c in clusters[i + 1:] if c != cluster), len(text))
                chars = text[cluster:next_cluster]
            else:
                chars = ""
            glyphs.append(Glyph(id=info.codepoint, code_points=tuple(ord(c) for c in chars), chars=chars,
                                advance_width=positions[i].x_advance))
            result_positions.append(Position(x_advance=positions[i].x_advance, x_offset=positions[i].x_offset,
                                             y_offset=positions[i].y_offset))
        # char index -> glyph index (first glyph of the char's cluster)
        glyph_indices: list[int] = []
        first_glyph_of_cluster: dict[int, int] = {}
        for i, cluster in enumerate(clusters):
            first_glyph_of_cluster.setdefault(cluster, i)
        sorted_clusters = sorted(first_glyph_of_cluster)
        ci = 0
        for char_index in range(len(text)):
            while ci + 1 < len(sorted_clusters) and sorted_clusters[ci + 1] <= char_index:
                ci += 1
            glyph_indices.append(first_glyph_of_cluster[sorted_clusters[ci]])
        return glyphs, result_positions, glyph_indices


@dataclass(frozen=True)
class Glyph:
    id: int
    code_points: tuple[int, ...]
    # the characters this glyph renders (used to draw it with reportlab, which works with characters)
    chars: str
    # advance width in font units (used for inserted glyphs, e.g. hyphens)
    advance_width: int = 0


@dataclass
class Position:
    x_advance: float
    x_offset: float = 0
    y_offset: float = 0


# ----------------------------------------------------------------------------------------------------------------------
# Attributed strings
# ----------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Attributes:
    font: FontFace
    font_size: float
    color: str = "black"
    align: str = "left"
    line_height: Optional[float] = None  # absolute value (react-pdf multiplies the style lineHeight by fontSize)

    @property
    def scale(self) -> float:
        return self.font_size / self.font.units_per_em


@dataclass
class Run:
    start: int
    end: int
    attributes: Attributes
    glyphs: list[Glyph] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)  # in points
    glyph_indices: list[int] = field(default_factory=list)
    # set by finalizeLine
    height: float = 0
    ascent: float = 0
    descent: float = 0
    x_advance: float = 0


@dataclass
class AttributedString:
    string: str
    runs: list[Run]
    syllables: list[str] = field(default_factory=list)


@dataclass
class Box:
    x: float
    y: float
    width: float
    height: float


@dataclass
class Line:
    string: str
    runs: list[Run]
    box: Box
    overflow_left: float = 0
    overflow_right: float = 0
    height: float = 0
    ascent: float = 0
    descent: float = 0
    x_advance: float = 0


@dataclass(frozen=True)
class Fragment:
    string: str
    attributes: Attributes


def _run_ascent(run: Run) -> float:
    return run.attributes.font.ascent * run.attributes.scale


def _run_descent(run: Run) -> float:
    return run.attributes.scale * run.attributes.font.descent


def _run_line_gap(run: Run) -> float:
    return run.attributes.font.line_gap * run.attributes.scale


def _run_height(run: Run) -> float:
    return run.attributes.line_height or (_run_line_gap(run) + _run_ascent(run) - _run_descent(run))


def _string_height(runs: list[Run]) -> float:
    result = 0.0
    for run in runs:
        result = max(result, _run_height(run))
    return result


def _glyph_index_at(index: int, run: Run) -> int:
    if 0 <= index < len(run.glyph_indices):
        return run.glyph_indices[index]
    return index if index < len(run.glyphs) else len(run.glyphs)


def _run_advance_width(run: Run) -> float:
    return sum(p.x_advance for p in run.positions)


def _advance_width_between_run(start: int, end: int, run: Run) -> float:
    run_start = run.start or 0
    glyph_start = max(0, _glyph_index_at(start - run_start, run))
    glyph_end = max(0, _glyph_index_at(end - run_start, run))
    return sum(p.x_advance for p in run.positions[glyph_start:glyph_end])


def _run_index_at(n: int, runs: list[Run]) -> int:
    for i, run in enumerate(runs):
        if run.start <= n < run.end:
            return i
    return -1


def _js_slice(items: list, start: int, end: int) -> list:
    n = len(items)
    start = max(n + start, 0) if start < 0 else min(start, n)
    end = max(n + end, 0) if end < 0 else min(end, n)
    return items[start:end] if start < end else []


def _filter_runs(start: int, end: int, runs: list[Run]) -> list[Run]:
    """textkit `filter`"""
    start_index = _run_index_at(start, runs)
    end_index = max(_run_index_at(end - 1, runs), start_index)
    return _js_slice(runs, start_index, end_index + 1)


def _advance_width_between(start: int, end: int, string: AttributedString) -> float:
    return sum(_advance_width_between_run(start, end, run) for run in _filter_runs(start, end, string.runs))


def _slice_run(start: int, end: int, run: Run) -> Run:
    """textkit run `slice` (start/end relative to the run)."""
    start_glyph = _glyph_index_at(start, run)
    end_glyph = _glyph_index_at(end, run)
    glyph_indices = run.glyph_indices[start:end]
    if glyph_indices:
        first = glyph_indices[0]
        glyph_indices = [g - first for g in glyph_indices]
    return Run(start=run.start + start, end=run.start + min(end, run.end - run.start), attributes=run.attributes,
               glyphs=run.glyphs[start_glyph:end_glyph],
               positions=[replace(p) for p in run.positions[start_glyph:end_glyph]],
               glyph_indices=glyph_indices)


def _slice_string(start: int, end: int, string: AttributedString) -> AttributedString:
    runs = []
    for run in _filter_runs(start, end, string.runs):
        local_start = max(start - run.start, 0)
        local_end = min(end, run.end) - run.start
        sliced = _slice_run(local_start, local_end, run)
        sliced.start = max(run.start, start) - start
        sliced.end = min(run.end, end) - start
        runs.append(sliced)
    return AttributedString(string=string.string[start:end], runs=runs)


# ----------------------------------------------------------------------------------------------------------------------
# Paragraph preprocessing
# ----------------------------------------------------------------------------------------------------------------------

_IGNORED_SCRIPTS = {"Zyyy", "Zinh", "Zzzz"}  # Common, Inherited, Unknown
_IGNORABLE_CODEPOINTS = [8232, 8233]  # LINE_SEPARATOR, PARAGRAPH_SEPARATOR


def _ignore_chars(fragment: Fragment) -> Fragment:
    """react-pdf layout `ignoreChars` preprocessor: removes the FIRST occurrence (non global regex) of the chars."""
    subset = [chr(cp) for cp in _IGNORABLE_CODEPOINTS if not fragment.attributes.font.has_glyph_for_code_point(cp)]
    if not subset:
        return fragment
    match = re.search("|".join(re.escape(c) for c in subset), fragment.string)
    if not match:
        return fragment
    return Fragment(fragment.string[:match.start()] + fragment.string[match.end():], fragment.attributes)


def _script_boundaries(string: str) -> list[int]:
    """Start offsets of textkit's scriptItemizer runs."""
    boundaries = []
    last_script = None
    for i, char in enumerate(string):
        script = ft_unicodedata.script(char)
        if script != last_script and script not in _IGNORED_SCRIPTS:
            boundaries.append(i)
            last_script = script
    return boundaries


def _from_fragments(fragments: list[Fragment]) -> tuple[str, list[tuple[int, int, Attributes]]]:
    offset = 0
    string = ""
    runs = []
    for fragment in fragments:
        string += fragment.string
        runs.append((offset, offset + len(fragment.string), fragment.attributes))
        offset += len(fragment.string)
    return string, runs


def _split_paragraphs(string: str) -> list[tuple[int, int]]:
    res = []
    start = 0
    break_point = string.find("\n") + 1
    while break_point > 0:
        res.append((start, break_point))
        start = break_point
        break_point = string.find("\n", break_point) + 1
    if start == 0:
        res.append((0, len(string)))
    elif start < len(string):
        res.append((start, len(string)))
    return res


def _preprocess_paragraph(string: str, fragment_runs: list[tuple[int, int, Attributes]]) -> AttributedString:
    """preprocessRuns (flatten fragment, font and script runs) + generateGlyphs + wrapWords"""
    if not string:
        return AttributedString(string="", runs=[])
    boundaries = set()
    for start, end, _ in fragment_runs:
        boundaries.add(start)
        boundaries.add(end)
    boundaries.update(_script_boundaries(string))
    boundaries.add(0)
    boundaries.add(len(string))
    points = sorted(b for b in boundaries if 0 <= b <= len(string))

    runs: list[Run] = []
    for start, end in zip(points, points[1:]):
        if start >= end:
            continue
        attributes = next((a for (s, e, a) in fragment_runs if s <= start < e), None)
        if attributes is None:
            continue
        glyphs, positions, glyph_indices = attributes.font.layout(string[start:end])
        scale = attributes.scale
        runs.append(Run(start=start, end=end, attributes=attributes, glyphs=glyphs,
                        positions=[Position(p.x_advance * scale, p.x_offset * scale, p.y_offset * scale)
                                   for p in positions],
                        glyph_indices=glyph_indices))

    # wrapWords
    syllables: list[str] = []
    for run in runs:
        words = [w for w in re.split(r"([ ]+)", string[run.start:run.end]) if w]
        for word in words:
            syllables.extend(word_syllables(word))
    return AttributedString(string=string, runs=runs, syllables=syllables)


# ----------------------------------------------------------------------------------------------------------------------
# Knuth & Plass
# ----------------------------------------------------------------------------------------------------------------------

_KP_INFINITY = 10000
_BEST_FIT_INFINITY = 10000
_TOLERANCE_STEPS = 5
_TOLERANCE_LIMIT = 50
_OPTS_WIDTH, _OPTS_STRETCH, _OPTS_SHRINK = 3, 6, 9
_HYPHEN = 0x002D


@dataclass
class _Node:
    type: str  # box | glue | penalty
    width: float
    value: Optional[tuple[int, int]] = None  # (start, end)
    stretch: float = 0
    shrink: float = 0
    penalty: float = 0
    flagged: int = 0
    hyphenated: bool = False


def _get_nodes(string: AttributedString, align: str, hyphenation_penalty: Optional[float] = None) -> list[_Node]:
    start = 0
    hyphen_width = 5
    syllables = string.syllables
    hyphen_penalty = hyphenation_penalty or (100 if align == "justify" else 600)
    result: list[_Node] = []
    for index, s in enumerate(syllables):
        width = _advance_width_between(start, start + len(s), string)
        if _js_trim(s) == "":
            stretch = width * _OPTS_WIDTH / _OPTS_STRETCH
            shrink = width * _OPTS_WIDTH / _OPTS_SHRINK
            result.append(_Node("glue", width, (start, start + len(s)), stretch, shrink))
        else:
            next_syllable = syllables[index + 1] if index + 1 < len(syllables) else None
            hyphenated = next_syllable != " "
            result.append(_Node("box", width, (start, start + len(s)), hyphenated=hyphenated))
            if next_syllable and hyphenated:
                result.append(_Node("penalty", hyphen_width, penalty=hyphen_penalty, flagged=1))
        start += len(s)
    result.append(_Node("glue", 0, None, _KP_INFINITY, 0))
    result.append(_Node("penalty", 0, penalty=-_KP_INFINITY, flagged=1))
    return result


def _js_trim(s: str) -> str:
    return s.strip(" \t\n\r\u000b\u000c            "
                   "     　﻿")


class _ActiveNode:
    __slots__ = ("data", "prev", "next")

    def __init__(self, data: dict):
        self.data = data
        self.prev: Optional[_ActiveNode] = None
        self.next: Optional[_ActiveNode] = None


class _LinkedList:
    def __init__(self):
        self.head: Optional[_ActiveNode] = None
        self.tail: Optional[_ActiveNode] = None
        self.size = 0

    def push(self, node: _ActiveNode):
        if self.head is None:
            self.head = self.tail = node
            node.prev = node.next = None
        else:
            node.prev = self.tail
            node.next = None
            self.tail.next = node
            self.tail = node
        self.size += 1

    def insert_before(self, node: _ActiveNode, new_node: _ActiveNode):
        new_node.prev = node.prev
        new_node.next = node
        if node.prev is None:
            self.head = new_node
        else:
            node.prev.next = new_node
        node.prev = new_node
        self.size += 1

    def remove(self, node: _ActiveNode):
        if node.prev is None:
            self.head = node.next
        else:
            node.prev.next = node.next
        if node.next is None:
            self.tail = node.prev
        else:
            node.next.prev = node.prev
        self.size -= 1

    def __iter__(self):
        node = self.head
        while node is not None:
            yield node
            node = node.next


def _linebreak(nodes: list[_Node], lines: list[float], tolerance: float) -> list[dict]:
    """Knuth & Plass line breaking (Bram Stein's implementation, as bundled in textkit)."""
    demerits_line, demerits_flagged, demerits_fitness = 10, 100, 3000
    active_nodes = _LinkedList()
    total = {"width": 0.0, "stretch": 0.0, "shrink": 0.0}
    line_lengths = lines

    def new_breakpoint(position, demerits, ratio, line, fitness_class, totals, previous):
        return {"position": position, "demerits": demerits, "ratio": ratio, "line": line,
                "fitnessClass": fitness_class, "totals": totals or {"width": 0, "stretch": 0, "shrink": 0},
                "previous": previous}

    def compute_cost(end, active, current_line):
        width = total["width"] - active["totals"]["width"]
        line_length = line_lengths[current_line - 1] if current_line < len(line_lengths) else line_lengths[-1]
        if nodes[end].type == "penalty":
            width += nodes[end].width
        if width < line_length:
            stretch = total["stretch"] - active["totals"]["stretch"]
            if stretch > 0:
                return (line_length - width) / stretch
            return _KP_INFINITY
        if width > line_length:
            shrink = total["shrink"] - active["totals"]["shrink"]
            if shrink > 0:
                return (line_length - width) / shrink
            return _KP_INFINITY
        return 0

    def compute_sum(break_point_index):
        result = dict(total)
        for i in range(break_point_index, len(nodes)):
            n = nodes[i]
            if n.type == "glue":
                result["width"] += n.width
                result["stretch"] += n.stretch
                result["shrink"] += n.shrink
            elif n.type == "box" or (n.type == "penalty" and n.penalty == -_KP_INFINITY and i > break_point_index):
                break
        return result

    def main_loop(node: _Node, index: int):
        active = active_nodes.head
        while active is not None:
            candidates = [{"demerits": math.inf} for _ in range(4)]
            while active is not None:
                next_node = active.next
                current_line = active.data["line"] + 1
                ratio = compute_cost(index, active.data, current_line)
                if ratio < -1 or (node.type == "penalty" and node.penalty == -_KP_INFINITY):
                    active_nodes.remove(active)
                if -1 <= ratio <= tolerance:
                    badness = 100 * math.pow(abs(ratio), 3)
                    if node.type == "penalty" and node.penalty >= 0:
                        demerits = math.pow(demerits_line + badness, 2) + math.pow(node.penalty, 2)
                    elif node.type == "penalty" and node.penalty != -_KP_INFINITY:
                        demerits = math.pow(demerits_line + badness, 2) - math.pow(node.penalty, 2)
                    else:
                        demerits = math.pow(demerits_line + badness, 2)
                    if node.type == "penalty" and nodes[active.data["position"]].type == "penalty":
                        demerits += demerits_flagged * node.flagged * nodes[active.data["position"]].flagged
                    if ratio < -0.5:
                        current_class = 0
                    elif ratio <= 0.5:
                        current_class = 1
                    elif ratio <= 1:
                        current_class = 2
                    else:
                        current_class = 3
                    if abs(current_class - active.data["fitnessClass"]) > 1:
                        demerits += demerits_fitness
                    demerits += active.data["demerits"]
                    if demerits < candidates[current_class]["demerits"]:
                        candidates[current_class] = {"active": active, "demerits": demerits, "ratio": ratio}
                active = next_node
                if active is not None and active.data["line"] >= current_line:
                    break
            tmp_sum = compute_sum(index)
            for fitness_class, candidate in enumerate(candidates):
                if candidate["demerits"] < math.inf:
                    new_node = _ActiveNode(new_breakpoint(index, candidate["demerits"], candidate["ratio"],
                                                      candidate["active"].data["line"] + 1, fitness_class, tmp_sum,
                                                      candidate["active"]))
                    if active is not None:
                        active_nodes.insert_before(active, new_node)
                    else:
                        active_nodes.push(new_node)

    active_nodes.push(_ActiveNode(new_breakpoint(0, 0, 0, 0, 0, None, None)))
    for index, node in enumerate(nodes):
        if node.type == "box":
            total["width"] += node.width
        elif node.type == "glue":
            if index > 0 and nodes[index - 1].type == "box":
                main_loop(node, index)
            total["width"] += node.width
            total["stretch"] += node.stretch
            total["shrink"] += node.shrink
        elif node.type == "penalty" and node.penalty != _KP_INFINITY:
            main_loop(node, index)

    if active_nodes.size != 0:
        # Find the best active node (the one with the least total demerits)
        best_node: Optional[_ActiveNode] = None
        for n in active_nodes:
            if best_node is None or n.data["demerits"] < best_node.data["demerits"]:
                best_node = n
        breaks = []
        current: Optional[_ActiveNode] = best_node
        while current is not None:
            breaks.append({"position": current.data["position"], "ratio": current.data["ratio"]})
            current = current.data["previous"]
        breaks.reverse()
        return breaks
    return []


def _get_next_breakpoint(subnodes: list[_Node], widths: list[float], line_number: int) -> Optional[int]:
    position = None
    minimum_badness = math.inf
    s = {"width": 0.0, "stretch": 0.0, "shrink": 0.0}
    line_length = widths[min(line_number, len(widths) - 1)]

    def calculate_ratio(n: _Node):
        if s["width"] < line_length:
            return (line_length - s["width"]) / s["stretch"] if s["stretch"] - n.stretch > 0 else _BEST_FIT_INFINITY
        if s["width"] > line_length:
            return (line_length - s["width"]) / s["shrink"] if s["shrink"] - n.shrink > 0 else _BEST_FIT_INFINITY
        return 0

    for i, node in enumerate(subnodes):
        if node.type == "box":
            s["width"] += node.width
        elif node.type == "glue":
            s["width"] += node.width
            s["stretch"] += node.stretch
            s["shrink"] += node.shrink
        if s["width"] - s["shrink"] > line_length:
            if position is None:
                j = i + 1 if i == 0 else i
                while j < len(subnodes) and subnodes[j].type in ("glue", "penalty"):
                    j += 1
                position = j - 1
            break
        if node.type in ("penalty", "glue"):
            ratio = calculate_ratio(node)
            penalty = node.penalty if node.type == "penalty" else 0
            badness = 100 * math.pow(abs(ratio), 3) + penalty
            if minimum_badness >= badness:
                position = i
                minimum_badness = badness
    return position if s["width"] - s["shrink"] > line_length else None


def _apply_best_fit(nodes: list[_Node], widths: list[float]) -> list[dict]:
    count = 0
    line_number = 0
    subnodes = nodes
    breakpoints = [{"position": 0}]
    while len(subnodes) > 0:
        bp = _get_next_breakpoint(subnodes, widths, line_number)
        if bp is not None:
            count += bp
            breakpoints.append({"position": count})
            subnodes = subnodes[bp + 1:]
            count += 1
            line_number += 1
        else:
            subnodes = []
    return breakpoints


def _insert_hyphen(line: AttributedString) -> AttributedString:
    """insertGlyph(line.length, HYPHEN, line): appended to the last run."""
    if not line.runs:
        return line
    run = line.runs[-1]
    glyph = run.attributes.font.glyph_for_code_point(_HYPHEN)
    run.glyphs = run.glyphs + [glyph]
    run.positions = run.positions + [Position(glyph.advance_width * run.attributes.scale)]
    run.glyph_indices = run.glyph_indices + [len(run.glyphs) - 1]
    run.end += 1
    line.string += "-"
    return line


def _break_lines(string: AttributedString, nodes: list[_Node], breaks: list[dict]) -> list[AttributedString]:
    start = 0
    lines = []
    for break_point in breaks:
        node = nodes[break_point["position"]]
        prev_node = nodes[break_point["position"] - 1]
        if break_point["position"] == len(nodes) - 1:
            continue
        if node.type == "penalty":
            end = prev_node.value[1]
            line = _insert_hyphen(_slice_string(start, end, string))
        else:
            end = node.value[1]
            line = _slice_string(start, end, string)
        start = end
        lines.append(line)
    lines.append(_slice_string(start, len(string.string), string))
    return lines


def _linebreaker(string: AttributedString, available_widths: list[float]) -> list[AttributedString]:
    tolerance = 4
    align = string.runs[0].attributes.align if string.runs else "left"
    nodes = _get_nodes(string, align)
    breaks = _linebreak(nodes, available_widths, tolerance)
    while len(breaks) == 0 and tolerance < _TOLERANCE_LIMIT:
        tolerance += _TOLERANCE_STEPS
        breaks = _linebreak(nodes, available_widths, tolerance)
    if len(breaks) == 0 or (len(breaks) == 1 and breaks[0]["position"] == 0):
        breaks = _apply_best_fit(nodes, available_widths)
    return _break_lines(string, nodes, breaks[1:])


# ----------------------------------------------------------------------------------------------------------------------
# Line finalization
# ----------------------------------------------------------------------------------------------------------------------

_ALIGNMENT_FACTORS = {"center": 0.5, "right": 1}
_WHITE_SPACES_CODE = 32


def _is_white_space(glyph: Optional[Glyph]) -> bool:
    return glyph is not None and _WHITE_SPACES_CODE in glyph.code_points


def _js_find_index(items, predicate) -> int:
    for i, item in enumerate(items):
        if predicate(item):
            return i
    return -1


def _leading_offset(line: Line) -> float:
    if not line.runs:
        return 0
    run = line.runs[0]
    count = _js_find_index(run.glyphs, lambda g: not _is_white_space(g))
    return sum(p.x_advance or 0 for p in run.positions[:count] if count != 0) if count != -1 else \
        sum(p.x_advance or 0 for p in run.positions[:-1])


def _trailing_offset(line: Line) -> float:
    if not line.runs:
        return 0
    run = line.runs[-1]
    glyphs = list(reversed(run.glyphs))
    positions = list(reversed(run.positions))
    count = _js_find_index(glyphs, lambda g: not _is_white_space(g))
    if count == -1:
        return sum(p.x_advance or 0 for p in positions[:-1])
    return sum(p.x_advance or 0 for p in positions[:count])


def _line_advance_width(line: Line) -> float:
    return sum(_run_advance_width(run) for run in line.runs)


def _remove_new_line(line: Line) -> Line:
    if line.string.endswith("\n"):
        line.string = line.string[:-1]
        if line.runs:
            run = line.runs[-1]
            local_len = run.end - run.start - 1
            sliced = _slice_run(0, local_len, run)
            sliced.start = run.start
            sliced.end = run.end - 1
            line.runs[-1] = sliced
    return line


def _adjust_overflow(line: Line) -> Line:
    overflow_left = _leading_offset(line) + (line.overflow_left or 0)
    overflow_right = _trailing_offset(line) + (line.overflow_right or 0)
    line.box = Box(x=line.box.x - overflow_left, y=line.box.y, width=line.box.width + overflow_left + overflow_right,
                   height=line.box.height)
    line.overflow_left = overflow_left
    line.overflow_right = overflow_right
    return line


_EXPAND_WHITESPACE = {"before": 0.5, "after": 0.5, "priority": 1, "unconstrained": False}
_EXPAND_CHAR = {"before": 0.14453125, "after": 0.14453125, "priority": 2, "unconstrained": False}
# @react-pdf/layout getLayoutOptions() overrides textkit's default whitespace shrink factor (-11/256) with -0.5
_SHRINK_WHITESPACE = {"before": -0.5, "after": -0.5, "priority": 1, "unconstrained": False}
_SHRINK_CHAR = {"before": -0.04296875, "after": -0.04296875, "priority": 2, "unconstrained": False}


def _justification(line: Line) -> Line:
    gap = line.box.width - _line_advance_width(line)
    if gap == 0:
        return line
    direction_grow = gap > 0
    char_factor = _EXPAND_CHAR if direction_grow else _SHRINK_CHAR
    whitespace_factor = _EXPAND_WHITESPACE if direction_grow else _SHRINK_WHITESPACE
    factors: list[dict] = []
    for run in line.runs:
        run_factors: list[dict] = []
        for index, glyph in enumerate(run.glyphs):
            if _is_white_space(glyph):
                f = dict(whitespace_factor)
                if index == len(run.glyphs) - 1:
                    f["before"] = 0
                    if index > 0:
                        run_factors[index - 1]["after"] = 0
            else:
                f = dict(char_factor)
            run_factors.append(f)
        factors.extend(run_factors)
    if not factors:
        return line
    factors[0]["before"] = 0
    factors[-1]["after"] = 0

    # getDistances
    total = 0.0
    priorities = [0.0] * 4
    unconstrained = [0.0] * 4
    for f in factors:
        s = f["before"] + f["after"]
        total += s
        priorities[f["priority"]] += s
        if f["unconstrained"]:
            unconstrained[f["priority"]] += s
    highest_priority = -1
    highest_priority_sum = 0.0
    remaining_gap = gap
    priority = 0
    for priority in range(0, 4):
        priority_sum = priorities[priority]
        if priority_sum != 0:
            if highest_priority == -1:
                highest_priority = priority
                highest_priority_sum = priority_sum
            if abs(remaining_gap) <= abs(priority_sum):
                priorities[priority] = remaining_gap / priority_sum
                unconstrained[priority] = 0
                remaining_gap = 0
                break
            priorities[priority] = 1
            remaining_gap -= priority_sum
            if unconstrained[priority] != 0:
                unconstrained[priority] = remaining_gap / unconstrained[priority]
                remaining_gap = 0
                break
    else:
        priority = 4
    for p in range(priority + 1, 4):
        priorities[p] = 0
        unconstrained[p] = 0
    if remaining_gap > 0 and highest_priority > -1:
        priorities[highest_priority] = (highest_priority_sum + (gap - total)) / highest_priority_sum
    distances = []
    for index, f in enumerate(factors):
        nxt = factors[index + 1] if index + 1 < len(factors) else None
        dist = f["after"] * priorities[f["priority"]]
        if nxt:
            dist += nxt["before"] * priorities[nxt["priority"]]
        if f["unconstrained"]:
            dist += f["after"] * unconstrained[f["priority"]]
            if nxt:
                dist += nxt["before"] * unconstrained[nxt["priority"]]
        distances.append(dist)
    index = 0
    for run in line.runs:
        for position in run.positions:
            position.x_advance += distances[index]
            index += 1
    return line


def _justify_line(line: Line, align: str) -> Line:
    line_width = _line_advance_width(line)
    align_factor = _ALIGNMENT_FACTORS.get(align, 0)
    remaining_width = max(0.0, line.box.width - line_width)
    should_justify = align == "justify" or line_width > line.box.width
    line.box = Box(x=line.box.x + remaining_width * align_factor, y=line.box.y, width=line.box.width,
                   height=line.box.height)
    return _justification(line) if should_justify else line


def _finalize_line(line: Line) -> Line:
    line_ascent = line_descent = line_height = line_x_advance = 0.0
    for run in line.runs:
        run.height = _run_height(run)
        run.ascent = _run_ascent(run)
        run.descent = _run_descent(run)
        run.x_advance = _run_advance_width(run)
        line_height = max(line_height, run.height)
        line_ascent = max(line_ascent, run.ascent)
        line_descent = max(line_descent, run.descent)
        line_x_advance += run.x_advance
    line.height = line_height
    line.ascent = line_ascent
    line.descent = line_descent
    line.x_advance = line_x_advance
    return line


# ----------------------------------------------------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------------------------------------------------

def layout_text(fragments: list[Fragment], width: float) -> list[Line]:
    """Lay out the text fragments of a <Text> node into lines for the given content width (infinite height)."""
    fragments = [_ignore_chars(f) for f in fragments]
    string, fragment_runs = _from_fragments(fragments)
    lines: list[Line] = []
    current_y = 0.0
    for p_start, p_end in _split_paragraphs(string):
        p_string = string[p_start:p_end]
        p_runs = [(max(s, p_start) - p_start, min(e, p_end) - p_start, a) for (s, e, a) in fragment_runs
                  if s < p_end and e > p_start]
        if not p_runs and fragment_runs:
            # empty fragment(s) at this position: keep the attributes for metrics
            p_runs = [(0, 0, fragment_runs[0][2])]
        paragraph = _preprocess_paragraph(p_string, p_runs)
        if not paragraph.runs:
            continue
        indent = 0
        available_widths = [width - indent]
        block = _linebreaker(paragraph, available_widths)
        # layoutLines
        block_lines: list[Line] = []
        for i, sliced in enumerate(block):
            line_attrs = sliced.runs[0].attributes if sliced.runs else None
            height = max(_string_height(sliced.runs), (line_attrs.line_height or 0) if line_attrs else 0)
            block_lines.append(Line(string=sliced.string, runs=sliced.runs,
                                    box=Box(x=0 + (indent if i == 0 else 0), y=current_y,
                                            width=width - (indent if i == 0 else 0), height=height)))
            current_y += height
        # finalizeBlock
        for i, line in enumerate(block_lines):
            is_last = i == len(block_lines) - 1
            line_attrs = line.runs[0].attributes if line.runs else None
            align = (line_attrs.align if line_attrs else "left")
            if is_last and align == "justify":
                align = "left"
            line = _remove_new_line(line)
            line = _adjust_overflow(line)
            line = _justify_line(line, align)
            line = _finalize_line(line)
            lines.append(line)
    return lines


def lines_width(lines: list[Line]) -> float:
    return max([0.0] + [line.x_advance for line in lines])


def lines_height(lines: list[Line]) -> float:
    return sum(line.box.height for line in lines)


@lru_cache(maxsize=None)
def load_font(path: str, reportlab_name: str) -> FontFace:
    return FontFace(path, reportlab_name)
