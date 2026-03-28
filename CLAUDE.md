# CLAUDE.md

## Project overview

Git Viewer is a read-only web UI for browsing local git repositories. Flask backend + vanilla JS SPA frontend. Designed for Raspberry Pi, runs on port 5125.

## Architecture

- `app.py` -- Flask app with REST API endpoints. All git operations via `subprocess` calling `git` CLI.
- `templates/index.html` -- Single-page app. All JS is inline. Uses diff2html, highlight.js, marked.js from CDN.
- `static/style.css` -- GitHub Dark theme. diff2html dark overrides use `!important` to override CDN defaults.
- `git-viewer.service` -- systemd unit file.

## API endpoints

- `GET /api/repos` -- list all repos under CODE_DIR with status info. Scans two levels: direct child repos and `category/repo` under subdirectories. Each repo includes a `category` field.
- `GET /api/log?repo=<name>&limit=50` -- commit history with shortstat
- `GET /api/diff?repo=<name>&commit=<hash>&file=<path>` -- unified diff (commit optional for working tree, file optional for filtering)
- `GET /api/branches?repo=<name>` -- branch list
- `GET /api/tree?repo=<name>&path=<subdir>` -- directory listing from working tree
- `GET /api/blob?repo=<name>&path=<file>` -- file content (JSON for text, raw bytes for images/PDFs)

## Key decisions

- File tree and blob endpoints read from the **working tree** (not `git ls-tree HEAD`), so untracked/modified files are visible.
- diff2html's default CSS uses `position: absolute` on line numbers. We override to `position: static` + `display: table-cell` so line numbers scroll with content.
- Root commits (no parent) use `git diff-tree --root` instead of `commit^..commit`.
- CODE_DIR supports two-level repo discovery: repos directly under CODE_DIR and repos nested one level deeper (`CODE_DIR/category/repo`). Repo names use `category/repo` format for nested repos.
- `subprocess` uses raw bytes + UTF-8 decode (not `text=True`) to avoid Windows cp932 encoding issues with non-ASCII paths.

## Development

```bash
# Raspberry Pi (systemd)
sudo systemctl restart git-viewer.service

# Windows (PowerShell)
$env:GIT_VIEWER_CODE_DIR="C:/code"; python app.py

# Windows (cmd)
set GIT_VIEWER_CODE_DIR=C:/code && python app.py

# Linux / macOS
GIT_VIEWER_CODE_DIR="C:/code" python app.py
```

CODE_DIR defaults to `/home/user/code/`. Override with `GIT_VIEWER_CODE_DIR` env var. Subdirectories under CODE_DIR are treated as category folders.
