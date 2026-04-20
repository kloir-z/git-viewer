import json
import mimetypes
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, send_file

app = Flask(__name__)

CONFIG_FILE = Path(__file__).parent / "config.local.json"


def load_code_dir() -> Path:
    env_value = os.environ.get("GIT_VIEWER_CODE_DIR")
    if env_value:
        return Path(env_value)
    if CONFIG_FILE.is_file():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if config.get("code_dir"):
                return Path(config["code_dir"])
        except (json.JSONDecodeError, OSError):
            pass
    return Path("/home/user/code")


CODE_DIR = load_code_dir()
FAVORITES_FILE = Path(__file__).parent / "favorites.json"


def read_favorites() -> list:
    if FAVORITES_FILE.is_file():
        try:
            return json.loads(FAVORITES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def write_favorites(favs: list):
    FAVORITES_FILE.write_text(json.dumps(favs, ensure_ascii=False), encoding="utf-8")


BOOKMARKS_FILE = Path(__file__).parent / "bookmarks.json"


def read_bookmarks() -> dict:
    if BOOKMARKS_FILE.is_file():
        try:
            return json.loads(BOOKMARKS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def write_bookmarks(bms: dict):
    BOOKMARKS_FILE.write_text(json.dumps(bms, ensure_ascii=False), encoding="utf-8")


def valid_repo(name: str) -> Path:
    """Validate repo name and return path. Abort 404 if not a git repo.

    Accepts 'repo' (direct child) or 'category/repo' (two-level).
    """
    if "\\" in name or name.startswith(".") or ".." in name:
        abort(400)
    parts = name.split("/")
    if len(parts) > 2 or any(p.startswith(".") for p in parts):
        abort(400)
    repo_path = (CODE_DIR / name).resolve()
    if not str(repo_path).startswith(str(CODE_DIR.resolve())):
        abort(403)
    if not (repo_path / ".git").is_dir():
        abort(404)
    return repo_path


def git(repo_path: Path, *args: str, default: str = "") -> str:
    """Run a git command and return stdout. Returns default on error."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path)] + list(args),
            capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            return default
        return result.stdout.decode("utf-8", errors="replace").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return default


def get_repo_info(repo_path: Path) -> dict:
    """Gather status info for a single repo."""
    name = repo_path.name

    # One porcelain v2 call yields branch, upstream, ahead/behind, and changes.
    # On Windows, each git invocation costs ~60-80ms, so fewer calls matters.
    status_raw = git(repo_path, "status", "--porcelain=v2", "--branch")
    branch = "unknown"
    changes = 0
    has_upstream = False
    ahead = behind = 0
    for line in status_raw.splitlines():
        if line.startswith("# branch.head "):
            branch = line[len("# branch.head "):]
        elif line.startswith("# branch.upstream "):
            has_upstream = True
        elif line.startswith("# branch.ab "):
            parts = line[len("# branch.ab "):].split()
            if len(parts) == 2:
                try:
                    ahead = int(parts[0].lstrip("+"))
                    behind = int(parts[1].lstrip("-"))
                except ValueError:
                    pass
        elif line and not line.startswith("#"):
            changes += 1

    if has_upstream:
        if ahead > 0 and behind > 0:
            remote_status = f"ahead {ahead}, behind {behind}"
        elif ahead > 0:
            remote_status = f"ahead {ahead}"
        elif behind > 0:
            remote_status = f"behind {behind}"
        else:
            remote_status = "up to date"
    else:
        remote_status = "no remote"

    log_line = git(repo_path, "log", "-1", "--format=%h\t%s\t%aI")
    if log_line and "\t" in log_line:
        parts = log_line.split("\t", 2)
        latest_commit, latest_message, latest_time = parts[0], parts[1], parts[2]
    else:
        latest_commit, latest_message, latest_time = "", "", ""

    return {
        "name": name,
        "branch": branch,
        "changes": changes,
        "latest_commit": latest_commit,
        "latest_message": latest_message,
        "latest_time": latest_time,
        "remote_status": remote_status,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/check")
def check():
    """Lightweight endpoint: return HEAD hash + change count for polling."""
    repo_name = request.args.get("repo", "")
    if not repo_name:
        return jsonify({"head": "", "changes": 0})
    repo_path = valid_repo(repo_name)
    head = git(repo_path, "rev-parse", "HEAD", default="")
    status = git(repo_path, "status", "--porcelain")
    changes = len(status.splitlines()) if status else 0
    return jsonify({"head": head, "changes": changes})


@app.route("/api/info")
def info():
    """Single-repo info (same shape as one entry in /api/repos)."""
    name = request.args.get("repo", "")
    repo_path = valid_repo(name)
    data = get_repo_info(repo_path)
    if "/" in name:
        data["name"] = name
        data["category"] = name.split("/", 1)[0]
    else:
        data["category"] = ""
    return jsonify(data)


@app.route("/api/repos")
def repos():
    # Collect all repo paths first, then fetch info in parallel
    repo_entries = []  # (path, category)
    for item in sorted(CODE_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not item.is_dir():
            continue
        if (item / ".git").is_dir():
            repo_entries.append((item, ""))
        else:
            category = item.name
            for sub in sorted(item.iterdir(), key=lambda p: p.name.lower()):
                if sub.is_dir() and (sub / ".git").is_dir():
                    repo_entries.append((sub, category))

    def fetch_info(entry):
        path, category = entry
        info = get_repo_info(path)
        if category:
            info["name"] = f"{category}/{path.name}"
        info["category"] = category
        return info

    with ThreadPoolExecutor(max_workers=8) as pool:
        repo_list = list(pool.map(fetch_info, repo_entries))
    return jsonify(repo_list)


@app.route("/api/log")
def log():
    name = request.args.get("repo", "")
    limit = min(int(request.args.get("limit", "50")), 200)
    repo_path = valid_repo(name)

    raw = git(repo_path, "log", f"-{limit}",
              "--format=%h\t%s\t%aI",
              "--shortstat")

    commits = []
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if "\t" not in line:
            i += 1
            continue
        parts = line.split("\t", 2)
        entry = {
            "hash": parts[0],
            "message": parts[1],
            "time": parts[2],
            "files_changed": 0,
            "insertions": 0,
            "deletions": 0,
        }
        i += 1
        while i < len(lines) and lines[i] == "":
            i += 1
        if i < len(lines) and "file" in lines[i] and "\t" not in lines[i]:
            stat = lines[i]
            fc = re.search(r"(\d+) file", stat)
            ins = re.search(r"(\d+) insertion", stat)
            dels = re.search(r"(\d+) deletion", stat)
            entry["files_changed"] = int(fc.group(1)) if fc else 0
            entry["insertions"] = int(ins.group(1)) if ins else 0
            entry["deletions"] = int(dels.group(1)) if dels else 0
            i += 1
        commits.append(entry)

    return jsonify(commits)


@app.route("/api/diff")
def diff():
    name = request.args.get("repo", "")
    commit = request.args.get("commit", "")
    repo_path = valid_repo(name)

    file_path = request.args.get("file", "")
    if file_path and ("/" == file_path[0] or ".." in file_path):
        abort(400)

    if commit:
        if not commit.replace("-", "").isalnum() or len(commit) > 40:
            abort(400)
        parent = git(repo_path, "rev-parse", "--verify", f"{commit}^", default="")
        if parent:
            cmd = ["diff", f"{commit}^..{commit}"]
            if file_path:
                cmd += ["--", file_path]
            diff_text = git(repo_path, *cmd)
            files_raw = git(repo_path, "diff", "--name-only", f"{commit}^..{commit}")
        else:
            cmd = ["diff-tree", "-p", "--root", commit]
            if file_path:
                cmd += ["--", file_path]
            raw = git(repo_path, *cmd)
            diff_text = raw.split("\n", 1)[1] if "\n" in raw else raw
            files_raw = git(repo_path, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit)
    else:
        file_args = ["--", file_path] if file_path else []
        unstaged = git(repo_path, "diff", *file_args)
        staged = git(repo_path, "diff", "--cached", *file_args)
        diff_text = staged + ("\n" if staged and unstaged else "") + unstaged
        files_raw = git(repo_path, "diff", "--name-only") + "\n" + git(repo_path, "diff", "--name-only", "--cached")

    files = sorted(set(f for f in files_raw.splitlines() if f))

    return jsonify({"diff": diff_text, "files": files})


@app.route("/api/branches")
def branches():
    name = request.args.get("repo", "")
    repo_path = valid_repo(name)

    raw = git(repo_path, "branch", "-a", "--format=%(refname:short)\t%(HEAD)\t%(upstream:short)\t%(objectname:short)")
    result = []
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\t", 3)
        result.append({
            "name": parts[0],
            "current": parts[1].strip() == "*",
            "upstream": parts[2] if len(parts) > 2 else "",
            "hash": parts[3] if len(parts) > 3 else "",
        })
    return jsonify(result)


@app.route("/api/tree")
def tree():
    name = request.args.get("repo", "")
    path = request.args.get("path", "")
    repo_path = valid_repo(name)

    if ".." in path:
        abort(400)

    target_dir = (repo_path / path).resolve() if path else repo_path
    if not str(target_dir).startswith(str(repo_path.resolve())):
        abort(403)
    if not target_dir.is_dir():
        abort(404)

    entries = []
    for item in target_dir.iterdir():
        rel = str(item.relative_to(repo_path)).replace("\\", "/")
        entries.append({
            "name": item.name,
            "path": rel,
            "type": "tree" if item.is_dir() else "blob",
        })
    entries.sort(key=lambda e: (0 if e["type"] == "tree" else 1, e["name"].lower()))
    return jsonify(entries)


TEXT_EXTS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.sh', '.bash', '.json', '.yml', '.yaml',
    '.xml', '.html', '.css', '.toml', '.md', '.txt', '.cfg', '.ini', '.conf',
    '.env', '.service', '.timer', '.csv', '.sql', '.rb', '.go', '.rs', '.java',
    '.c', '.h', '.cpp', '.hpp', '.vue', '.svelte', '.gitignore', '.dockerignore',
    '.dockerfile', '.makefile', '',
}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico'}
PDF_EXTS = {'.pdf'}


@app.route("/api/blob")
def blob():
    name = request.args.get("repo", "")
    path = request.args.get("path", "")
    repo_path = valid_repo(name)

    if not path or ".." in path:
        abort(400)

    file_full = (repo_path / path).resolve()
    if not str(file_full).startswith(str(repo_path.resolve())):
        abort(403)
    if not file_full.is_file():
        abort(404)

    filename = path.replace("\\", "/").rsplit("/", 1)[-1]
    ext = ('.' + filename.rsplit('.', 1)[1]).lower() if '.' in filename else ''

    # Binary files (images, PDFs): return raw bytes
    if ext in IMAGE_EXTS or ext in PDF_EXTS:
        mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        return send_file(file_full, mimetype=mime, download_name=path.rsplit('/', 1)[-1])

    # Text files: return JSON with content and ext
    try:
        content = file_full.read_text(encoding="utf-8", errors="replace")
    except Exception:
        abort(500)
    return jsonify({"content": content, "path": path, "ext": ext})


@app.route("/api/blob", methods=["PUT"])
def blob_write():
    data = request.get_json()
    if not data:
        abort(400)
    name = data.get("repo", "")
    path = data.get("path", "")
    file_content = data.get("content")
    if file_content is None:
        abort(400)

    repo_path = valid_repo(name)

    if not path or ".." in path:
        abort(400)

    file_full = (repo_path / path).resolve()
    if not str(file_full).startswith(str(repo_path.resolve())):
        abort(403)
    if not file_full.is_file():
        abort(404)

    try:
        file_full.write_text(file_content, encoding="utf-8")
    except Exception:
        abort(500)
    return jsonify({"ok": True})


@app.route("/api/favorites")
def favorites():
    return jsonify(read_favorites())


@app.route("/api/favorites", methods=["POST"])
def add_favorite():
    data = request.get_json()
    if not data or "path" not in data:
        abort(400)
    path = data["path"]
    favs = read_favorites()
    if path not in favs:
        favs.append(path)
        write_favorites(favs)
    return jsonify({"ok": True})


@app.route("/api/favorites", methods=["DELETE"])
def remove_favorite():
    data = request.get_json()
    if not data or "path" not in data:
        abort(400)
    path = data["path"]
    favs = read_favorites()
    if path in favs:
        favs.remove(path)
        write_favorites(favs)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5125, debug=False)
