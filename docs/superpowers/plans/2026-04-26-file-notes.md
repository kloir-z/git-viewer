# File Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add sidecar memo (`<filename.ext>.notes.md`) feature for text/code/MD/SRT files in git-viewer, with create/edit/delete UI, anchor auto-relocation, and unresolved memo handling.

**Architecture:** Pure-Python parser/serializer/resolver in a new `notes.py` module (with pytest unit tests); five new Flask endpoints in `app.py`; vanilla JS UI integrated into `templates/index.html` and `static/style.css`. Server resolves anchors for text/code/SRT and writes back relocations atomically; MD anchor resolution is client-side with a separate relocate endpoint.

**Tech Stack:** Flask 3.x, Python 3.10+, pytest, marked.js (existing CDN), highlight.js (existing CDN), vanilla JS, CSS.

**Spec:** `docs/superpowers/specs/2026-04-26-file-notes-design.md` — read this first. Tasks below reference the spec for design details and only restate code/tests inline.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `notes.py` | Create | Pure logic: heading parsing, snapshot codec, NotesDoc parse/serialize, atomic write, anchor resolution (lines + SRT). No Flask. |
| `tests/__init__.py` | Create | Empty marker file |
| `tests/test_notes.py` | Create | Unit tests for `notes.py` |
| `tests/conftest.py` | Create | pytest config (e.g., `tmp_path` fixtures) |
| `pytest.ini` | Create | Minimal pytest config |
| `requirements.txt` | Modify | Add `pytest>=8.0` |
| `app.py` | Modify | Add 5 endpoints under `/api/notes*`. Reuse existing `valid_repo`, path-validation, and `TEXT_EXTS` patterns. |
| `templates/index.html` | Modify | Inline JS: notes fetcher, marker rendering, modal UI, unresolved panel, file list badges. |
| `static/style.css` | Modify | Marker (💬) styles, modal styles, badge styles, unresolved panel styles. |

---

## Phase 1: `notes.py` module (pure logic, TDD)

All Phase 1 tasks operate on `notes.py` and `tests/test_notes.py`. No Flask, no I/O beyond what the resolver needs (file reads), no UI.

### Task 1: Bootstrap pytest infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`
- Modify: `requirements.txt`

- [ ] **Step 1: Add pytest to requirements**

Modify `requirements.txt`:
```
flask>=3.0
pytest>=8.0
```

- [ ] **Step 2: Create empty test package**

Write `tests/__init__.py` (empty file).

- [ ] **Step 3: Add pytest config**

Write `pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v
```

- [ ] **Step 4: Add conftest with import path setup**

Write `tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

This lets `tests/test_notes.py` do `from notes import ...` even when pytest runs from project root.

- [ ] **Step 5: Install pytest and verify it runs**

Run: `pip install pytest>=8.0` (or `pip install -r requirements.txt`)
Run: `pytest`
Expected: `no tests ran in 0.0s` (no error).

- [ ] **Step 6: Commit**

```bash
git add tests/__init__.py tests/conftest.py pytest.ini requirements.txt
git commit -m "chore: bootstrap pytest infrastructure"
```

---

### Task 2: Snapshot codec (encode/decode `<!--snapshot:{JSON}-->`)

**Files:**
- Create: `notes.py`
- Create/modify: `tests/test_notes.py`

Spec section: ファイルフォーマット → スナップショット仕様 / スナップショット書式の制約

- [ ] **Step 1: Write failing tests for snapshot codec**

Append to `tests/test_notes.py`:
```python
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
```

- [ ] **Step 2: Run tests; expect ImportError or NameError**

Run: `pytest tests/test_notes.py -v`
Expected: ImportError on `from notes import ...`.

- [ ] **Step 3: Implement codec**

Create `notes.py`:
```python
import json
import re

SNAPSHOT_RE = re.compile(r"^<!--snapshot:(.*)-->$")


def encode_snapshot(snap: dict) -> str:
    """Encode a snapshot dict as a single-line HTML comment."""
    body = json.dumps(snap, ensure_ascii=False, separators=(",", ":"))
    if "\n" in body:
        raise ValueError("snapshot JSON must not contain literal newlines")
    return f"<!--snapshot:{body}-->"


def decode_snapshot(line: str) -> dict | None:
    """Decode a snapshot HTML comment line. Returns None if invalid."""
    m = SNAPSHOT_RE.match(line.strip())
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data
```

- [ ] **Step 4: Run tests; expect PASS**

Run: `pytest tests/test_notes.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add notes.py tests/test_notes.py
git commit -m "feat(notes): snapshot codec"
```

---

### Task 3: Anchor heading parsing

**Files:**
- Modify: `notes.py`
- Modify: `tests/test_notes.py`

Spec section: 見出しパース正規表現 / アンカー見出し書式

- [ ] **Step 1: Write failing tests**

Append to `tests/test_notes.py`:
```python
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
    # spec allows . or , in regex; we normalize to ms
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
```

- [ ] **Step 2: Run; expect ImportError**

Run: `pytest tests/test_notes.py -v`
Expected: ImportError on parse_anchor_heading / format_anchor_heading.

- [ ] **Step 3: Implement parsers and formatters**

Append to `notes.py`:
```python
HEADING_LINES = re.compile(r"^L(\d+)(?:-(\d+))?$")
HEADING_MD = re.compile(r'^S(\d+)(?:\s+"((?:[^"\\]|\\.)*)")?$')
HEADING_SRT = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$"
)
HEADING_UNRESOLVED = re.compile(r"^Unresolved$")

WS_RE = re.compile(r"\s+")


def _ms(h, m, s, ms):
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def _format_ms(ms):
    s, ms = divmod(int(ms), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_anchor_heading(text: str) -> dict | None:
    """Parse a heading body (without leading `## ` / `### `). Returns None if unrecognized."""
    text = text.strip()
    if HEADING_UNRESOLVED.match(text):
        return {"kind": "unresolved"}
    m = HEADING_LINES.match(text)
    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        return {"kind": "lines", "start": start, "end": end}
    m = HEADING_MD.match(text)
    if m:
        idx = int(m.group(1))
        raw = m.group(2) or ""
        # un-escape \" and \\
        unescaped = re.sub(r"\\(.)", r"\1", raw)
        return {"kind": "md_sentence", "index": idx, "heading_text": unescaped}
    m = HEADING_SRT.match(text)
    if m:
        start_ms = _ms(*m.group(1, 2, 3, 4))
        end_ms = _ms(*m.group(5, 6, 7, 8))
        return {"kind": "srt", "start_ms": start_ms, "end_ms": end_ms}
    return None


def format_anchor_heading(anchor: dict) -> str:
    kind = anchor["kind"]
    if kind == "lines":
        start, end = anchor["start"], anchor["end"]
        return f"L{start}" if start == end else f"L{start}-{end}"
    if kind == "md_sentence":
        text = WS_RE.sub(" ", anchor.get("heading_text", "")).strip()
        if len(text) > 30:
            text = text[:30] + "..."
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'S{anchor["index"]} "{escaped}"'
    if kind == "srt":
        return f"{_format_ms(anchor['start_ms'])} --> {_format_ms(anchor['end_ms'])}"
    if kind == "unresolved":
        return "Unresolved"
    raise ValueError(f"unknown anchor kind: {kind}")
```

- [ ] **Step 4: Run; expect PASS**

Run: `pytest tests/test_notes.py -v`
Expected: all parse/format tests pass.

- [ ] **Step 5: Commit**

```bash
git add notes.py tests/test_notes.py
git commit -m "feat(notes): anchor heading parse/format"
```

---

### Task 4: NotesDoc model + `parse_notes_md`

**Files:**
- Modify: `notes.py`
- Modify: `tests/test_notes.py`

Spec section: `<filename.ext>.notes.md` ファイルフォーマット → ファイル全体構造

- [ ] **Step 1: Write failing tests**

Append to `tests/test_notes.py`:
```python
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
```

- [ ] **Step 2: Run; expect ImportError**

Run: `pytest tests/test_notes.py -v`
Expected: ImportError on parse_notes_md.

- [ ] **Step 3: Implement NotesDoc dataclasses + parser**

Append to `notes.py`:
```python
from dataclasses import dataclass, field


@dataclass
class NotesSection:
    anchor: dict
    snapshot: dict | None
    body: str


@dataclass
class NotesDoc:
    title: str | None = None
    resolved: list[NotesSection] = field(default_factory=list)
    unresolved: list[NotesSection] = field(default_factory=list)


def parse_notes_md(text: str) -> NotesDoc:
    doc = NotesDoc()
    lines = text.splitlines()
    i = 0
    in_unresolved = False
    seen_anchors: set[tuple] = set()

    # title
    if i < len(lines) and lines[i].startswith("# "):
        doc.title = lines[i][2:].strip()
        i += 1

    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            heading = line[3:].strip()
            anchor = parse_anchor_heading(heading)
            i += 1
            if anchor and anchor["kind"] == "unresolved":
                in_unresolved = True
                continue
            section, i = _consume_section_body(lines, i, level=2)
            if anchor is None:
                continue  # ignore unrecognized headings
            key = _anchor_key(anchor)
            if key in seen_anchors:
                continue
            seen_anchors.add(key)
            section.anchor = anchor
            target = doc.unresolved if in_unresolved else doc.resolved
            # in resolved mode but file has Unresolved before this — shouldn't happen, treat as resolved
            target.append(section)
        elif line.startswith("### ") and in_unresolved:
            heading = line[4:].strip()
            anchor = parse_anchor_heading(heading)
            i += 1
            section, i = _consume_section_body(lines, i, level=3)
            if anchor is None or anchor["kind"] == "unresolved":
                continue
            key = _anchor_key(anchor)
            if key in seen_anchors:
                continue
            seen_anchors.add(key)
            section.anchor = anchor
            doc.unresolved.append(section)
        else:
            i += 1
    return doc


def _consume_section_body(lines, start, level):
    """Consume body lines until next heading at same or higher level. Returns (section, new_index)."""
    body_lines = []
    snapshot = None
    i = start
    boundary_prefixes = ["## "] if level == 2 else ["## ", "### "]
    # Skip leading blank lines but allow them in body too
    while i < len(lines):
        line = lines[i]
        if any(line.startswith(p) for p in boundary_prefixes):
            break
        if snapshot is None:
            decoded = decode_snapshot(line)
            if decoded is not None:
                snapshot = decoded
                i += 1
                continue
        body_lines.append(line)
        i += 1
    # strip leading/trailing blank lines from body
    while body_lines and body_lines[0].strip() == "":
        body_lines.pop(0)
    while body_lines and body_lines[-1].strip() == "":
        body_lines.pop()
    body = "\n".join(body_lines)
    return NotesSection(anchor={}, snapshot=snapshot, body=body), i


def _anchor_key(anchor: dict) -> tuple:
    kind = anchor["kind"]
    if kind == "lines":
        return ("lines", anchor["start"], anchor["end"])
    if kind == "md_sentence":
        return ("md_sentence", anchor["index"])
    if kind == "srt":
        return ("srt", anchor["start_ms"], anchor["end_ms"])
    return (kind,)
```

- [ ] **Step 4: Run; expect PASS**

Run: `pytest tests/test_notes.py -v`
Expected: all parse tests pass.

- [ ] **Step 5: Commit**

```bash
git add notes.py tests/test_notes.py
git commit -m "feat(notes): parse_notes_md"
```

---

### Task 5: `serialize_notes_md` + sort order

**Files:**
- Modify: `notes.py`
- Modify: `tests/test_notes.py`

Spec section: ファイル全体構造 → セクションの並び順

- [ ] **Step 1: Write failing tests**

Append:
```python
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
```

- [ ] **Step 2: Run; expect ImportError**

Run: `pytest tests/test_notes.py -v`

- [ ] **Step 3: Implement serializer**

Append to `notes.py`:
```python
def _sort_key(anchor: dict):
    kind = anchor["kind"]
    if kind == "lines":
        return (0, anchor["start"], anchor["end"])
    if kind == "md_sentence":
        return (0, anchor["index"], 0)
    if kind == "srt":
        return (0, anchor["start_ms"], anchor["end_ms"])
    return (1, 0, 0)


def serialize_notes_md(doc: NotesDoc) -> str:
    parts = []
    if doc.title:
        parts.append(f"# {doc.title}\n")

    for sec in sorted(doc.resolved, key=lambda s: _sort_key(s.anchor)):
        parts.append(_serialize_section(sec, level=2))

    if doc.unresolved:
        parts.append("\n## Unresolved\n")
        for sec in sorted(doc.unresolved, key=lambda s: _sort_key(s.anchor)):
            parts.append(_serialize_section(sec, level=3))

    return "".join(parts)


def _serialize_section(sec: NotesSection, level: int) -> str:
    prefix = "##" if level == 2 else "###"
    out = [f"\n{prefix} {format_anchor_heading(sec.anchor)}\n"]
    if sec.snapshot is not None:
        out.append(f"\n{encode_snapshot(sec.snapshot)}\n")
    if sec.body:
        out.append(f"\n{sec.body.rstrip()}\n")
    return "".join(out)
```

- [ ] **Step 4: Run; expect PASS**

Run: `pytest tests/test_notes.py -v`

- [ ] **Step 5: Commit**

```bash
git add notes.py tests/test_notes.py
git commit -m "feat(notes): serialize_notes_md"
```

---

### Task 6: Atomic file write

**Files:**
- Modify: `notes.py`
- Modify: `tests/test_notes.py`

- [ ] **Step 1: Write failing tests**

Append:
```python
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
```

- [ ] **Step 2: Run; expect ImportError**

- [ ] **Step 3: Implement**

Append to `notes.py`:
```python
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically (tempfile + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add notes.py tests/test_notes.py
git commit -m "feat(notes): atomic_write_text"
```

---

### Task 7: Lines normalization + resolver

**Files:**
- Modify: `notes.py`
- Modify: `tests/test_notes.py`

Spec section: アンカー解決ロジック → テキスト/コード（行ベース）

- [ ] **Step 1: Write failing tests**

Append:
```python
from notes import resolve_lines_anchor


def _make_snap(start, end, text):
    return {"kind": "lines", "start": start, "end": end, "text": text}


def test_resolve_lines_exact_match():
    file_text = "a\nb\nc\nd\ne\n"
    snap = _make_snap(2, 3, "b\nc")
    result = resolve_lines_anchor(file_text, anchor={"kind": "lines", "start": 2, "end": 3}, snapshot=snap)
    assert result.resolved is True
    assert result.relocated is False
    assert result.start == 2
    assert result.end == 3


def test_resolve_lines_relocated_within_50():
    # snapshot says lines 5-6 should match "x\ny" but content moved to 8-9
    file_text = "a\nb\nc\nd\ne\nf\ng\nx\ny\nz\n"
    snap = _make_snap(5, 6, "x\ny")
    result = resolve_lines_anchor(file_text, anchor={"kind": "lines", "start": 5, "end": 6}, snapshot=snap)
    assert result.resolved is True
    assert result.relocated is True
    assert result.start == 8
    assert result.end == 9


def test_resolve_lines_unresolved_when_text_gone():
    file_text = "a\nb\nc\n"
    snap = _make_snap(1, 2, "x\ny")
    result = resolve_lines_anchor(file_text, anchor={"kind": "lines", "start": 1, "end": 2}, snapshot=snap)
    assert result.resolved is False


def test_resolve_lines_unresolved_when_outside_50():
    snap_text = "x\ny"
    file_text = "\n".join(["pad"] * 100 + snap_text.split("\n") + ["pad"] * 5) + "\n"
    snap = _make_snap(5, 6, snap_text)
    result = resolve_lines_anchor(file_text, anchor={"kind": "lines", "start": 5, "end": 6}, snapshot=snap)
    assert result.resolved is False


def test_resolve_lines_picks_nearest_when_multiple_candidates():
    snap_text = "TARGET"
    file_text = "TARGET\n" + "\n".join(["x"] * 9) + "\nTARGET\n" + "\n".join(["y"] * 5) + "\n"
    # snapshot original was line 11; copies at lines 1 and 11 (and 11 is the original)
    snap = _make_snap(11, 11, snap_text)
    result = resolve_lines_anchor(file_text, anchor={"kind": "lines", "start": 11, "end": 11}, snapshot=snap)
    assert result.resolved is True
    assert result.start == 11  # nearest


def test_resolve_lines_no_snapshot_uses_anchor_range():
    file_text = "a\nb\nc\n"
    result = resolve_lines_anchor(file_text, anchor={"kind": "lines", "start": 2, "end": 3}, snapshot=None)
    assert result.resolved is True
    assert result.relocated is False


def test_resolve_lines_no_snapshot_out_of_range():
    file_text = "a\nb\n"
    result = resolve_lines_anchor(file_text, anchor={"kind": "lines", "start": 5, "end": 6}, snapshot=None)
    assert result.resolved is False
```

- [ ] **Step 2: Run; expect ImportError**

- [ ] **Step 3: Implement**

Append to `notes.py`:
```python
@dataclass
class LinesResolution:
    resolved: bool
    relocated: bool = False
    start: int = 0
    end: int = 0
    reason: str = ""


def _normalize_block(s: str) -> str:
    # remove trailing whitespace per line and trailing blank lines
    lines = s.split("\n")
    return "\n".join(line.rstrip() for line in lines).rstrip("\n")


def resolve_lines_anchor(file_text: str, anchor: dict, snapshot: dict | None) -> LinesResolution:
    file_lines = file_text.split("\n")
    if file_lines and file_lines[-1] == "":
        file_lines.pop()  # drop trailing empty from final newline

    anchor_start, anchor_end = anchor["start"], anchor["end"]
    n = len(file_lines)

    if snapshot is None:
        if 1 <= anchor_start <= anchor_end <= n:
            return LinesResolution(resolved=True, start=anchor_start, end=anchor_end)
        return LinesResolution(resolved=False, reason="行範囲がファイル外")

    snap_text = snapshot.get("text", "")
    snap_lines = snap_text.split("\n")
    if snap_lines and snap_lines[-1] == "":
        snap_lines.pop()
    block_size = len(snap_lines)
    if block_size == 0:
        # nothing to match against; fall back to anchor-range check
        if 1 <= anchor_start <= anchor_end <= n:
            return LinesResolution(resolved=True, start=anchor_start, end=anchor_end)
        return LinesResolution(resolved=False, reason="スナップショットが空")

    target = _normalize_block(snap_text)

    # exact-position check
    if 1 <= anchor_start and anchor_start - 1 + block_size <= n:
        chunk = "\n".join(file_lines[anchor_start - 1 : anchor_start - 1 + block_size])
        if _normalize_block(chunk) == target:
            return LinesResolution(
                resolved=True, start=anchor_start, end=anchor_start + block_size - 1
            )

    # search ±50
    search_min = max(1, anchor_start - 50)
    search_max = n - block_size + 1
    if anchor_end + 50 < search_max:
        search_max = anchor_end + 50

    candidates = []
    for i in range(search_min, search_max + 1):
        chunk = "\n".join(file_lines[i - 1 : i - 1 + block_size])
        if _normalize_block(chunk) == target:
            candidates.append(i)

    if not candidates:
        return LinesResolution(resolved=False, reason="行範囲のテキストが見つからなかった")

    best = min(candidates, key=lambda i: abs(i - anchor_start))
    return LinesResolution(
        resolved=True, relocated=(best != anchor_start),
        start=best, end=best + block_size - 1,
    )
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add notes.py tests/test_notes.py
git commit -m "feat(notes): resolve_lines_anchor"
```

---

### Task 8: SRT cue parser + resolver

**Files:**
- Modify: `notes.py`
- Modify: `tests/test_notes.py`

Spec section: SRT 解決

- [ ] **Step 1: Write failing tests**

Append:
```python
from notes import parse_srt_cues, resolve_srt_anchor


SRT_SAMPLE = (
    "1\n"
    "00:00:01,000 --> 00:00:02,500\n"
    "Hello\n"
    "\n"
    "2\n"
    "00:00:03,000 --> 00:00:04,000\n"
    "World\n"
)


def test_parse_srt_cues_basic():
    cues = parse_srt_cues(SRT_SAMPLE)
    assert len(cues) == 2
    assert cues[0]["start_ms"] == 1000
    assert cues[0]["end_ms"] == 2500
    assert cues[0]["text"] == "Hello"
    assert cues[0]["cue_index"] == 1
    assert cues[1]["text"] == "World"


def test_parse_srt_cues_handles_dot_separator():
    src = "1\n00:00:01.000 --> 00:00:02.000\nHi\n"
    cues = parse_srt_cues(src)
    assert cues[0]["start_ms"] == 1000


def test_resolve_srt_exact_match():
    cues = parse_srt_cues(SRT_SAMPLE)
    anchor = {"kind": "srt", "start_ms": 3000, "end_ms": 4000}
    result = resolve_srt_anchor(cues, anchor)
    assert result.resolved is True
    assert result.cue_index == 2


def test_resolve_srt_no_match():
    cues = parse_srt_cues(SRT_SAMPLE)
    anchor = {"kind": "srt", "start_ms": 9999, "end_ms": 10000}
    result = resolve_srt_anchor(cues, anchor)
    assert result.resolved is False
```

- [ ] **Step 2: Run; expect ImportError**

- [ ] **Step 3: Implement**

Append to `notes.py`:
```python
SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)


def parse_srt_cues(text: str) -> list[dict]:
    cues = []
    blocks = re.split(r"\r?\n\r?\n", text.strip())
    for block in blocks:
        block_lines = block.splitlines()
        if len(block_lines) < 2:
            continue
        # block_lines[0] is index (sometimes missing), [1] is timecode
        idx_line = block_lines[0].strip()
        if SRT_TIME_RE.match(idx_line):
            time_idx = 0
            cue_index = len(cues) + 1
        else:
            time_idx = 1
            try:
                cue_index = int(idx_line)
            except ValueError:
                cue_index = len(cues) + 1
        if time_idx >= len(block_lines):
            continue
        m = SRT_TIME_RE.match(block_lines[time_idx])
        if not m:
            continue
        start_ms = _ms(*m.group(1, 2, 3, 4))
        end_ms = _ms(*m.group(5, 6, 7, 8))
        text_body = "\n".join(block_lines[time_idx + 1 :]).strip()
        cues.append({
            "cue_index": cue_index, "start_ms": start_ms, "end_ms": end_ms, "text": text_body,
        })
    return cues


@dataclass
class SrtResolution:
    resolved: bool
    cue_index: int = 0
    reason: str = ""


def resolve_srt_anchor(cues: list[dict], anchor: dict) -> SrtResolution:
    target = (anchor["start_ms"], anchor["end_ms"])
    for cue in cues:
        if (cue["start_ms"], cue["end_ms"]) == target:
            return SrtResolution(resolved=True, cue_index=cue["cue_index"])
    return SrtResolution(resolved=False, reason="該当タイムコードの字幕が見つからなかった")
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add notes.py tests/test_notes.py
git commit -m "feat(notes): SRT parse + resolve"
```

---

### Task 9: High-level helpers used by API layer

**Files:**
- Modify: `notes.py`
- Modify: `tests/test_notes.py`

Provides: `notes_path_for(target_path)`, `load_notes(notes_path)`, `save_notes(notes_path, doc)`, `upsert_section(doc, section)`, `delete_section(doc, anchor)`, and a top-level `resolve_doc(doc, target_text, kind)` that walks resolved sections and applies the right resolver.

- [ ] **Step 1: Write failing tests**

Append:
```python
from notes import notes_path_for, load_notes, save_notes, upsert_section, delete_section


def test_notes_path_for_appends_suffix():
    from pathlib import PurePosixPath
    assert notes_path_for(PurePosixPath("foo/bar.srt")).as_posix() == "foo/bar.srt.notes.md"
    assert notes_path_for(PurePosixPath("README.md")).as_posix() == "README.md.notes.md"


def test_notes_path_for_rejects_already_notes():
    from pathlib import PurePosixPath
    import pytest
    with pytest.raises(ValueError):
        notes_path_for(PurePosixPath("foo.notes.md"))


def test_load_notes_missing_returns_empty(tmp_path):
    p = tmp_path / "x.notes.md"
    doc = load_notes(p)
    assert doc.title is None
    assert doc.resolved == []


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "x.notes.md"
    doc = NotesDoc(title="Notes for x.py", resolved=[NotesSection(
        anchor={"kind": "lines", "start": 1, "end": 1}, snapshot=None, body="hello")])
    save_notes(p, doc)
    loaded = load_notes(p)
    assert loaded.title == doc.title
    assert loaded.resolved[0].body == "hello"


def test_upsert_inserts_new():
    doc = NotesDoc()
    sec = NotesSection(anchor={"kind": "lines", "start": 1, "end": 1}, snapshot=None, body="a")
    upsert_section(doc, sec)
    assert len(doc.resolved) == 1


def test_upsert_overwrites_existing():
    doc = NotesDoc(resolved=[NotesSection(
        anchor={"kind": "lines", "start": 1, "end": 1}, snapshot=None, body="old")])
    upsert_section(doc, NotesSection(
        anchor={"kind": "lines", "start": 1, "end": 1}, snapshot=None, body="new"))
    assert len(doc.resolved) == 1
    assert doc.resolved[0].body == "new"


def test_delete_removes_existing():
    doc = NotesDoc(resolved=[NotesSection(
        anchor={"kind": "lines", "start": 1, "end": 1}, snapshot=None, body="x")])
    deleted = delete_section(doc, {"kind": "lines", "start": 1, "end": 1})
    assert deleted is True
    assert doc.resolved == []


def test_delete_not_found():
    doc = NotesDoc()
    deleted = delete_section(doc, {"kind": "lines", "start": 1, "end": 1})
    assert deleted is False
```

- [ ] **Step 2: Run; expect ImportError**

- [ ] **Step 3: Implement helpers**

Append to `notes.py`:
```python
NOTES_SUFFIX = ".notes.md"


def notes_path_for(target_path) -> Path:
    """Given a relative target file path, return the corresponding notes path."""
    p = Path(target_path)
    if p.name.endswith(NOTES_SUFFIX):
        raise ValueError("cannot create notes for a notes file")
    return p.parent / (p.name + NOTES_SUFFIX)


def load_notes(path) -> NotesDoc:
    p = Path(path)
    if not p.is_file():
        return NotesDoc()
    text = p.read_text(encoding="utf-8")
    return parse_notes_md(text)


def save_notes(path, doc: NotesDoc) -> None:
    text = serialize_notes_md(doc)
    atomic_write_text(Path(path), text)


def upsert_section(doc: NotesDoc, section: NotesSection) -> None:
    key = _anchor_key(section.anchor)
    for i, existing in enumerate(doc.resolved):
        if _anchor_key(existing.anchor) == key:
            doc.resolved[i] = section
            return
    doc.resolved.append(section)


def delete_section(doc: NotesDoc, anchor: dict) -> bool:
    key = _anchor_key(anchor)
    for i, existing in enumerate(doc.resolved):
        if _anchor_key(existing.anchor) == key:
            doc.resolved.pop(i)
            return True
    for i, existing in enumerate(doc.unresolved):
        if _anchor_key(existing.anchor) == key:
            doc.unresolved.pop(i)
            return True
    return False
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add notes.py tests/test_notes.py
git commit -m "feat(notes): high-level load/save/upsert/delete helpers"
```

---

## Phase 2: Flask API endpoints

All Phase 2 tasks modify `app.py`. Use the same `valid_repo`, path validation, and `TEXT_EXTS` patterns already present.

### Task 10: GET /api/notes

**Files:**
- Modify: `app.py`
- Modify: `tests/test_notes.py` (add Flask integration test)

Spec section: API 詳細 → `GET /api/notes`

- [ ] **Step 1: Write failing test (integration)**

Append to `tests/test_notes.py`:
```python
import pytest


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Flask test client with CODE_DIR pointing at a tmp repo."""
    repo = tmp_path / "myrepo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("GIT_VIEWER_CODE_DIR", str(tmp_path))
    # Re-import app fresh so it picks up env
    import importlib, sys
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as flask_app  # noqa: F401
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client(), repo


def test_get_notes_missing_file(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("x = 1\n", encoding="utf-8")
    resp = client.get("/api/notes?repo=myrepo&path=foo.py")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["mtime"] is None
    assert body["resolved"] == []
    assert body["unresolved"] == []
    assert body["kind"] == "lines"


def test_get_notes_resolved_lines(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    notes = (
        "# Notes for foo.py\n"
        "## L2-3\n"
        '<!--snapshot:{"kind":"lines","start":2,"end":3,"text":"b\\nc"}-->\n'
        "メモ\n"
    )
    (repo / "foo.py.notes.md").write_text(notes, encoding="utf-8")
    resp = client.get("/api/notes?repo=myrepo&path=foo.py")
    body = resp.get_json()
    assert len(body["resolved"]) == 1
    sec = body["resolved"][0]
    assert sec["anchor"] == {"kind": "lines", "start": 2, "end": 3}
    assert sec["relocated"] is False


def test_get_notes_relocates_and_writes_back(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("\n\n\nb\nc\nd\n", encoding="utf-8")
    notes = (
        "# Notes for foo.py\n"
        "## L1-2\n"
        '<!--snapshot:{"kind":"lines","start":1,"end":2,"text":"b\\nc"}-->\n'
        "メモ\n"
    )
    notes_path = repo / "foo.py.notes.md"
    notes_path.write_text(notes, encoding="utf-8")
    resp = client.get("/api/notes?repo=myrepo&path=foo.py")
    body = resp.get_json()
    assert body["resolved"][0]["relocated"] is True
    assert body["resolved"][0]["anchor"] == {"kind": "lines", "start": 4, "end": 5}
    # File rewritten with new heading
    assert "## L4-5" in notes_path.read_text(encoding="utf-8")


def test_get_notes_unresolved_lines(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("a\n", encoding="utf-8")
    notes = (
        "## L10\n"
        '<!--snapshot:{"kind":"lines","start":10,"end":10,"text":"missing"}-->\n'
        "メモ\n"
    )
    (repo / "foo.py.notes.md").write_text(notes, encoding="utf-8")
    resp = client.get("/api/notes?repo=myrepo&path=foo.py")
    body = resp.get_json()
    assert body["resolved"] == []
    assert len(body["unresolved"]) == 1


def test_get_notes_md_returns_client_resolve_flag(app_client):
    client, repo = app_client
    (repo / "doc.md").write_text("hello\n", encoding="utf-8")
    notes = (
        "## S0 \"hello\"\n"
        '<!--snapshot:{"kind":"md_sentence","index":0,"text":"hello"}-->\n'
        "メモ\n"
    )
    (repo / "doc.md.notes.md").write_text(notes, encoding="utf-8")
    resp = client.get("/api/notes?repo=myrepo&path=doc.md")
    body = resp.get_json()
    assert body["kind"] == "md_sentence"
    assert body["resolved"][0]["client_resolve"] is True
```

- [ ] **Step 2: Run; expect failures (404 / endpoint missing)**

Run: `pytest tests/test_notes.py -v`

- [ ] **Step 3: Implement endpoint in `app.py`**

Add near the bottom of `app.py` (after existing routes), and add imports at top:
```python
# Add to imports
import notes as notes_mod
```

Add helpers and route:
```python
NOTES_SUFFIX = ".notes.md"


def _notes_kind_for_path(path: str) -> str:
    ext = ('.' + path.rsplit('.', 1)[1]).lower() if '.' in path else ''
    if ext == '.md':
        return 'md_sentence'
    if ext == '.srt':
        return 'srt'
    return 'lines'


def _promote_to_unresolved(sec, reason):
    """Mutate a section so its body has a '未解決理由:' line prepended (if not already)."""
    body = sec.body or ""
    if "未解決理由:" not in body.split("\n", 1)[0]:
        sec.body = f"未解決理由: {reason}\n\n{body}".rstrip() + "\n"


def _resolve_doc_server_side(doc, target_path: Path, kind: str) -> bool:
    """Resolve text/code or SRT anchors in place. Returns True if doc mutated."""
    if not target_path.is_file():
        if doc.resolved:
            for sec in doc.resolved:
                _promote_to_unresolved(sec, "対象ファイルが存在しない")
                doc.unresolved.append(sec)
            doc.resolved = []
            return True
        return False

    mutated = False
    file_text = target_path.read_text(encoding="utf-8", errors="replace")

    if kind == 'srt':
        cues = notes_mod.parse_srt_cues(file_text)
        new_resolved = []
        for sec in doc.resolved:
            if sec.anchor["kind"] != "srt":
                new_resolved.append(sec)
                continue
            r = notes_mod.resolve_srt_anchor(cues, sec.anchor)
            if r.resolved:
                new_resolved.append(sec)
            else:
                _promote_to_unresolved(sec, r.reason or "SRT タイムコード不一致")
                doc.unresolved.append(sec)
                mutated = True
        doc.resolved = new_resolved
    elif kind == 'lines':
        new_resolved = []
        for sec in doc.resolved:
            if sec.anchor["kind"] != "lines":
                new_resolved.append(sec)
                continue
            r = notes_mod.resolve_lines_anchor(file_text, sec.anchor, sec.snapshot)
            if not r.resolved:
                _promote_to_unresolved(sec, r.reason or "行範囲解決失敗")
                doc.unresolved.append(sec)
                mutated = True
                continue
            if r.relocated:
                sec.anchor = {"kind": "lines", "start": r.start, "end": r.end}
                mutated = True
            new_resolved.append(sec)
        doc.resolved = new_resolved
    # md_sentence: no server-side changes

    return mutated


@app.route("/api/notes")
def notes_get():
    name = request.args.get("repo", "")
    path = request.args.get("path", "")
    repo_path = valid_repo(name)
    if not path or ".." in path or path.endswith(NOTES_SUFFIX):
        abort(400)

    target_full = (repo_path / path).resolve()
    if not str(target_full).startswith(str(repo_path.resolve())):
        abort(403)

    kind = _notes_kind_for_path(path)
    notes_full = target_full.parent / (target_full.name + NOTES_SUFFIX)

    if not notes_full.is_file():
        return jsonify({"mtime": None, "kind": kind, "resolved": [], "unresolved": []})

    doc = notes_mod.load_notes(notes_full)
    mutated = _resolve_doc_server_side(doc, target_full, kind)
    if mutated:
        notes_mod.save_notes(notes_full, doc)
    mtime = notes_full.stat().st_mtime

    def _extract_reason(body):
        first = (body or "").split("\n", 1)[0]
        if first.startswith("未解決理由:"):
            return first[len("未解決理由:"):].strip()
        return ""

    def section_to_dict(sec, *, unresolved=False, client_resolve=False):
        d = {
            "anchor": sec.anchor,
            "snapshot": sec.snapshot,
            "body": sec.body,
        }
        if not unresolved:
            d["relocated"] = False
            if client_resolve:
                d["client_resolve"] = True
        else:
            d["reason"] = _extract_reason(sec.body) or "アンカーが解決できない"
        return d

    is_md = (kind == 'md_sentence')
    resolved_out = [section_to_dict(s, client_resolve=is_md) for s in doc.resolved]
    unresolved_out = [section_to_dict(s, unresolved=True) for s in doc.unresolved]

    return jsonify({
        "mtime": mtime,
        "kind": kind,
        "resolved": resolved_out,
        "unresolved": unresolved_out,
    })
```

- [ ] **Step 4: Run; expect PASS**

Run: `pytest tests/test_notes.py -v`

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_notes.py
git commit -m "feat(api): GET /api/notes with server-side resolution"
```

---

### Task 11: PUT /api/notes (upsert)

**Files:**
- Modify: `app.py`
- Modify: `tests/test_notes.py`

Spec section: API 詳細 → `PUT /api/notes`

- [ ] **Step 1: Write failing tests**

Append:
```python
def test_put_notes_creates_file(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("a\nb\n", encoding="utf-8")
    payload = {
        "repo": "myrepo",
        "path": "foo.py",
        "if_match_mtime": None,
        "anchor": {"kind": "lines", "start": 1, "end": 1},
        "snapshot": {"kind": "lines", "start": 1, "end": 1, "text": "a"},
        "body": "ここはこう",
    }
    resp = client.put("/api/notes", json=payload)
    assert resp.status_code == 200
    assert resp.get_json()["mtime"] is not None
    notes_text = (repo / "foo.py.notes.md").read_text(encoding="utf-8")
    assert "## L1" in notes_text
    assert "ここはこう" in notes_text


def test_put_notes_overwrites_existing(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("a\n", encoding="utf-8")
    initial = (
        "## L1\n"
        '<!--snapshot:{"kind":"lines","start":1,"end":1,"text":"a"}-->\n'
        "old body\n"
    )
    notes_path = repo / "foo.py.notes.md"
    notes_path.write_text(initial, encoding="utf-8")
    mtime = notes_path.stat().st_mtime
    payload = {
        "repo": "myrepo",
        "path": "foo.py",
        "if_match_mtime": mtime,
        "anchor": {"kind": "lines", "start": 1, "end": 1},
        "snapshot": {"kind": "lines", "start": 1, "end": 1, "text": "a"},
        "body": "new body",
    }
    resp = client.put("/api/notes", json=payload)
    assert resp.status_code == 200
    assert "new body" in notes_path.read_text(encoding="utf-8")
    assert "old body" not in notes_path.read_text(encoding="utf-8")


def test_put_notes_mtime_conflict(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("a\n", encoding="utf-8")
    notes_path = repo / "foo.py.notes.md"
    notes_path.write_text("## L1\nbody\n", encoding="utf-8")
    payload = {
        "repo": "myrepo",
        "path": "foo.py",
        "if_match_mtime": 0.0,  # stale
        "anchor": {"kind": "lines", "start": 1, "end": 1},
        "snapshot": None,
        "body": "x",
    }
    resp = client.put("/api/notes", json=payload)
    assert resp.status_code == 409


def test_put_notes_rejects_huge_snapshot(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("a\n", encoding="utf-8")
    huge = "x" * (50 * 1024 + 1)
    payload = {
        "repo": "myrepo", "path": "foo.py", "if_match_mtime": None,
        "anchor": {"kind": "lines", "start": 1, "end": 1},
        "snapshot": {"kind": "lines", "start": 1, "end": 1, "text": huge},
        "body": "x",
    }
    resp = client.put("/api/notes", json=payload)
    assert resp.status_code == 400
```

- [ ] **Step 2: Run; expect failures**

- [ ] **Step 3: Implement**

Add to `app.py`:
```python
SNAPSHOT_TEXT_LIMIT = 50 * 1024  # 50 KB


def _validate_anchor(a):
    if not isinstance(a, dict) or "kind" not in a:
        return False
    k = a["kind"]
    if k == "lines":
        return all(isinstance(a.get(x), int) for x in ("start", "end")) and a["start"] >= 1 and a["end"] >= a["start"]
    if k == "md_sentence":
        return isinstance(a.get("index"), int) and a["index"] >= 0
    if k == "srt":
        return all(isinstance(a.get(x), int) for x in ("start_ms", "end_ms"))
    return False


def _validate_snapshot(s):
    if s is None:
        return True
    if not isinstance(s, dict):
        return False
    if isinstance(s.get("text"), str) and len(s["text"]) > SNAPSHOT_TEXT_LIMIT:
        return False
    return True


def _check_mtime(notes_full: Path, expected):
    actual = notes_full.stat().st_mtime if notes_full.is_file() else None
    if expected is None:
        return actual is None
    if actual is None:
        return False
    return abs(actual - float(expected)) < 1e-6


@app.route("/api/notes", methods=["PUT"])
def notes_put():
    data = request.get_json(silent=True) or {}
    name = data.get("repo", "")
    path = data.get("path", "")
    anchor = data.get("anchor")
    snapshot = data.get("snapshot")
    body = data.get("body", "")
    if_match = data.get("if_match_mtime", None)
    if not isinstance(body, str):
        abort(400)
    if not _validate_anchor(anchor) or not _validate_snapshot(snapshot):
        abort(400)
    repo_path = valid_repo(name)
    if not path or ".." in path or path.endswith(NOTES_SUFFIX):
        abort(400)
    target_full = (repo_path / path).resolve()
    if not str(target_full).startswith(str(repo_path.resolve())):
        abort(403)
    notes_full = target_full.parent / (target_full.name + NOTES_SUFFIX)

    if not _check_mtime(notes_full, if_match):
        abort(409)

    doc = notes_mod.load_notes(notes_full) if notes_full.is_file() else notes_mod.NotesDoc(
        title=f"Notes for {target_full.name}"
    )
    if doc.title is None:
        doc.title = f"Notes for {target_full.name}"

    section = notes_mod.NotesSection(anchor=anchor, snapshot=snapshot, body=body)
    notes_mod.upsert_section(doc, section)
    notes_mod.save_notes(notes_full, doc)

    return jsonify({"mtime": notes_full.stat().st_mtime})
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_notes.py
git commit -m "feat(api): PUT /api/notes (upsert)"
```

---

### Task 12: DELETE /api/notes

**Files:**
- Modify: `app.py`
- Modify: `tests/test_notes.py`

Spec section: API 詳細 → `DELETE /api/notes`

- [ ] **Step 1: Write failing tests**

Append:
```python
def test_delete_notes_removes_section(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("a\nb\n", encoding="utf-8")
    notes_path = repo / "foo.py.notes.md"
    initial = (
        "## L1\nfirst\n"
        "## L2\nsecond\n"
    )
    notes_path.write_text(initial, encoding="utf-8")
    payload = {
        "repo": "myrepo", "path": "foo.py",
        "if_match_mtime": notes_path.stat().st_mtime,
        "anchor": {"kind": "lines", "start": 1, "end": 1},
    }
    resp = client.delete("/api/notes", json=payload)
    assert resp.status_code == 200
    text = notes_path.read_text(encoding="utf-8")
    assert "first" not in text
    assert "second" in text


def test_delete_last_section_removes_file(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("a\n", encoding="utf-8")
    notes_path = repo / "foo.py.notes.md"
    notes_path.write_text("## L1\nbody\n", encoding="utf-8")
    payload = {
        "repo": "myrepo", "path": "foo.py",
        "if_match_mtime": notes_path.stat().st_mtime,
        "anchor": {"kind": "lines", "start": 1, "end": 1},
    }
    resp = client.delete("/api/notes", json=payload)
    assert resp.status_code == 200
    assert resp.get_json()["mtime"] is None
    assert not notes_path.exists()


def test_delete_notes_mtime_conflict(app_client):
    client, repo = app_client
    (repo / "foo.py").write_text("a\n", encoding="utf-8")
    notes_path = repo / "foo.py.notes.md"
    notes_path.write_text("## L1\nbody\n", encoding="utf-8")
    payload = {
        "repo": "myrepo", "path": "foo.py",
        "if_match_mtime": 0.0,
        "anchor": {"kind": "lines", "start": 1, "end": 1},
    }
    resp = client.delete("/api/notes", json=payload)
    assert resp.status_code == 409
```

- [ ] **Step 2: Run; expect failures**

- [ ] **Step 3: Implement**

Add to `app.py`:
```python
@app.route("/api/notes", methods=["DELETE"])
def notes_delete():
    data = request.get_json(silent=True) or {}
    name = data.get("repo", "")
    path = data.get("path", "")
    anchor = data.get("anchor")
    if_match = data.get("if_match_mtime", None)
    if not _validate_anchor(anchor):
        abort(400)
    repo_path = valid_repo(name)
    if not path or ".." in path or path.endswith(NOTES_SUFFIX):
        abort(400)
    target_full = (repo_path / path).resolve()
    if not str(target_full).startswith(str(repo_path.resolve())):
        abort(403)
    notes_full = target_full.parent / (target_full.name + NOTES_SUFFIX)
    if not notes_full.is_file():
        return jsonify({"mtime": None})
    if not _check_mtime(notes_full, if_match):
        abort(409)
    doc = notes_mod.load_notes(notes_full)
    notes_mod.delete_section(doc, anchor)
    if not doc.resolved and not doc.unresolved:
        try:
            notes_full.unlink()
        except OSError:
            pass
        return jsonify({"mtime": None})
    notes_mod.save_notes(notes_full, doc)
    return jsonify({"mtime": notes_full.stat().st_mtime})
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_notes.py
git commit -m "feat(api): DELETE /api/notes"
```

---

### Task 13: POST /api/notes/relocate (MD)

**Files:**
- Modify: `app.py`
- Modify: `tests/test_notes.py`

Spec section: API 詳細 → `POST /api/notes/relocate`

- [ ] **Step 1: Write failing tests**

Append:
```python
def test_relocate_md_section(app_client):
    client, repo = app_client
    (repo / "doc.md").write_text("hello\n", encoding="utf-8")
    notes_path = repo / "doc.md.notes.md"
    initial = (
        "## S5 \"old text\"\n"
        '<!--snapshot:{"kind":"md_sentence","index":5,"text":"hello"}-->\n'
        "メモ\n"
    )
    notes_path.write_text(initial, encoding="utf-8")
    payload = {
        "repo": "myrepo", "path": "doc.md",
        "if_match_mtime": notes_path.stat().st_mtime,
        "old_anchor": {"kind": "md_sentence", "index": 5},
        "new_anchor": {"kind": "md_sentence", "index": 3},
        "new_heading_text": "hello",
    }
    resp = client.post("/api/notes/relocate", json=payload)
    assert resp.status_code == 200
    text = notes_path.read_text(encoding="utf-8")
    assert "## S3 \"hello\"" in text
    assert "S5" not in text
    assert "メモ" in text


def test_relocate_section_not_found(app_client):
    client, repo = app_client
    (repo / "doc.md").write_text("x\n", encoding="utf-8")
    notes_path = repo / "doc.md.notes.md"
    notes_path.write_text("## S1\nbody\n", encoding="utf-8")
    payload = {
        "repo": "myrepo", "path": "doc.md",
        "if_match_mtime": notes_path.stat().st_mtime,
        "old_anchor": {"kind": "md_sentence", "index": 99},
        "new_anchor": {"kind": "md_sentence", "index": 1},
        "new_heading_text": "x",
    }
    resp = client.post("/api/notes/relocate", json=payload)
    assert resp.status_code == 404
```

- [ ] **Step 2: Run; expect failures**

- [ ] **Step 3: Implement**

Add to `app.py`:
```python
@app.route("/api/notes/relocate", methods=["POST"])
def notes_relocate():
    data = request.get_json(silent=True) or {}
    name = data.get("repo", "")
    path = data.get("path", "")
    old_anchor = data.get("old_anchor")
    new_anchor = data.get("new_anchor")
    new_heading_text = data.get("new_heading_text", "")
    if_match = data.get("if_match_mtime", None)
    if not _validate_anchor(old_anchor) or not _validate_anchor(new_anchor):
        abort(400)
    if old_anchor["kind"] != "md_sentence" or new_anchor["kind"] != "md_sentence":
        abort(400)
    if not isinstance(new_heading_text, str):
        abort(400)
    repo_path = valid_repo(name)
    if not path or ".." in path or path.endswith(NOTES_SUFFIX):
        abort(400)
    target_full = (repo_path / path).resolve()
    if not str(target_full).startswith(str(repo_path.resolve())):
        abort(403)
    notes_full = target_full.parent / (target_full.name + NOTES_SUFFIX)
    if not notes_full.is_file() or not _check_mtime(notes_full, if_match):
        abort(409 if notes_full.is_file() else 404)

    doc = notes_mod.load_notes(notes_full)
    new_anchor_full = dict(new_anchor)
    new_anchor_full["heading_text"] = new_heading_text
    target_key = notes_mod._anchor_key(old_anchor)
    found = False
    for sec in doc.resolved:
        if notes_mod._anchor_key(sec.anchor) == target_key:
            sec.anchor = new_anchor_full
            found = True
            break
    if not found:
        abort(404)
    notes_mod.save_notes(notes_full, doc)
    return jsonify({"mtime": notes_full.stat().st_mtime})
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_notes.py
git commit -m "feat(api): POST /api/notes/relocate"
```

---

### Task 14: GET /api/notes/index

**Files:**
- Modify: `app.py`
- Modify: `tests/test_notes.py`

Spec section: API 詳細 → `GET /api/notes/index`

- [ ] **Step 1: Write failing tests**

Append:
```python
def test_notes_index_empty(app_client):
    client, repo = app_client
    resp = client.get("/api/notes/index?repo=myrepo&path=")
    assert resp.status_code == 200
    assert resp.get_json() == {"files": {}}


def test_notes_index_counts_sections(app_client):
    client, repo = app_client
    (repo / "a.py.notes.md").write_text(
        "## L1\nx\n## L2\ny\n", encoding="utf-8")
    (repo / "b.py.notes.md").write_text(
        "## L1\nx\n## Unresolved\n### L99\nz\n", encoding="utf-8")
    (repo / "sub").mkdir()
    (repo / "sub" / "c.py.notes.md").write_text("## L1\nx\n", encoding="utf-8")
    resp = client.get("/api/notes/index?repo=myrepo&path=")
    body = resp.get_json()
    assert body["files"] == {"a.py": 2, "b.py": 2}  # only top-level
    resp2 = client.get("/api/notes/index?repo=myrepo&path=sub")
    assert resp2.get_json()["files"] == {"c.py": 1}
```

- [ ] **Step 2: Run; expect failures**

- [ ] **Step 3: Implement**

Add to `app.py`:
```python
@app.route("/api/notes/index")
def notes_index():
    name = request.args.get("repo", "")
    path = request.args.get("path", "") or ""
    repo_path = valid_repo(name)
    if ".." in path:
        abort(400)
    base_full = (repo_path / path).resolve() if path else repo_path
    if not str(base_full).startswith(str(repo_path.resolve())):
        abort(403)
    if not base_full.is_dir():
        return jsonify({"files": {}})
    out = {}
    for entry in base_full.iterdir():
        if not entry.is_file():
            continue
        if not entry.name.endswith(NOTES_SUFFIX):
            continue
        target_name = entry.name[: -len(NOTES_SUFFIX)]
        try:
            doc = notes_mod.load_notes(entry)
        except OSError:
            continue
        count = len(doc.resolved) + len(doc.unresolved)
        if count > 0:
            out[target_name] = count
    return jsonify({"files": out})
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_notes.py
git commit -m "feat(api): GET /api/notes/index"
```

---

## Phase 3: Frontend

All Phase 3 tasks modify `templates/index.html` and `static/style.css`. There is no frontend test framework — manual smoke testing per task. Commit after each task and verify in the browser.

### Task 15: CSS for markers, modal, badges, unresolved panel

**Files:**
- Modify: `static/style.css`

- [ ] **Step 1: Append note-feature styles**

Append to `static/style.css`:
```css
/* === File notes feature === */
.note-marker {
  display: inline-block;
  margin-left: 6px;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  vertical-align: middle;
  user-select: none;
  opacity: 0.85;
}
.note-marker:hover { opacity: 1; }
.note-marker.has-note { color: #f0c04a; }
.note-marker.add-note { color: #6e7681; opacity: 0; }
.code-line:hover .note-marker.add-note,
.bm-target:hover .note-marker.add-note,
.srt-cue:hover .note-marker.add-note { opacity: 0.6; }

.notes-badge {
  display: inline-block;
  margin-left: 4px;
  font-size: 10px;
  color: #f0c04a;
  background: rgba(240, 192, 74, 0.12);
  border: 1px solid rgba(240, 192, 74, 0.4);
  border-radius: 3px;
  padding: 0 4px;
  line-height: 14px;
  vertical-align: middle;
}

.note-modal-backdrop {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.note-modal {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  width: min(640px, 90vw);
  max-height: 80vh;
  display: flex; flex-direction: column;
  padding: 16px;
  gap: 8px;
}
.note-modal h3 { margin: 0; font-size: 14px; color: #c9d1d9; }
.note-modal-anchor {
  font-family: monospace; font-size: 11px; color: #8b949e;
  background: #0d1117; padding: 4px 6px; border-radius: 3px;
}
.note-modal textarea {
  flex: 1; min-height: 200px; font-family: monospace; font-size: 13px;
  background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
  border-radius: 3px; padding: 8px; resize: vertical;
}
.note-modal-actions { display: flex; gap: 8px; justify-content: flex-end; }
.note-modal-actions button {
  padding: 4px 12px; border-radius: 3px; border: 1px solid #30363d;
  background: #21262d; color: #c9d1d9; cursor: pointer;
}
.note-modal-actions button.btn-save { background: #238636; border-color: #2ea043; }
.note-modal-actions button.btn-delete { background: #da3633; border-color: #f85149; }

.unresolved-panel {
  margin-top: 16px;
  padding: 8px;
  border: 1px solid #30363d;
  border-radius: 4px;
  background: #161b22;
}
.unresolved-panel summary {
  cursor: pointer; color: #f0c04a; font-weight: 600; font-size: 13px;
}
.unresolved-item {
  margin-top: 8px; padding: 8px; background: #0d1117;
  border-left: 3px solid #f0c04a; border-radius: 3px;
}
.unresolved-item .anchor {
  font-family: monospace; font-size: 11px; color: #8b949e;
}
.unresolved-item .reason { font-size: 11px; color: #f85149; margin-top: 2px; }
.unresolved-item .body { margin-top: 6px; white-space: pre-wrap; }
.unresolved-item .actions { margin-top: 6px; display: flex; gap: 6px; }
```

- [ ] **Step 2: Restart service and verify CSS loads**

Run: `powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"`
Open the app in browser. No visual change yet — just confirm no CSS parse errors in DevTools console.

- [ ] **Step 3: Commit**

```bash
git add static/style.css
git commit -m "feat(notes): CSS for markers, modal, panel, badges"
```

---

### Task 16: Frontend `notes` data fetcher and central state

**Files:**
- Modify: `templates/index.html`

Add a self-contained module-like block of JS near the bottom of the inline `<script>` (before existing helpers like `splitMdIntoSentences`). This holds:
- `notesState` (current file's mtime, resolved sections, unresolved sections)
- `fetchNotes(path)` — calls `GET /api/notes`, populates `notesState`
- `putNote(...)`, `deleteNote(...)`, `relocateNote(...)` — wrappers with mtime conflict retry

- [ ] **Step 1: Insert state object and helpers**

Find a good insertion point near the end of the inline `<script>` (above the closing `</script>` or just before unrelated existing helpers). Add:
```javascript
// === File notes feature ===
let notesState = { path: null, mtime: null, kind: null, resolved: [], unresolved: [] };

async function fetchNotes(path) {
  const url = `/api/notes?repo=${encodeURIComponent(currentRepo)}&path=${encodeURIComponent(path)}`;
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    notesState = {
      path,
      mtime: data.mtime,
      kind: data.kind,
      resolved: data.resolved || [],
      unresolved: data.unresolved || [],
    };
    return notesState;
  } catch (e) {
    notesState = { path, mtime: null, kind: null, resolved: [], unresolved: [] };
    console.warn('fetchNotes failed', e);
    return notesState;
  }
}

async function putNote(anchor, snapshot, body) {
  const payload = {
    repo: currentRepo, path: notesState.path,
    if_match_mtime: notesState.mtime,
    anchor, snapshot, body,
  };
  const resp = await fetch('/api/notes', {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  if (resp.status === 409) {
    alert('他で更新されたためメモを保存できませんでした。再読込してやり直してください。');
    return null;
  }
  if (!resp.ok) {
    alert('メモの保存に失敗しました');
    return null;
  }
  const data = await resp.json();
  notesState.mtime = data.mtime;
  return data;
}

async function deleteNote(anchor) {
  const payload = {
    repo: currentRepo, path: notesState.path,
    if_match_mtime: notesState.mtime,
    anchor,
  };
  const resp = await fetch('/api/notes', {
    method: 'DELETE', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  if (resp.status === 409) {
    alert('他で更新されたためメモを削除できませんでした。');
    return null;
  }
  if (!resp.ok) {
    alert('メモの削除に失敗しました');
    return null;
  }
  const data = await resp.json();
  notesState.mtime = data.mtime;
  return data;
}

async function relocateNote(oldAnchor, newAnchor, headingText) {
  const payload = {
    repo: currentRepo, path: notesState.path,
    if_match_mtime: notesState.mtime,
    old_anchor: oldAnchor, new_anchor: newAnchor, new_heading_text: headingText,
  };
  const resp = await fetch('/api/notes/relocate', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  if (!resp.ok) return null;
  const data = await resp.json();
  notesState.mtime = data.mtime;
  return data;
}

function findResolvedNote(anchorMatch) {
  return notesState.resolved.find(s => anchorMatch(s.anchor));
}
```

- [ ] **Step 2: Manual smoke**

Restart service. Open DevTools console. Type:
```javascript
fetchNotes('app.py').then(s => console.log(s));
```
Expected: object with `mtime: null`, empty arrays for a file without `.notes.md`.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat(notes): frontend fetch/put/delete/relocate helpers"
```

---

### Task 17: Marker rendering for text/code

**Files:**
- Modify: `templates/index.html`

Locate `showBlob` text/code branch (look for the `else` block that renders `.code-line` rows after the SRT branch). After rendering, call `fetchNotes(path)` and decorate each `.code-line` with a 💬 marker on the right.

- [ ] **Step 1: Find text rendering location**

Open `templates/index.html` and look near `## L` in line 1080 area for the text-rendering branch. The structure is approximately:
```javascript
} else {
  // text/code rendering with .code-line rows ...
}
```

- [ ] **Step 2: Add `decorateTextNotes(blobView, path)` helper**

Append to the notes block in `templates/index.html`:
```javascript
function decorateTextNotes(blobView, path) {
  const linesByStart = new Map();
  for (const sec of notesState.resolved) {
    if (sec.anchor.kind !== 'lines') continue;
    linesByStart.set(sec.anchor.start, sec);
  }
  blobView.querySelectorAll('.code-line[data-bm-line]').forEach(line => {
    const lineNo = Number(line.getAttribute('data-bm-line'));
    const sec = linesByStart.get(lineNo);
    const marker = document.createElement('span');
    marker.className = 'note-marker ' + (sec ? 'has-note' : 'add-note');
    marker.textContent = '💬';
    marker.title = sec ? '編集' : 'メモを追加';
    marker.onclick = (e) => {
      e.stopPropagation();
      if (sec) {
        openNoteModal({ kind: 'lines', existing: sec });
      } else {
        const anchor = { kind: 'lines', start: lineNo, end: lineNo };
        const snapshot = { kind: 'lines', start: lineNo, end: lineNo, text: line.textContent };
        openNoteModal({ kind: 'lines', anchor, snapshot });
      }
    };
    line.appendChild(marker);
  });
}
```

- [ ] **Step 3: Wire into `showBlob` text branch**

Find the text-rendering branch in `showBlob`. After it sets `blobView.innerHTML = ...`, add:
```javascript
await fetchNotes(path);
decorateTextNotes(blobView, path);
renderUnresolvedPanel(blobView);
```

The exact diff target is the closing brace of the `else` text/code branch in `showBlob`. Add the three lines just before that brace.

- [ ] **Step 4: Manual smoke**

Stub `openNoteModal` and `renderUnresolvedPanel` for now:
```javascript
function openNoteModal(opts) { console.log('openNoteModal', opts); }
function renderUnresolvedPanel(blobView) {}
```
Restart service. Open a code file. 💬 should appear on hover near each line. Click it — see console log.

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "feat(notes): text/code marker rendering"
```

---

### Task 18: Marker rendering for SRT

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add `decorateSrtNotes(blobView, cues)` helper**

Append to the notes JS block:
```javascript
function srtMsToTime(ms) {
  const total = Math.round(ms);
  const h = String(Math.floor(total / 3600000)).padStart(2, '0');
  const m = String(Math.floor((total % 3600000) / 60000)).padStart(2, '0');
  const s = String(Math.floor((total % 60000) / 1000)).padStart(2, '0');
  const r = String(total % 1000).padStart(3, '0');
  return `${h}:${m}:${s},${r}`;
}

function srtTimeToMs(s) {
  const m = /^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$/.exec(s.trim());
  if (!m) return null;
  return ((+m[1] * 60 + +m[2]) * 60 + +m[3]) * 1000 + +m[4];
}

function decorateSrtNotes(blobView, cues) {
  const byKey = new Map();
  for (const sec of notesState.resolved) {
    if (sec.anchor.kind !== 'srt') continue;
    byKey.set(`${sec.anchor.start_ms}-${sec.anchor.end_ms}`, sec);
  }
  blobView.querySelectorAll('.srt-cue').forEach(cueEl => {
    const idx = Number(cueEl.getAttribute('data-bm-idx'));
    const cue = cues[idx];
    if (!cue) return;
    const startMs = srtTimeToMs(cue.start);
    const endMs = srtTimeToMs(cue.end);
    if (startMs == null || endMs == null) return;
    const key = `${startMs}-${endMs}`;
    const sec = byKey.get(key);
    const marker = document.createElement('span');
    marker.className = 'note-marker ' + (sec ? 'has-note' : 'add-note');
    marker.textContent = '💬';
    marker.title = sec ? '編集' : 'メモを追加';
    marker.onclick = (e) => {
      e.stopPropagation();
      if (sec) {
        openNoteModal({ kind: 'srt', existing: sec });
      } else {
        const anchor = { kind: 'srt', start_ms: startMs, end_ms: endMs };
        const snapshot = {
          kind: 'srt', start_ms: startMs, end_ms: endMs,
          cue_index: cue.index ? Number(cue.index) : (idx + 1),
          text: cue.text,
        };
        openNoteModal({ kind: 'srt', anchor, snapshot });
      }
    };
    cueEl.querySelector('.srt-meta')?.appendChild(marker);
  });
}
```

- [ ] **Step 2: Wire into SRT branch in `showBlob`**

Find the `.srt` branch (where `cardsHtml` is built and `blobView.innerHTML = ...` happens with `srt-container`). After it, add:
```javascript
await fetchNotes(path);
decorateSrtNotes(blobView, cues);
renderUnresolvedPanel(blobView);
```

- [ ] **Step 3: Manual smoke**

Restart service. Open an `.srt` file. 💬 markers should appear in each cue's metadata row.

- [ ] **Step 4: Commit**

```bash
git add templates/index.html
git commit -m "feat(notes): SRT marker rendering"
```

---

### Task 19: Marker rendering for MD with client-side resolve

**Files:**
- Modify: `templates/index.html`

MD requires resolving by index first then by `snapshot.text`. After matching, optionally call `relocateNote` to write back the new index.

- [ ] **Step 1: Add MD decoration helper**

Append:
```javascript
function decorateMdNotes(blobView) {
  const sentences = blobView.querySelectorAll('[data-bm-idx]');
  // Build a text -> nodes map
  const indexByText = new Map();
  sentences.forEach(node => {
    const idx = Number(node.getAttribute('data-bm-idx'));
    const text = node.textContent.trim();
    if (!indexByText.has(text)) indexByText.set(text, []);
    indexByText.get(text).push({ idx, node });
  });

  const sectionsForRelocate = [];
  for (const sec of notesState.resolved) {
    if (sec.anchor.kind !== 'md_sentence') continue;
    let resolvedNode = null;
    let resolvedIdx = null;
    let relocated = false;

    // Try original index first
    const origNode = blobView.querySelector(`[data-bm-idx="${sec.anchor.index}"]`);
    if (origNode && sec.snapshot && origNode.textContent.trim() === sec.snapshot.text.trim()) {
      resolvedNode = origNode;
      resolvedIdx = sec.anchor.index;
    } else if (sec.snapshot) {
      // Fallback: find by text
      const candidates = indexByText.get(sec.snapshot.text.trim()) || [];
      if (candidates.length === 0) {
        notesState.unresolved.push({ ...sec, reason: 'MD: 同一の文が見つからなかった' });
        continue;
      }
      const best = candidates.reduce((a, b) =>
        Math.abs(a.idx - sec.anchor.index) <= Math.abs(b.idx - sec.anchor.index) ? a : b
      );
      resolvedNode = best.node;
      resolvedIdx = best.idx;
      relocated = (resolvedIdx !== sec.anchor.index);
    } else if (origNode) {
      resolvedNode = origNode;
      resolvedIdx = sec.anchor.index;
    } else {
      notesState.unresolved.push({ ...sec, reason: 'MD: index がファイル外でスナップショットなし' });
      continue;
    }

    if (relocated) {
      sectionsForRelocate.push({
        old_anchor: sec.anchor,
        new_anchor: { kind: 'md_sentence', index: resolvedIdx },
        heading_text: (sec.snapshot?.text || '').slice(0, 30),
      });
    }
    // Update in-memory anchor so PUT/DELETE work later
    sec.anchor = { ...sec.anchor, index: resolvedIdx };

    const marker = document.createElement('span');
    marker.className = 'note-marker has-note';
    marker.textContent = '💬';
    marker.title = '編集';
    marker.onclick = (e) => {
      e.stopPropagation();
      openNoteModal({ kind: 'md_sentence', existing: sec });
    };
    resolvedNode.appendChild(marker);
  }

  // Add "add" markers to all sentences that don't already have a note
  sentences.forEach(node => {
    if (node.querySelector('.note-marker')) return;
    const idx = Number(node.getAttribute('data-bm-idx'));
    const marker = document.createElement('span');
    marker.className = 'note-marker add-note';
    marker.textContent = '💬';
    marker.title = 'メモを追加';
    marker.onclick = (e) => {
      e.stopPropagation();
      const text = node.textContent.trim();
      const anchor = { kind: 'md_sentence', index: idx };
      const snapshot = { kind: 'md_sentence', index: idx, text };
      openNoteModal({ kind: 'md_sentence', anchor, snapshot });
    };
    node.appendChild(marker);
  });

  // Background relocate writes
  for (const r of sectionsForRelocate) {
    relocateNote(r.old_anchor, r.new_anchor, r.heading_text).catch(() => {});
  }
}
```

- [ ] **Step 2: Wire into MD branch in `showBlob`**

After the existing `splitMdIntoSentences(mdBody);` line in `showBlob`'s `.md` branch, append:
```javascript
await fetchNotes(path);
decorateMdNotes(mdBody);
renderUnresolvedPanel(blobView);
```

Place these lines after the `.md` branch's existing bookmark setup so they run last.

- [ ] **Step 3: Manual smoke**

Restart service. Open an MD file. Hover over a sentence — 💬 appears. Click — modal stub fires.

- [ ] **Step 4: Commit**

```bash
git add templates/index.html
git commit -m "feat(notes): MD marker rendering with client-side resolve"
```

---

### Task 20: Note modal (create/edit/delete)

**Files:**
- Modify: `templates/index.html`

Replace the stub `openNoteModal` with a real modal.

- [ ] **Step 1: Implement modal**

Replace the stub with:
```javascript
function openNoteModal(opts) {
  // opts = { kind, existing } or { kind, anchor, snapshot }
  const isEdit = !!opts.existing;
  const anchor = isEdit ? opts.existing.anchor : opts.anchor;
  const snapshot = isEdit ? opts.existing.snapshot : opts.snapshot;
  const initialBody = isEdit ? opts.existing.body : '';
  const anchorLabel = formatAnchorLabel(anchor);

  const backdrop = document.createElement('div');
  backdrop.className = 'note-modal-backdrop';
  backdrop.innerHTML = `
    <div class="note-modal" onclick="event.stopPropagation()">
      <h3>${isEdit ? 'メモを編集' : 'メモを追加'}</h3>
      <div class="note-modal-anchor">${esc(anchorLabel)}</div>
      <textarea class="note-body"></textarea>
      <div class="note-modal-actions">
        ${isEdit ? '<button class="btn-delete">削除</button>' : ''}
        <button class="btn-cancel">キャンセル</button>
        <button class="btn-save">保存</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  const textarea = backdrop.querySelector('.note-body');
  textarea.value = initialBody;
  textarea.focus();

  const close = () => backdrop.remove();
  backdrop.onclick = close;
  backdrop.querySelector('.btn-cancel').onclick = close;
  backdrop.querySelector('.btn-save').onclick = async () => {
    const body = textarea.value;
    const result = await putNote(anchor, snapshot, body);
    if (result) {
      close();
      await reloadCurrentBlob();
    }
  };
  if (isEdit) {
    backdrop.querySelector('.btn-delete').onclick = async () => {
      if (!confirm('このメモを削除しますか？')) return;
      const result = await deleteNote(anchor);
      if (result !== null) {
        close();
        await reloadCurrentBlob();
      }
    };
  }
}

function formatAnchorLabel(a) {
  if (a.kind === 'lines') {
    return a.start === a.end ? `L${a.start}` : `L${a.start}-${a.end}`;
  }
  if (a.kind === 'md_sentence') return `S${a.index}`;
  if (a.kind === 'srt') return `${srtMsToTime(a.start_ms)} --> ${srtMsToTime(a.end_ms)}`;
  return JSON.stringify(a);
}

async function reloadCurrentBlob() {
  if (notesState.path) {
    await showBlob(notesState.path);
  }
}
```

- [ ] **Step 2: Manual smoke**

Restart service. Open a code file, click + 💬 on a line, type "test メモ", save. Verify `<file>.py.notes.md` is created with the section. Reload — marker shows 💬 (yellow). Click it, edit, save, verify update. Click delete, confirm, verify file removed.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat(notes): create/edit/delete modal"
```

---

### Task 21: Unresolved memo panel

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Implement `renderUnresolvedPanel`**

Replace the stub with:
```javascript
function renderUnresolvedPanel(blobView) {
  // Remove existing panel if any
  blobView.querySelectorAll('.unresolved-panel').forEach(p => p.remove());
  if (!notesState.unresolved.length) return;

  const panel = document.createElement('details');
  panel.className = 'unresolved-panel';
  panel.open = true;
  const summary = document.createElement('summary');
  summary.textContent = `未解決メモ (${notesState.unresolved.length})`;
  panel.appendChild(summary);

  for (const sec of notesState.unresolved) {
    const item = document.createElement('div');
    item.className = 'unresolved-item';
    const anchorLabel = formatAnchorLabel(sec.anchor);
    const reason = sec.reason || '理由不明';
    item.innerHTML = `
      <div class="anchor">${esc(anchorLabel)}</div>
      <div class="reason">${esc(reason)}</div>
      <div class="body">${esc(sec.body || '')}</div>
      <div class="actions">
        <button class="btn-delete-unresolved">削除</button>
      </div>`;
    item.querySelector('.btn-delete-unresolved').onclick = async () => {
      if (!confirm('この未解決メモを削除しますか？')) return;
      await deleteNote(sec.anchor);
      await reloadCurrentBlob();
    };
    panel.appendChild(item);
  }
  blobView.appendChild(panel);
}
```

- [ ] **Step 2: Manual smoke**

Create a code file `foo.py` with 5 lines. Add a memo on `L10` (use a script that PUTs to a non-existent line — easier: add memo on L5, then truncate the file to 2 lines, reload). The unresolved panel should show "未解決メモ (1)" with the section.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat(notes): unresolved memo panel"
```

---

### Task 22: File list badges

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Modify `renderFiles` to fetch and apply notes index**

Find the existing `renderFiles` function (around line 393). After it builds the entries HTML, add a fetch + decorate step:
```javascript
async function decorateNotesBadges() {
  const url = `/api/notes/index?repo=${encodeURIComponent(currentRepo)}&path=${encodeURIComponent(currentPath)}`;
  try {
    const resp = await fetch(url);
    if (!resp.ok) return;
    const data = await resp.json();
    const counts = data.files || {};
    document.querySelectorAll('#content .list-row').forEach(row => {
      const nameSpan = row.querySelector('span:nth-child(2)');
      if (!nameSpan) return;
      const name = nameSpan.textContent;
      const count = counts[name];
      if (count) {
        const badge = document.createElement('span');
        badge.className = 'notes-badge';
        badge.textContent = `💬${count}`;
        nameSpan.appendChild(badge);
      }
    });
  } catch (e) {
    console.warn('decorateNotesBadges failed', e);
  }
}
```

Modify `renderFiles` to call it at the end:
```javascript
// at the end of renderFiles, after content.innerHTML = `...`;
decorateNotesBadges();
```

- [ ] **Step 2: Manual smoke**

Add a memo to a file. Re-open the file list. The file row should show `💬1` next to the name. Files without memos: no badge.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat(notes): file list badges"
```

---

## Phase 4: End-to-end verification

### Task 23: Manual integration test pass

**Files:** None (verification only)

- [ ] **Step 1: Restart service**

```bash
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

- [ ] **Step 2: Walk through spec test plan**

Execute the spec's manual integration tests (spec section: テスト計画 → 統合テスト) one by one:

1. New memo on Python file → `.notes.md` created, badge appears
2. Edit memo → updated
3. Delete memo → section gone, file deleted when last
4. Add line above existing memo → auto-relocation, heading updated
5. Delete the snapshot text from file → unresolved panel
6. SRT memo → tamper timecode → unresolved
7. MD memo → reorder sentences → fallback resolution + relocate
8. Two browser tabs same file → second tab gets 409 alert
9. Manually edit `.notes.md` to break JSON → server returns best-effort data
10. Try `path=../etc/passwd` via curl → 403
11. Submit 60KB snapshot via curl PUT → 400

Note any failures and file follow-up tasks.

- [ ] **Step 3: If all pass, commit**

If documentation updates emerge, e.g. README mention:
```bash
git add <files>
git commit -m "docs: file notes feature integration verified"
```

If no doc changes, no commit needed.

---

## Notes on running tests

- Run all backend tests: `pytest`
- Run a specific task's tests: `pytest tests/test_notes.py::test_name -v`
- Frontend has no automated tests; rely on manual smoke after each frontend task and the Phase 4 walk-through.
- After modifying `app.py`, restart the Windows service for changes to take effect (CLAUDE.md):
  `powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"`
