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
