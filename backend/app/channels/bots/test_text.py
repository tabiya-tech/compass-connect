import pytest

from app.channels.bots.text import split_text


class TestSplitText:
    @pytest.mark.parametrize("text, max_length, expected", [
        pytest.param("", 10, [], id="empty text has no chunks"),
        pytest.param("  \n ", 10, [], id="blank text has no chunks"),
        pytest.param("hello", 10, ["hello"], id="short text is one chunk"),
        pytest.param("0123456789", 10, ["0123456789"], id="text of exactly the max length is one chunk"),
        pytest.param("aaaa\n\nbb cc\ndd", 10, ["aaaa", "bb cc\ndd"], id="splits at a paragraph break"),
        pytest.param("aaa bbb\nccc ddd", 10, ["aaa bbb", "ccc ddd"], id="splits at a line break"),
        pytest.param("aaa bbb ccc", 10, ["aaa bbb", "ccc"], id="splits at a space"),
        pytest.param("abcdefghijklmnopqrstuvwxy", 10, ["abcdefghij", "klmnopqrst", "uvwxy"],
                     id="cuts a word longer than the max length"),
        pytest.param("ab😀😀😀😀", 6, ["ab😀😀", "😀😀"], id="an emoji counts as two"),
    ])
    def test_split_text(self, text: str, max_length: int, expected: list[str]):
        # WHEN the text is split
        actual = split_text(text, max_length)

        # THEN it is split into the expected chunks
        assert actual == expected

    def test_every_chunk_fits_and_no_text_is_lost(self):
        # GIVEN a long text with paragraphs, lines and long words
        given_text = "\n\n".join(f"Paragraph {i}: " + "word " * 300 + "x" * 5000 for i in range(5))

        # WHEN it is split for Telegram
        actual = split_text(given_text, 4096)

        # THEN every chunk fits in a Telegram message
        assert all(0 < len(chunk.encode("utf-16-le")) // 2 <= 4096 for chunk in actual)
        # AND only whitespace is lost
        assert "".join(actual).replace(" ", "").replace("\n", "") == given_text.replace(" ", "").replace("\n", "")

    def test_rejects_a_max_length_below_one(self):
        with pytest.raises(ValueError):
            split_text("hello", 0)
