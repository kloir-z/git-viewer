# Read Bookmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-file "bookmark" (しおり) to the Files tab preview so users can mark where they left off reading and jump back later. One bookmark per file, stored server-side.

**Architecture:** Flask backend adds `GET/PUT/DELETE /api/bookmark` plus a JSON store `bookmarks.json` (same pattern as `favorites.json`). Frontend: Markdown preview tags each top-level block with a click handler; code preview is rewritten with a line-number gutter whose numbers are clickable. A jump button appears in the section header when a bookmark exists.

**Tech Stack:** Flask (backend), vanilla JS + marked + highlight.js (frontend), existing project patterns. No tests exist in this repo — verification is manual, matching the earlier `file-editing` and `folder-favorites` plans.

Spec: `docs/superpowers/specs/2026-04-20-read-bookmark-design.md`

---

## Post-Implementation Deviations

The plan below reflects the state at the start of implementation. The following changes were made interactively during the session and are now the source of truth (see spec for the updated description):

- **Click → Double-click.** All bookmark toggle gestures (Markdown block, code gutter, code body line) are `dblclick` instead of `click`, to avoid accidental toggles while navigating. `touch-action: manipulation` was added on `.bm-target`, `.code-line-num`, and `.code-line` so mobile double-tap-zoom does not steal the gesture.
- **Code body lines are also clickable.** In addition to the gutter, `.code-line` elements respond to dblclick and set a bookmark for that line. Single-click still preserves text selection.
- **Bookmark icons (📑) removed.** The hover hint and the active-state 📑 on Markdown blocks were dropped (they cluttered the reading flow). The jump button in the section header now shows the plain text `しおりへ` instead of a 📑 glyph.
- **Inset yellow bar removed from code body lines.** Only the light-yellow background remains; the gutter cell continues to show the saturated yellow marker. The bar overlapped text.
- **Alignment fix for the code body.** Added `.code-body code.hljs { padding: 0 !important; }` to cancel the `padding: 1em` that the highlight.js github-dark CDN CSS applies to `pre code.hljs`, which otherwise offsets the body about one line below the gutter.
- **Error notifications use `alert()`.** The spec called for "小さなトースト通知1回"; the project has no toast infrastructure, so `alert()` was used (matching `saveBlob`). Both `setBookmark` and `deleteBookmark` check `r.ok` and surface failures this way.
- **Jump button is hidden when the bookmarked target no longer exists** (e.g. after the file was edited to have fewer blocks/lines). Previously the button appeared unconditionally and silently did nothing.

The original task text below is preserved as the implementation artifact; refer to the spec for current behavior.

---

### Task 1: Update `.gitignore` for JSON stores

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add `bookmarks.json` and `favorites.json`**

Current `.gitignore`:

```
.claude/settings.local.json
config.local.json
```

Replace with:

```
.claude/settings.local.json
config.local.json
bookmarks.json
favorites.json
```

- [ ] **Step 2: Verify**

Run: `git status`

Expected: `favorites.json` no longer appears as untracked. `bookmarks.json` will not appear even after it's created later.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore bookmarks.json and favorites.json"
```

---

### Task 2: Backend bookmark store + helpers

**Files:**
- Modify: `app.py` (add constants and helper functions next to `FAVORITES_FILE` / `read_favorites` / `write_favorites` around line 31-44)

- [ ] **Step 1: Add `BOOKMARKS_FILE` constant and I/O helpers**

Add after `write_favorites` (currently ending at line 44):

```python
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
```

- [ ] **Step 2: Verify app still starts**

Restart the service:

```powershell
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

Then open `http://localhost:5125/` in a browser. Expected: app loads normally (no bookmark UI yet).

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add bookmarks.json store and helpers"
```

---

### Task 3: Backend `GET /api/bookmark`

**Files:**
- Modify: `app.py` (add route after the `remove_favorite` route, around line 425)

- [ ] **Step 1: Add GET endpoint**

Add at the end of the route definitions, after `remove_favorite`:

```python
@app.route("/api/bookmark")
def bookmark_get():
    name = request.args.get("repo", "")
    path = request.args.get("path", "")
    valid_repo(name)
    if not path or ".." in path:
        abort(400)
    bms = read_bookmarks()
    entry = bms.get(name, {}).get(path)
    return jsonify(entry or {})
```

- [ ] **Step 2: Restart and verify with curl**

Restart the service (same command as Task 2 Step 2).

Test an empty case:

```bash
curl "http://localhost:5125/api/bookmark?repo=git-viewer&path=README.md"
```

Expected: `{}`

Test an invalid repo:

```bash
curl -i "http://localhost:5125/api/bookmark?repo=does-not-exist&path=x"
```

Expected: HTTP 404.

Test path traversal:

```bash
curl -i "http://localhost:5125/api/bookmark?repo=git-viewer&path=../etc"
```

Expected: HTTP 400.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add GET /api/bookmark"
```

---

### Task 4: Backend `PUT /api/bookmark`

**Files:**
- Modify: `app.py` (add route immediately after `bookmark_get`)

- [ ] **Step 1: Add PUT endpoint**

Add right after `bookmark_get`:

```python
@app.route("/api/bookmark", methods=["PUT"])
def bookmark_set():
    data = request.get_json()
    if not data:
        abort(400)
    name = data.get("repo", "")
    path = data.get("path", "")
    btype = data.get("type", "")
    index = data.get("index")
    if btype not in ("md", "text") or not isinstance(index, int):
        abort(400)
    valid_repo(name)
    if not path or ".." in path:
        abort(400)
    bms = read_bookmarks()
    if name not in bms:
        bms[name] = {}
    bms[name][path] = {"type": btype, "index": index}
    write_bookmarks(bms)
    return jsonify({"ok": True})
```

- [ ] **Step 2: Restart and verify with curl**

Restart the service.

```bash
curl -X PUT http://localhost:5125/api/bookmark \
  -H "Content-Type: application/json" \
  -d '{"repo":"git-viewer","path":"README.md","type":"md","index":3}'
```

Expected: `{"ok":true}`

Verify by GET:

```bash
curl "http://localhost:5125/api/bookmark?repo=git-viewer&path=README.md"
```

Expected: `{"index":3,"type":"md"}`

Verify the file on disk:

```bash
cat bookmarks.json
```

Expected: `{"git-viewer": {"README.md": {"type": "md", "index": 3}}}`

Test bad type:

```bash
curl -i -X PUT http://localhost:5125/api/bookmark \
  -H "Content-Type: application/json" \
  -d '{"repo":"git-viewer","path":"x","type":"bogus","index":1}'
```

Expected: HTTP 400.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add PUT /api/bookmark"
```

---

### Task 5: Backend `DELETE /api/bookmark`

**Files:**
- Modify: `app.py` (add route immediately after `bookmark_set`)

- [ ] **Step 1: Add DELETE endpoint**

Add right after `bookmark_set`:

```python
@app.route("/api/bookmark", methods=["DELETE"])
def bookmark_remove():
    data = request.get_json()
    if not data:
        abort(400)
    name = data.get("repo", "")
    path = data.get("path", "")
    valid_repo(name)
    if not path or ".." in path:
        abort(400)
    bms = read_bookmarks()
    if name in bms and path in bms[name]:
        del bms[name][path]
        if not bms[name]:
            del bms[name]
        write_bookmarks(bms)
    return jsonify({"ok": True})
```

- [ ] **Step 2: Restart and verify**

Restart the service.

Using the bookmark set in Task 4:

```bash
curl -X DELETE http://localhost:5125/api/bookmark \
  -H "Content-Type: application/json" \
  -d '{"repo":"git-viewer","path":"README.md"}'
```

Expected: `{"ok":true}`

Verify:

```bash
curl "http://localhost:5125/api/bookmark?repo=git-viewer&path=README.md"
```

Expected: `{}`

Delete a non-existent bookmark (idempotent):

```bash
curl -X DELETE http://localhost:5125/api/bookmark \
  -H "Content-Type: application/json" \
  -d '{"repo":"git-viewer","path":"does-not-exist.md"}'
```

Expected: `{"ok":true}` (no error).

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add DELETE /api/bookmark"
```

---

### Task 6: Frontend bookmark API wrappers + shared UI helpers

**Files:**
- Modify: `templates/index.html` (add helpers above `showBlob`, which currently starts at line 480)

- [ ] **Step 1: Add API wrappers and UI helpers**

Insert the following block immediately above `async function showBlob(path) {` (line 480):

```javascript
// --- Bookmark helpers ---
async function fetchBookmark(path) {
  try {
    const r = await fetch(`/api/bookmark?repo=${encodeURIComponent(currentRepo)}&path=${encodeURIComponent(path)}`);
    if (!r.ok) return {};
    return await r.json();
  } catch {
    return {};
  }
}

async function setBookmark(path, type, index) {
  try {
    await fetch('/api/bookmark', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({repo: currentRepo, path, type, index}),
    });
  } catch {}
}

async function deleteBookmark(path) {
  try {
    await fetch('/api/bookmark', {
      method: 'DELETE',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({repo: currentRepo, path}),
    });
  } catch {}
}

function splitHighlightedIntoLines(html) {
  const lines = [];
  let openTags = [];
  let currentLine = '';
  let i = 0;
  while (i < html.length) {
    const ch = html[i];
    if (ch === '<') {
      const end = html.indexOf('>', i);
      if (end < 0) { currentLine += html.slice(i); break; }
      const tag = html.slice(i, end + 1);
      currentLine += tag;
      if (tag.startsWith('</')) openTags.pop();
      else if (!tag.endsWith('/>')) openTags.push(tag);
      i = end + 1;
    } else if (ch === '\n') {
      currentLine += '</span>'.repeat(openTags.length);
      lines.push(currentLine);
      currentLine = openTags.join('');
      i++;
    } else {
      currentLine += ch;
      i++;
    }
  }
  lines.push(currentLine);
  return lines;
}

function bookmarkTarget(blobView, type, index) {
  if (type === 'md') {
    return blobView.querySelector(`[data-bm-idx="${index}"]`);
  }
  return blobView.querySelector(`.code-line[data-bm-line="${index}"]`);
}

function applyBookmarkUi(blobView, bm) {
  blobView.querySelectorAll('.bookmarked').forEach(el => el.classList.remove('bookmarked'));
  const jumpBtn = blobView.querySelector('#bm-jump-btn');
  if (!bm || !bm.type) {
    delete blobView.dataset.bmIdx;
    delete blobView.dataset.bmType;
    if (jumpBtn) jumpBtn.innerHTML = '';
    return;
  }
  blobView.dataset.bmIdx = String(bm.index);
  blobView.dataset.bmType = bm.type;
  const target = bookmarkTarget(blobView, bm.type, bm.index);
  if (target) {
    target.classList.add('bookmarked');
    if (bm.type === 'text') {
      const gutter = blobView.querySelector(`.code-line-num[data-bm-line="${bm.index}"]`);
      if (gutter) gutter.classList.add('bookmarked');
    }
  }
  if (jumpBtn) {
    jumpBtn.innerHTML = `<button class="btn-jump" onclick="jumpToBookmark()" title="しおりへ">📑</button>`;
  }
}

async function onBookmarkClick(path, type, index) {
  const blobView = document.getElementById('blob-view');
  if (!blobView) return;
  const sameType = blobView.dataset.bmType === type;
  const sameIdx = blobView.dataset.bmIdx === String(index);
  if (sameType && sameIdx) {
    await deleteBookmark(path);
    applyBookmarkUi(blobView, {});
  } else {
    await setBookmark(path, type, index);
    applyBookmarkUi(blobView, {type, index});
  }
}

function jumpToBookmark() {
  const blobView = document.getElementById('blob-view');
  if (!blobView) return;
  const idx = blobView.dataset.bmIdx;
  const type = blobView.dataset.bmType;
  if (idx === undefined || !type) return;
  const target = bookmarkTarget(blobView, type, Number(idx));
  if (target) target.scrollIntoView({block: 'center'});
}
```

- [ ] **Step 2: Restart and sanity check**

Restart the service. Open the app. Navigate to any file. Expected: the page still renders (no bookmark UI yet because `showBlob` is not wired up). Confirm no JS errors in the browser console.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: add frontend bookmark API wrappers and helpers"
```

---

### Task 7: Wire bookmarks into Markdown preview

**Files:**
- Modify: `templates/index.html` — `showBlob` Markdown branch (currently around lines 525-556)

- [ ] **Step 1: Add jump-button placeholder and block-level wiring**

Replace the current Markdown branch (the block that starts with `if (fileExt === '.md') {` and ends just before `} else {`). Current code:

```javascript
  if (fileExt === '.md') {
    const mdPrefs = JSON.parse(localStorage.getItem('mdPrefs') || '{}');
    const fontSize = mdPrefs.fontSize || '13';
    const spacing = mdPrefs.spacing || '6';
    const theme = mdPrefs.theme || 'dark';
    const themeClass = theme === 'dark' ? '' : ` md-theme-${theme}`;
    blobView.innerHTML = `
      <div class="section-header" style="margin-top:8px;">${esc(path)}<button class="btn-edit" onclick="editBlob('${esc(path)}')">編集</button></div>
      <div class="md-toolbar">
        <label>文字サイズ<select id="md-font-size" onchange="updateMdPref('fontSize',this.value)">
          <option value="11"${fontSize==='11'?' selected':''}>小</option>
          <option value="13"${fontSize==='13'?' selected':''}>中</option>
          <option value="15"${fontSize==='15'?' selected':''}>大</option>
          <option value="18"${fontSize==='18'?' selected':''}>特大</option>
        </select></label>
        <label>段落間隔<select id="md-spacing" onchange="updateMdPref('spacing',this.value)">
          <option value="4"${spacing==='4'?' selected':''}>狭い</option>
          <option value="6"${spacing==='6'?' selected':''}>普通</option>
          <option value="10"${spacing==='10'?' selected':''}>広い</option>
          <option value="16"${spacing==='16'?' selected':''}>とても広い</option>
        </select></label>
        <label>テーマ<select id="md-theme" onchange="updateMdPref('theme',this.value)">
          <option value="dark"${theme==='dark'?' selected':''}>ダーク</option>
          <option value="light"${theme==='light'?' selected':''}>ライト</option>
          <option value="sepia"${theme==='sepia'?' selected':''}>セピア</option>
        </select></label>
      </div>
      <div class="blob-container markdown-body${themeClass}" id="md-body" style="padding:12px;--md-font-size:${fontSize}px;--md-spacing:${spacing}px;"></div>`;
    const mdBody = blobView.querySelector('#md-body');
    mdBody.innerHTML = marked.parse(data.content);
    rewriteMdAssets(mdBody, parentPath(path));
    blobView.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
  } else {
```

Replace with (changed lines: section-header adds the jump-button span; after rendering, wire bookmark UI):

```javascript
  if (fileExt === '.md') {
    const mdPrefs = JSON.parse(localStorage.getItem('mdPrefs') || '{}');
    const fontSize = mdPrefs.fontSize || '13';
    const spacing = mdPrefs.spacing || '6';
    const theme = mdPrefs.theme || 'dark';
    const themeClass = theme === 'dark' ? '' : ` md-theme-${theme}`;
    blobView.innerHTML = `
      <div class="section-header" style="margin-top:8px;">${esc(path)}<span id="bm-jump-btn"></span><button class="btn-edit" onclick="editBlob('${esc(path)}')">編集</button></div>
      <div class="md-toolbar">
        <label>文字サイズ<select id="md-font-size" onchange="updateMdPref('fontSize',this.value)">
          <option value="11"${fontSize==='11'?' selected':''}>小</option>
          <option value="13"${fontSize==='13'?' selected':''}>中</option>
          <option value="15"${fontSize==='15'?' selected':''}>大</option>
          <option value="18"${fontSize==='18'?' selected':''}>特大</option>
        </select></label>
        <label>段落間隔<select id="md-spacing" onchange="updateMdPref('spacing',this.value)">
          <option value="4"${spacing==='4'?' selected':''}>狭い</option>
          <option value="6"${spacing==='6'?' selected':''}>普通</option>
          <option value="10"${spacing==='10'?' selected':''}>広い</option>
          <option value="16"${spacing==='16'?' selected':''}>とても広い</option>
        </select></label>
        <label>テーマ<select id="md-theme" onchange="updateMdPref('theme',this.value)">
          <option value="dark"${theme==='dark'?' selected':''}>ダーク</option>
          <option value="light"${theme==='light'?' selected':''}>ライト</option>
          <option value="sepia"${theme==='sepia'?' selected':''}>セピア</option>
        </select></label>
      </div>
      <div class="blob-container markdown-body${themeClass}" id="md-body" style="padding:12px;--md-font-size:${fontSize}px;--md-spacing:${spacing}px;"></div>`;
    const mdBody = blobView.querySelector('#md-body');
    mdBody.innerHTML = marked.parse(data.content);
    rewriteMdAssets(mdBody, parentPath(path));
    blobView.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
    Array.from(mdBody.children).forEach((el, idx) => {
      el.setAttribute('data-bm-idx', String(idx));
      el.classList.add('bm-target');
      el.addEventListener('click', (e) => {
        if (e.target.closest('a, button, input, select, textarea, img')) return;
        onBookmarkClick(path, 'md', idx);
      });
    });
    const bm = await fetchBookmark(path);
    applyBookmarkUi(blobView, bm);
  } else {
```

- [ ] **Step 2: Restart and manually verify**

Restart the service. Open a Markdown file in the Files tab (e.g., `git-viewer/README.md`).

- Click on a paragraph — a bookmark icon/band should appear on that paragraph and the 📑 button should appear in the header.
- Click elsewhere — the bookmark should move to the new block.
- Click the same block again — the bookmark should clear and the 📑 button should disappear.
- Re-open the file (click the file in the tree again) — the bookmark and 📑 button should restore on the previously-marked block.
- Click the 📑 button — the view should scroll to the bookmarked block.

If styles look wrong (no visible marker), that's expected — CSS comes in Task 9.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: wire bookmarks into Markdown preview"
```

---

### Task 8: Rewrite code/text preview with line gutter and bookmark support

**Files:**
- Modify: `templates/index.html` — `showBlob` code/text branch (the `else` block currently at lines 557-564)

- [ ] **Step 1: Replace the code/text rendering branch**

Find the current `else` branch of `showBlob`:

```javascript
  } else {
    const lang = LANG_MAP[fileExt] || 'plaintext';
    const escaped = data.content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    blobView.innerHTML = `
      <div class="section-header" style="margin-top:8px;">${esc(path)}<button class="btn-edit" onclick="editBlob('${esc(path)}')">編集</button></div>
      <div class="blob-container"><pre class="blob-content"><code class="language-${lang}">${escaped}</code></pre></div>`;
    blobView.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
  }
```

Replace with:

```javascript
  } else {
    const lang = LANG_MAP[fileExt] || 'plaintext';
    let highlighted;
    try {
      highlighted = hljs.highlight(data.content, {language: lang, ignoreIllegals: true}).value;
    } catch {
      highlighted = data.content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
    const lines = splitHighlightedIntoLines(highlighted);
    const gutterHtml = lines.map((_, i) =>
      `<div class="code-line-num" data-bm-line="${i+1}">${i+1}</div>`
    ).join('');
    const bodyHtml = lines.map((line, i) =>
      `<div class="code-line" data-bm-line="${i+1}">${line || ' '}</div>`
    ).join('');
    blobView.innerHTML = `
      <div class="section-header" style="margin-top:8px;">${esc(path)}<span id="bm-jump-btn"></span><button class="btn-edit" onclick="editBlob('${esc(path)}')">編集</button></div>
      <div class="blob-container">
        <div class="code-wrapper">
          <div class="code-gutter">${gutterHtml}</div>
          <pre class="code-body"><code class="language-${lang} hljs">${bodyHtml}</code></pre>
        </div>
      </div>`;
    blobView.querySelectorAll('.code-gutter .code-line-num').forEach(el => {
      el.addEventListener('click', () => {
        const line = Number(el.getAttribute('data-bm-line'));
        onBookmarkClick(path, 'text', line);
      });
    });
    const bm = await fetchBookmark(path);
    applyBookmarkUi(blobView, bm);
  }
```

- [ ] **Step 2: Restart and manually verify**

Restart the service. Open a code file (e.g., `git-viewer/app.py`).

- Line numbers should appear on the left.
- Clicking a line number should mark that line and show the 📑 button.
- Clicking the same line number again should unmark.
- Clicking a different line number should move the bookmark.
- Reopening the file should restore the bookmark and show the jump button.
- Selecting text in the body should still work normally (clicking the body text should NOT set a bookmark).
- Open a file with multi-line strings or block comments (e.g., a Python file with `"""..."""` spanning lines) and confirm syntax coloring remains correct line by line.

If styles look rough, that's expected — CSS comes in Task 9.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: add line gutter and bookmarks to code preview"
```

---

### Task 9: CSS for bookmarks and code gutter

**Files:**
- Modify: `static/style.css` — add rules at the end of the file (after the existing `/* Edit mode */` block, around line 433)

- [ ] **Step 1: Add bookmark + gutter styles**

Append to the end of `static/style.css`:

```css
/* Bookmark (read marker) */
.bm-target { position: relative; cursor: pointer; }
.bm-target:hover::before {
  content: "📑";
  position: absolute;
  left: -22px;
  top: 0;
  opacity: 0.35;
  font-size: 12px;
  pointer-events: none;
}
.markdown-body > .bookmarked {
  border-left: 4px solid #f0c04a;
  padding-left: 8px;
  background: rgba(240, 192, 74, 0.08);
}
.markdown-body > .bookmarked::before {
  content: "📑";
  opacity: 1;
}

/* Code preview with line gutter */
.code-wrapper { display: flex; align-items: flex-start; min-width: 100%; }
.code-gutter {
  flex: 0 0 auto;
  padding: 8px 6px 8px 8px;
  text-align: right;
  color: var(--text-muted);
  user-select: none;
  background: #0d1117;
  border-right: 1px solid #21262d;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  font-size: 12px;
  line-height: 1.4;
}
.code-line-num { cursor: pointer; padding: 0 4px; }
.code-line-num:hover { color: #f0c04a; background: rgba(240, 192, 74, 0.12); }
.code-line-num.bookmarked {
  color: #0d1117;
  background: #f0c04a;
  font-weight: bold;
}
.code-body {
  flex: 1 1 auto;
  margin: 0;
  padding: 8px;
  overflow-x: auto;
  background: #161b22;
}
.code-line {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  font-size: 12px;
  line-height: 1.4;
  white-space: pre;
  color: var(--text);
}
.code-line.bookmarked {
  background: rgba(240, 192, 74, 0.08);
  box-shadow: inset 4px 0 0 #f0c04a;
}

/* Jump-to-bookmark button */
.btn-jump {
  margin-left: 6px;
  padding: 2px 6px;
  background: var(--bg-tertiary);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
  font-size: 11px;
}
.btn-jump:hover { background: var(--accent); color: #fff; }
```

- [ ] **Step 2: Hard-reload the browser and verify**

No service restart needed (CSS only), but reload the page with cache bypass (Ctrl+F5 / Cmd+Shift+R).

Manually verify:

- Markdown: hovering a paragraph shows a faint 📑 to the left; the bookmarked paragraph has a yellow left border and a light yellow background; the 📑 persists at full opacity on the bookmarked block.
- Code: the gutter is visible with right-aligned line numbers; the bookmarked line has a yellow highlight in the gutter and an inset yellow bar in the body; hovering a line number shows a subtle highlight.
- The 📑 jump button is visible in the header when a bookmark exists and disappears when cleared.

- [ ] **Step 3: Commit**

```bash
git add static/style.css
git commit -m "style: add bookmark and code gutter styles"
```

---

### Task 10: End-to-end verification

**Files:** none

- [ ] **Step 1: Full manual test pass**

Restart the service one final time to pick up all changes:

```powershell
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

Walk through the full feature:

1. **Markdown bookmark set / move / clear**
   - Open a `.md` file with several paragraphs.
   - Click paragraph A → bookmark appears. Header 📑 button appears.
   - Click paragraph B → bookmark moves to B.
   - Click paragraph B again → bookmark clears; 📑 button disappears.
2. **Markdown persistence**
   - Set a bookmark, navigate away to another file, come back → bookmark is restored.
3. **Markdown link safety**
   - In a paragraph containing a link, click the link itself → navigates (bookmark NOT set).
   - Click whitespace in the same paragraph → bookmark is set.
4. **Code bookmark set / move / clear**
   - Open a code file.
   - Click line number 10 → line marked, header shows 📑.
   - Click line 42 → bookmark moves.
   - Click line 42 again → cleared.
5. **Code text selection**
   - Select a range of text in the code body → selection works normally (no accidental bookmark).
6. **Cross-file isolation**
   - Bookmark file X, bookmark file Y, re-open X → X's bookmark is intact (not Y's).
7. **Jump button**
   - Scroll away from the bookmark. Click 📑 → scrolls to the bookmarked block/line (centered).
8. **Edit mode round-trip**
   - With a bookmark set, click 編集 → bookmark UI disappears (editor shown).
   - Click キャンセル → bookmark reappears on the same block/line.
9. **Stale index handling**
   - Edit and save a Markdown file to remove blocks so the bookmark's index exceeds the number of blocks.
   - Re-open → no error, no marker shown; 📑 button does not appear because the target is missing. Setting a new bookmark works.
10. **Broken `bookmarks.json`**
    - Stop the service, replace `bookmarks.json` with `not json` on disk, restart.
    - Expected: app still starts, GET returns `{}`, setting a bookmark overwrites the file with valid JSON.

- [ ] **Step 2: Restore state**

If you created test bookmarks you want to keep, leave them. Otherwise, delete `bookmarks.json`.

- [ ] **Step 3: Final commit (if any fixes were needed)**

Only if Step 1 surfaced issues that required edits:

```bash
git add <fixed-files>
git commit -m "fix: <summary of what was fixed>"
```

Otherwise skip this step.

---

## Self-Review Notes

- **Spec coverage:** Data store ✓ (Task 2), GET/PUT/DELETE ✓ (Tasks 3-5), `valid_repo` + `..` check ✓ (in each route), Markdown block UI ✓ (Tasks 6-7), code gutter UI ✓ (Task 8), jump button ✓ (Tasks 6-8), CSS ✓ (Task 9), `.gitignore` ✓ (Task 1), edit-mode round-trip verification ✓ (Task 10 step 1.8), stale index handling ✓ (Task 10 step 1.9), broken JSON ✓ (Task 10 step 1.10).
- **No placeholders:** Every step shows the exact code or command.
- **Type/name consistency:** `BOOKMARKS_FILE`, `read_bookmarks`, `write_bookmarks`, `bookmark_get`, `bookmark_set`, `bookmark_remove`, `fetchBookmark`, `setBookmark`, `deleteBookmark`, `splitHighlightedIntoLines`, `bookmarkTarget`, `applyBookmarkUi`, `onBookmarkClick`, `jumpToBookmark`, `.bm-target`, `.bookmarked`, `.code-wrapper`, `.code-gutter`, `.code-line-num`, `.code-body`, `.code-line`, `.btn-jump`, `#bm-jump-btn`, `data-bm-idx`, `data-bm-line`, `data-bm-type` — all consistent across tasks.
