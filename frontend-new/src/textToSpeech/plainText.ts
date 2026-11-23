const EMOJI = /[\p{Extended_Pictographic}\u{1F3FB}-\u{1F3FF}\u{FE0F}\u{200D}\u{20E3}]/gu;
const ENDS_WITH_PUNCTUATION = /[.!?:;,…]$/;

/**
 * Turns the markdown of a message into the plain text to read aloud: no link targets, markers, code fences or emoji.
 * Each line (a paragraph, a heading, an item of a list) ends with a full stop, so that it is read as a sentence.
 */
export const toPlainText = (markdown: string): string => {
  const text = markdown
    // code: keep what is in it, without the fences and backticks
    .replace(/```[^\n]*\n([\s\S]*?)```/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    // images and links: keep their text, not their target
    .replace(/!\[([^\]]*)]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]*)]\([^)]*\)/g, "$1")
    .replace(/<https?:\/\/[^>]*>/g, "")
    .replace(/https?:\/\/\S+/g, "")
    // html tags, a line break being the end of a line
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/?[a-zA-Z][^>]*>/g, "")
    // block markers: headings, quotes, rules, items of lists, rows of tables
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/^\s*([-*_])(\s*\1){2,}\s*$/gm, "")
    .replace(/^\s*([-*+]|\d+[.)])\s+/gm, "")
    .replace(/^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*$/gm, "")
    .replace(/\|/g, " ")
    // emphasis
    .replace(/(\*\*|__)(.+?)\1/g, "$2")
    .replace(/(^|[^\w*])\*(?!\s)([^*]+?)\*(?!\w)/g, "$1$2")
    .replace(/(^|[^\w])_(?!\s)([^_]+?)_(?!\w)/g, "$1$2")
    .replace(/~~(.+?)~~/g, "$1")
    .replace(EMOJI, "");

  return text
    .split("\n")
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter((line) => line.length > 0)
    .map((line) => (ENDS_WITH_PUNCTUATION.test(line) ? line : `${line}.`))
    .join(" ");
};

const utf8Length = (text: string): number => new TextEncoder().encode(text).length;

const splitIntoSentences = (text: string): string[] => {
  if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
    const segmenter = new Intl.Segmenter(undefined, { granularity: "sentence" });
    return Array.from(segmenter.segment(text), (segment) => segment.segment);
  }
  return text.match(/[^.!?…]+(?:[.!?…]+["')\]]*\s*|$)/g) ?? [text];
};

/** Splits a piece of text longer than the limit at spaces, and a word longer than the limit wherever it must. */
const splitLongPiece = (piece: string, maxBytes: number): string[] => {
  const parts: string[] = [];
  let current = "";
  for (const word of piece.split(/(\s+)/)) {
    if (utf8Length(current + word) <= maxBytes) {
      current += word;
      continue;
    }
    if (current.trim()) parts.push(current);
    current = "";
    if (utf8Length(word) <= maxBytes) {
      current = word;
      continue;
    }
    for (const character of Array.from(word)) {
      if (utf8Length(current + character) > maxBytes) {
        parts.push(current);
        current = "";
      }
      current += character;
    }
  }
  if (current.trim()) parts.push(current);
  return parts;
};

/**
 * Splits a text into parts of at most `maxBytes` bytes of UTF-8, at sentence boundaries where possible, so that each
 * part can be read aloud in one request. The parts, read in order, are the whole text.
 */
export const splitIntoParts = (text: string, maxBytes: number): string[] => {
  const parts: string[] = [];
  let current = "";
  for (const sentence of splitIntoSentences(text)) {
    if (utf8Length(current + sentence) <= maxBytes) {
      current += sentence;
      continue;
    }
    if (current.trim()) parts.push(current);
    current = "";
    if (utf8Length(sentence) <= maxBytes) {
      current = sentence;
    } else {
      const pieces = splitLongPiece(sentence, maxBytes);
      current = pieces.pop() ?? "";
      parts.push(...pieces);
    }
  }
  if (current.trim()) parts.push(current);
  return parts.map((part) => part.trim()).filter((part) => part.length > 0);
};
