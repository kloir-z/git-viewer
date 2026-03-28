import mimetypes
import os
import re
import subprocess
from io import BytesIO
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, send_file

app = Flask(__name__)

CODE_DIR = Path(os.environ.get("GIT_VIEWER_CODE_DIR", "/home/user/code"))


def valid_repo(name: str) -> Path:
    """Validate repo name and return path. Abort 404 if not a git repo."""
    if "/" in name or "\\" in name or name.startswith("."):
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
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else default
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return default


def get_repo_info(repo_path: Path) -> dict:
    """Gather status info for a single repo."""
    name = repo_path.name
    branch = git(repo_path, "rev-parse", "--abbrev-ref", "HEAD", default="unknown")

    status_lines = git(repo_path, "status", "--porcelain")
    changes = len(status_lines.splitlines()) if status_lines else 0

    log_line = git(repo_path, "log", "-1", "--format=%h\t%s\t%aI")
    if log_line and "\t" in log_line:
        parts = log_line.split("\t", 2)
        latest_commit, latest_message, latest_time = parts[0], parts[1], parts[2]
    else:
        latest_commit, latest_message, latest_time = "", "", ""

    remote_raw = git(repo_path, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    if remote_raw and "\t" in remote_raw:
        ahead, behind = remote_raw.split("\t")
        if int(ahead) > 0 and int(behind) > 0:
            remote_status = f"ahead {ahead}, behind {behind}"
        elif int(ahead) > 0:
            remote_status = f"ahead {ahead}"
        elif int(behind) > 0:
            remote_status = f"behind {behind}"
        else:
            remote_status = "up to date"
    else:
        remote_status = "no remote"

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


@app.route("/api/repos")
def repos():
    repo_list = []
    for item in sorted(CODE_DIR.iterdir(), key=lambda p: p.name.lower()):
        if item.is_dir() and (item / ".git").is_dir():
            repo_list.append(get_repo_info(item))
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
        rel = str(item.relative_to(repo_path))
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

    ext = ('.' + path.rsplit('.', 1)[1]).lower() if '.' in path.rsplit('/', 1)[-1] else ''

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5125, debug=False)
