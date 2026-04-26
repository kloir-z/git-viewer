from notes import encode_snapshot, decode_snapshot


def test_encode_snapshot_lines():
    snap = {"kind": "lines", "start": 10, "end": 15, "text": "foo\nbar"}
    s = encode_snapshot(snap)
    assert s.startswith("<!--snapshot:")
    assert s.endswith("-->")
    assert "\n" not in s  # must be single line


def test_encode_decode_roundtrip_lines():
    snap = {"kind": "lines", "start": 10, "end": 15, "text": "foo\nbar\n"}
    assert decode_snapshot(encode_snapshot(snap)) == snap


def test_decode_invalid_returns_none():
    assert decode_snapshot("<!--not a snapshot-->") is None
    assert decode_snapshot("plain text") is None
    assert decode_snapshot("<!--snapshot:{broken json-->") is None


def test_encode_unicode_and_quotes():
    snap = {"kind": "md_sentence", "index": 0, "text": 'これは"引用"を含む。'}
    decoded = decode_snapshot(encode_snapshot(snap))
    assert decoded == snap


def test_encode_multiline_text_is_serialized_as_escaped_newline():
    snap = {"kind": "lines", "start": 1, "end": 2, "text": "line1\nline2"}
    s = encode_snapshot(snap)
    assert "\\n" in s
    assert "\n" not in s


from notes import parse_anchor_heading, format_anchor_heading


def test_parse_lines_range():
    assert parse_anchor_heading("L10-15") == {"kind": "lines", "start": 10, "end": 15}


def test_parse_lines_single():
    assert parse_anchor_heading("L10") == {"kind": "lines", "start": 10, "end": 10}


def test_parse_md_sentence_with_text():
    assert parse_anchor_heading('S42 "hello world"') == {
        "kind": "md_sentence", "index": 42, "heading_text": "hello world",
    }


def test_parse_md_sentence_without_text():
    assert parse_anchor_heading("S42") == {
        "kind": "md_sentence", "index": 42, "heading_text": "",
    }


def test_parse_md_sentence_with_escaped_quote():
    assert parse_anchor_heading('S5 "say \\"hi\\""') == {
        "kind": "md_sentence", "index": 5, "heading_text": 'say "hi"',
    }


def test_parse_srt():
    assert parse_anchor_heading("00:01:23,456 --> 00:01:30,000") == {
        "kind": "srt", "start_ms": 83456, "end_ms": 90000,
    }


def test_parse_srt_with_dot_separator():
    assert parse_anchor_heading("00:00:01.500 --> 00:00:02.000") == {
        "kind": "srt", "start_ms": 1500, "end_ms": 2000,
    }


def test_parse_unresolved():
    assert parse_anchor_heading("Unresolved") == {"kind": "unresolved"}


def test_parse_unknown_returns_none():
    assert parse_anchor_heading("Random heading") is None
    assert parse_anchor_heading("L10-foo") is None


def test_format_lines_range():
    assert format_anchor_heading({"kind": "lines", "start": 10, "end": 15}) == "L10-15"


def test_format_lines_single():
    assert format_anchor_heading({"kind": "lines", "start": 10, "end": 10}) == "L10"


def test_format_md_sentence_truncates_to_30_chars():
    long = "a" * 50
    out = format_anchor_heading({"kind": "md_sentence", "index": 7, "heading_text": long})
    assert out == 'S7 "' + "a" * 30 + '..."'


def test_format_md_sentence_short_no_ellipsis():
    out = format_anchor_heading({"kind": "md_sentence", "index": 7, "heading_text": "short"})
    assert out == 'S7 "short"'


def test_format_md_sentence_normalizes_whitespace():
    out = format_anchor_heading({"kind": "md_sentence", "index": 1, "heading_text": "a  b\nc"})
    assert out == 'S1 "a b c"'


def test_format_md_sentence_escapes_quote():
    out = format_anchor_heading({"kind": "md_sentence", "index": 1, "heading_text": 'a"b'})
    assert out == 'S1 "a\\"b"'


def test_format_srt():
    out = format_anchor_heading({"kind": "srt", "start_ms": 83456, "end_ms": 90000})
    assert out == "00:01:23,456 --> 00:01:30,000"
