"""
Port of the `hyphen` npm package (v1.10.6, ISC licence, https://github.com/ytiurin/hyphen) as used by
@react-pdf/textkit (`hyphen(require('hyphen/patterns/en-us'))`) to split words into syllables.

The frontend PDF (react-pdf) breaks lines on syllable boundaries, so the backend must split words exactly the
same way to produce the same line breaks. The port intentionally keeps the quirks of the original implementation
(e.g. the pattern offset of the first letter, JavaScript `undefined`/`NaN` arithmetic when a pattern runs past the
end of the word), because "fixing" them would produce different hyphenation points than the frontend.

The pattern data (`en_us.json`) is a JSON conversion of `hyphen/patterns/en-us.js`.
"""
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator, Optional

SOFT_HYPHEN = "­"
_DEFAULT_MIN_WORD_LENGTH = 5
_PATTERNS_FILE = Path(__file__).parent / "en_us.json"

# JavaScript: /\s|(?![\'])[\!-\@\[-\`\{-\~–-‼]/
# JS `\s` = [\t\n\v\f\r    -     　﻿]
_JS_WHITESPACE = "\t\n\u000b\u000c\r              " \
                 "    　﻿"
_NOT_LETTER_RE = re.compile("[" + re.escape(_JS_WHITESPACE) + r"]|(?!')[!-@\[-`{-~–-‼]")

# A JavaScript `undefined` slot in the levels array
_UNDEFINED = None


def _is_not_letter(char: str) -> bool:
    # RegExp.test("") is false in JS, so the end of the text counts as a "letter"
    return bool(char) and _NOT_LETTER_RE.match(char) is not None


def _js_max(a, b):
    """Math.max with JS coercion: digits are strings, undefined -> NaN."""
    a = math.nan if a is _UNDEFINED else float(a)
    b = math.nan if b is _UNDEFINED else float(b)
    if math.isnan(a) or math.isnan(b):
        return math.nan
    return max(a, b)


class _Hyphenator:
    def __init__(self, levels_table: list[str], trie: dict, exceptions: list[str], hyphen_char: str = SOFT_HYPHEN,
                 min_word_length: int = _DEFAULT_MIN_WORD_LENGTH):
        self._levels_table = levels_table
        self._trie = trie
        self._hyphen_char = hyphen_char
        self._min_word_length = min_word_length
        # exceptions are pre-populated in the cache (key "~" + word without hyphens)
        self._cache: dict[str, str] = {
            "~" + exception.replace("-", ""): exception.replace("-", hyphen_char) for exception in exceptions
        }

    # --- text reading ------------------------------------------------------------------------------------------------

    def _read_fragments(self, text: str) -> Iterator[tuple[str, str]]:
        """Port of createTextReader(createHyphenationVerifier([htmlVerifier, hyphenCharVerifier], minWordLength))."""
        accum0 = ""
        accum = ""
        html_skip = False
        hyphen_skip = False
        hyphen_char = self._hyphen_char
        i = 0
        while i < len(text):
            char1 = text[i]
            i += 1
            char2 = text[i] if i < len(text) else ""
            chars = (char1, char2)
            accum += char1

            # --- verifiers (short-circuit `skip2 || verify(...)`), they may call accumulate() ---
            skip = False
            # HTML verifier
            if html_skip:
                if chars[0] == ">":
                    accum0 += accum
                    accum = ""
                    html_skip = False
            elif chars[0] == "<" and (not _is_not_letter(chars[1]) or chars[1] == "/"):
                html_skip = True
            skip = html_skip
            if not skip:
                # hyphen char verifier
                if hyphen_skip:
                    if not _is_not_letter(chars[0]) and _is_not_letter(chars[1]):
                        accum0 += accum
                        accum = ""
                        hyphen_skip = False
                elif not _is_not_letter(chars[0]) and chars[1] == hyphen_char:
                    hyphen_skip = True
                skip = hyphen_skip

            if not skip:
                if _is_not_letter(char1) and not _is_not_letter(char2):
                    accum0 += accum
                    accum = ""
                if not _is_not_letter(char1) and _is_not_letter(char2):
                    if len(accum) >= self._min_word_length:
                        yield accum0, accum
                        accum0, accum = "", ""
                        continue
                    accum0 += accum
                    accum = ""
            if char2 == "":
                if len(accum) < self._min_word_length or skip:
                    accum0 += accum
                    accum = ""
                yield accum0, accum
                accum0, accum = "", ""

    # --- Liang ---------------------------------------------------------------------------------------------------------

    def _hyphenate_word(self, text: str) -> str:
        levels: list = [0] * (len(text) + 1)
        lowered = list("." + text.lower() + ".")
        pattern_entity_index = -1
        slice_start = 0
        while True:
            word_slice = lowered[slice_start:]
            slice_start += 1
            if len(word_slice) < 3:
                break
            pattern_entity_index += 1
            if slice_start == 2:  # isFirstCharacter()
                pattern_entity_index -= 1
            trie_ptr = self._trie
            for letter in word_slice:
                trie_node = trie_ptr.get(letter) if isinstance(trie_ptr, dict) else None
                if trie_node is None:
                    break
                trie_ptr = {}
                pattern_levels_index = -1
                if isinstance(trie_node, list):
                    trie_ptr = trie_node[0]
                    pattern_levels_index = trie_node[1]
                elif isinstance(trie_node, dict):
                    trie_ptr = trie_node
                elif isinstance(trie_node, (int, float)):
                    pattern_levels_index = int(trie_node)
                if pattern_levels_index < 0:
                    continue
                pattern_levels = self._levels_table[pattern_levels_index]
                for k, digit in enumerate(pattern_levels):
                    index = pattern_entity_index + k
                    while index >= len(levels):
                        levels.append(_UNDEFINED)  # JS array holes
                    levels[index] = _js_max(digit, levels[index])
        n = len(levels)
        levels[0] = levels[1] = levels[n - 1] = levels[n - 2] = 0
        out = []
        for i, level in enumerate(levels):
            is_odd = level is not _UNDEFINED and not (isinstance(level, float) and math.isnan(level)) and level % 2 == 1
            out.append((self._hyphen_char if is_odd else "") + (text[i] if i < len(text) else ""))
        return "".join(out)

    def __call__(self, text: str) -> str:
        result = []
        for prefix, word in self._read_fragments(text):
            if word:
                key = "~" + word
                if key not in self._cache:
                    self._cache[key] = self._hyphenate_word(word)
                word = self._cache[key]
            result.append(prefix + word)
        return "".join(result)


@lru_cache(maxsize=1)
def _get_hyphenator() -> _Hyphenator:
    with open(_PATTERNS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return _Hyphenator(levels_table=data["levels"].split(","), trie=data["trie"], exceptions=data["exceptions"])


def hyphenate(text: str) -> str:
    """Insert soft hyphens at the syllable boundaries of the words in `text` (en-us patterns)."""
    return _get_hyphenator()(text)


@lru_cache(maxsize=4096)
def _word_syllables(word: str) -> tuple[str, ...]:
    base = word if SOFT_HYPHEN in word else hyphenate(word)
    return tuple(base.split(SOFT_HYPHEN))


def word_syllables(word: Optional[str]) -> list[str]:
    """Port of textkit's `wordHyphenation()` engine: split a single (space-free) word into its syllables."""
    if word is None:
        return []
    return list(_word_syllables(word))


SyllableSplitter = Callable[[str], list[str]]
