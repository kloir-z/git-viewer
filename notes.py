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
