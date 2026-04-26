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
