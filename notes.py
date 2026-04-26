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
