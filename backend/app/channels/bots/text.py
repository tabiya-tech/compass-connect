def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _longest_prefix_within(text: str, max_length: int) -> int:
    """
    The number of characters at the start of the text that fit in max_length UTF-16 code units.
    """
    length = 0
    for index, char in enumerate(text):
        length += 2 if ord(char) > 0xFFFF else 1
        if length > max_length:
            return index
    return len(text)


def split_text(text: str, max_length: int) -> list[str]:
    """
    Split a text into chunks that each fit in a message of the channel.

    Lengths are counted in UTF-16 code units, the way Telegram counts them (an emoji can count as two). Splits at the
    last paragraph break that fits, otherwise the last line break, otherwise the last space, otherwise mid-word.

    :param text: The text to split.
    :param max_length: The longest message the channel accepts.
    :return: The chunks, without the whitespace around them. Empty when the text is blank.
    """
    if max_length < 1:
        raise ValueError("max_length must be at least 1")

    chunks: list[str] = []
    remaining = text.strip()
    while remaining:
        if _utf16_length(remaining) <= max_length:
            chunks.append(remaining)
            break

        window = remaining[:_longest_prefix_within(remaining, max_length)]
        cut = len(window)
        for separator in ("\n\n", "\n", " "):
            position = window.rfind(separator)
            if position > 0:
                cut = position
                break

        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return chunks
