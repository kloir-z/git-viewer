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


from notes import parse_notes_md


def test_parse_empty_string():
    doc = parse_notes_md("")
    assert doc.title is None
    assert doc.resolved == []
    assert doc.unresolved == []


def test_parse_title_only():
    doc = parse_notes_md("# Notes for foo.py\n")
    assert doc.title == "Notes for foo.py"
    assert doc.resolved == []


def test_parse_single_lines_section():
    md = (
        "# Notes for foo.py\n"
        "\n"
        "## L10-15\n"
        "\n"
        '<!--snapshot:{"kind":"lines","start":10,"end":15,"text":"foo"}-->\n'
        "\n"
        "メモ本文1行目\n"
        "メモ本文2行目\n"
    )
    doc = parse_notes_md(md)
    assert len(doc.resolved) == 1
    sec = doc.resolved[0]
    assert sec.anchor == {"kind": "lines", "start": 10, "end": 15}
    assert sec.snapshot == {"kind": "lines", "start": 10, "end": 15, "text": "foo"}
    assert sec.body.strip() == "メモ本文1行目\nメモ本文2行目"


def test_parse_two_sections_and_unresolved():
    md = (
        "# Notes for foo.py\n"
        "## L10\n"
        '<!--snapshot:{"kind":"lines","start":10,"end":10,"text":"a"}-->\n'
        "first\n"
        "## L20\n"
        '<!--snapshot:{"kind":"lines","start":20,"end":20,"text":"b"}-->\n'
        "second\n"
        "## Unresolved\n"
        "### L99\n"
        '<!--snapshot:{"kind":"lines","start":99,"end":99,"text":"c"}-->\n'
        "未解決理由: ファイルの行数が不足\n"
        "third\n"
    )
    doc = parse_notes_md(md)
    assert len(doc.resolved) == 2
    assert len(doc.unresolved) == 1
    assert doc.unresolved[0].anchor == {"kind": "lines", "start": 99, "end": 99}
    assert "third" in doc.unresolved[0].body


def test_parse_unrecognized_heading_is_ignored():
    md = (
        "## NonsenseHeading\n"
        "ignored body\n"
        "## L1\n"
        '<!--snapshot:{"kind":"lines","start":1,"end":1,"text":"x"}-->\n'
        "real\n"
    )
    doc = parse_notes_md(md)
    assert len(doc.resolved) == 1
    assert "real" in doc.resolved[0].body


def test_parse_missing_snapshot_kept_as_none():
    md = (
        "## L1\n"
        "no snapshot here\n"
    )
    doc = parse_notes_md(md)
    assert len(doc.resolved) == 1
    assert doc.resolved[0].snapshot is None
    assert "no snapshot here" in doc.resolved[0].body


def test_parse_duplicate_anchor_first_wins():
    md = (
        "## L1\n"
        '<!--snapshot:{"kind":"lines","start":1,"end":1,"text":"a"}-->\n'
        "first\n"
        "## L1\n"
        '<!--snapshot:{"kind":"lines","start":1,"end":1,"text":"b"}-->\n'
        "second\n"
    )
    doc = parse_notes_md(md)
    assert len(doc.resolved) == 1
    assert "first" in doc.resolved[0].body


from notes import serialize_notes_md, NotesDoc, NotesSection


def test_serialize_empty():
    doc = NotesDoc(title="Notes for foo.py")
    out = serialize_notes_md(doc)
    assert out == "# Notes for foo.py\n"


def test_serialize_one_lines_section():
    doc = NotesDoc(
        title="Notes for foo.py",
        resolved=[NotesSection(
            anchor={"kind": "lines", "start": 10, "end": 15},
            snapshot={"kind": "lines", "start": 10, "end": 15, "text": "x"},
            body="メモ",
        )],
    )
    out = serialize_notes_md(doc)
    assert "# Notes for foo.py" in out
    assert "## L10-15" in out
    assert '<!--snapshot:{"kind":"lines"' in out
    assert "メモ" in out


def test_serialize_sort_order_lines():
    doc = NotesDoc(
        title="t",
        resolved=[
            NotesSection(anchor={"kind": "lines", "start": 30, "end": 30}, snapshot=None, body="c"),
            NotesSection(anchor={"kind": "lines", "start": 10, "end": 10}, snapshot=None, body="a"),
            NotesSection(anchor={"kind": "lines", "start": 20, "end": 20}, snapshot=None, body="b"),
        ],
    )
    out = serialize_notes_md(doc)
    pos_a = out.index("## L10")
    pos_b = out.index("## L20")
    pos_c = out.index("## L30")
    assert pos_a < pos_b < pos_c


def test_serialize_unresolved_section_after_resolved():
    doc = NotesDoc(
        title="t",
        resolved=[NotesSection(anchor={"kind": "lines", "start": 1, "end": 1}, snapshot=None, body="r")],
        unresolved=[NotesSection(anchor={"kind": "lines", "start": 99, "end": 99}, snapshot=None, body="u")],
    )
    out = serialize_notes_md(doc)
    assert out.index("## L1") < out.index("## Unresolved")
    assert out.index("## Unresolved") < out.index("### L99")


def test_serialize_parse_roundtrip():
    original = NotesDoc(
        title="Notes for foo.py",
        resolved=[
            NotesSection(
                anchor={"kind": "lines", "start": 10, "end": 15},
                snapshot={"kind": "lines", "start": 10, "end": 15, "text": "x\ny"},
                body="本文1\n本文2",
            ),
            NotesSection(
                anchor={"kind": "srt", "start_ms": 1000, "end_ms": 2000},
                snapshot={"kind": "srt", "start_ms": 1000, "end_ms": 2000, "cue_index": 1, "text": "字幕"},
                body="srt メモ",
            ),
        ],
        unresolved=[
            NotesSection(
                anchor={"kind": "lines", "start": 99, "end": 99},
                snapshot={"kind": "lines", "start": 99, "end": 99, "text": "z"},
                body="未解決理由: foo\n本文",
            ),
        ],
    )
    text = serialize_notes_md(original)
    parsed = parse_notes_md(text)
    assert parsed.title == original.title
    assert len(parsed.resolved) == 2
    assert parsed.resolved[0].anchor == original.resolved[0].anchor
    assert parsed.resolved[0].snapshot == original.resolved[0].snapshot
    assert parsed.resolved[0].body == original.resolved[0].body
    assert len(parsed.unresolved) == 1
    assert parsed.unresolved[0].anchor == original.unresolved[0].anchor


from notes import atomic_write_text


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "out.md"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_overwrites(tmp_path):
    target = tmp_path / "out.md"
    target.write_text("old", encoding="utf-8")
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_creates_parent(tmp_path):
    target = tmp_path / "sub" / "out.md"
    atomic_write_text(target, "x")
    assert target.read_text(encoding="utf-8") == "x"


def test_atomic_write_no_temp_left_behind(tmp_path):
    target = tmp_path / "out.md"
    atomic_write_text(target, "x")
    leftovers = [p for p in tmp_path.iterdir() if p.name != "out.md"]
    assert leftovers == []
