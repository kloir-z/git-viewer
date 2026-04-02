# File Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add inline file editing to the Files tab so users can edit text files and save changes to the working tree.

**Architecture:** Add a `PUT /api/blob` endpoint that writes file content to disk. On the frontend, add an edit button to text file views that swaps the highlighted code for a textarea with save/cancel controls.

**Tech Stack:** Flask (backend), vanilla JS (frontend), existing project patterns

---

### Task 1: Add `PUT /api/blob` backend endpoint

**Files:**
- Modify: `app.py:261-289` (after existing `GET /api/blob` route)

- [ ] **Step 1: Add the PUT endpoint to `app.py`**

Add this route after the existing `GET /api/blob` route (after line 289):

```python
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
```

- [ ] **Step 2: Verify manually**

Start the app and test with curl:

```bash
curl -X PUT http://localhost:5125/api/blob \
  -H "Content-Type: application/json" \
  -d '{"repo":"git-viewer","path":"README.md","content":"test"}'
```

Expected: `{"ok":true}` and the file content is updated. Restore the file after testing.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add PUT /api/blob endpoint for file editing"
```

---

### Task 2: Add edit button and edit mode to frontend

**Files:**
- Modify: `templates/index.html` — `showBlob()` function and add new helper functions

- [ ] **Step 1: Add `editBlob()` function**

Add this function after the `showBlob()` function (after line 397):

```javascript
let editingPath = '';
let editingOriginal = '';

async function editBlob(path) {
  const blobView = document.getElementById('blob-view');
  if (!blobView) return;

  editingPath = path;
  const blobUrl = `/api/blob?repo=${currentRepo}&path=${encodeURIComponent(path)}`;
  const data = await fetchJson(blobUrl);
  if (data.content === undefined) {
    blobView.innerHTML = '<div class="diff-empty">ファイルを編集できません</div>';
    return;
  }

  editingOriginal = data.content;
  const escaped = data.content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  blobView.innerHTML = `
    <div class="section-header" style="margin-top:8px;">${esc(path)}
      <span style="margin-left:8px;color:var(--text-muted);font-size:11px;">編集中</span>
    </div>
    <div class="blob-container">
      <textarea id="edit-textarea" class="edit-textarea" spellcheck="false">${escaped}</textarea>
    </div>
    <div class="edit-controls">
      <button class="btn-save" onclick="saveBlob()">保存</button>
      <button class="btn-cancel" onclick="showBlob('${esc(editingPath)}')">キャンセル</button>
    </div>`;

  const ta = document.getElementById('edit-textarea');
  ta.style.height = Math.max(200, ta.scrollHeight) + 'px';
}

async function saveBlob() {
  const ta = document.getElementById('edit-textarea');
  if (!ta) return;

  const res = await fetch('/api/blob', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({repo: currentRepo, path: editingPath, content: ta.value}),
  });

  if (res.ok) {
    showBlob(editingPath);
  } else {
    alert('保存に失敗しました');
  }
}
```

- [ ] **Step 2: Add the edit button to `showBlob()`**

In the `showBlob()` function, modify the two places where the section-header is rendered for text files (markdown and code blocks). Add an edit button to both.

For the markdown section (around line 386), change:
```javascript
      <div class="section-header" style="margin-top:8px;">${esc(path)}</div>
```
to:
```javascript
      <div class="section-header" style="margin-top:8px;">${esc(path)}<button class="btn-edit" onclick="editBlob('${esc(path)}')">編集</button></div>
```

For the code section (around line 392), change:
```javascript
      <div class="section-header" style="margin-top:8px;">${esc(path)}</div>
```
to:
```javascript
      <div class="section-header" style="margin-top:8px;">${esc(path)}<button class="btn-edit" onclick="editBlob('${esc(path)}')">編集</button></div>
```

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: add inline file editing UI"
```

---

### Task 3: Add CSS styles for edit mode

**Files:**
- Modify: `static/style.css`

- [ ] **Step 1: Add edit-related styles**

Append these styles to the end of `static/style.css`:

```css
/* Edit mode */
.btn-edit {
  margin-left: 8px;
  padding: 2px 10px;
  background: var(--bg-tertiary);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
}
.btn-edit:hover {
  background: var(--accent);
  color: #fff;
}
.edit-textarea {
  width: 100%;
  min-height: 200px;
  padding: 12px;
  background: var(--bg-secondary);
  color: var(--text);
  border: none;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  tab-size: 4;
  box-sizing: border-box;
}
.edit-textarea:focus {
  outline: 1px solid var(--accent);
}
.edit-controls {
  display: flex;
  gap: 8px;
  padding: 8px 0;
}
.btn-save, .btn-cancel {
  padding: 4px 16px;
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.btn-save {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-save:hover {
  opacity: 0.9;
}
.btn-cancel {
  background: var(--bg-tertiary);
  color: var(--text);
}
.btn-cancel:hover {
  background: var(--border);
}
```

- [ ] **Step 2: Commit**

```bash
git add static/style.css
git commit -m "style: add edit mode styles"
```

---

### Task 4: Manual verification and restart service

- [ ] **Step 1: Restart the service**

Windows:
```powershell
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

- [ ] **Step 2: Verify the feature**

1. Open the app in browser, go to Files tab
2. Click a text file — confirm "編集" button appears in the header
3. Click "編集" — confirm textarea appears with file content
4. Click "キャンセル" — confirm it returns to highlighted view
5. Edit content and click "保存" — confirm file is saved and highlighted view returns
6. Confirm images/PDFs do NOT show the edit button
