# Git Viewer

Read-only web UI for browsing git repositories. Built for Raspberry Pi but works on any Linux machine.

## Features

- **Overview** -- branch, changes, remote status, recent commits at a glance
- **Log** -- commit history with inline diff expansion (line-by-line / side-by-side toggle)
- **Diff** -- uncommitted changes with word-level highlighting (diff2html)
- **Files** -- working tree browser with syntax highlighting (highlight.js), Markdown rendering (marked.js), image/PDF preview

## Setup

```bash
pip install -r requirements.txt  # flask>=3.0
python app.py                    # http://localhost:5125
```

By default it scans all git repos under `/home/user/code/`. Change `CODE_DIR` in `app.py` to point to your directory.

### systemd (optional)

```bash
sudo cp git-viewer.service /etc/systemd/system/
sudo systemctl enable --now git-viewer.service
```

## Stack

- Python / Flask (backend, ~200 lines)
- Vanilla JS SPA (frontend, single index.html)
- diff2html, highlight.js, marked.js (CDN)
- GitHub Dark theme
