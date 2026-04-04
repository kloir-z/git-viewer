# Folder Favorites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ファイルタブのディレクトリにお気に入り機能を追加し、ヘッダーからワンクリックでジャンプできるようにする

**Architecture:** バックエンドに `favorites.json` ファイルベースのCRUD APIを追加。フロントエンドはヘッダーのタイトルをお気に入りドロップダウンに置換し、ファイルタブのディレクトリ行に星マークトグルを追加。

**Tech Stack:** Flask (Python), Vanilla JS, CSS

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `app.py` | Modify (lines 1-8, 319-322) | Add favorites API endpoints (GET/POST/DELETE) |
| `templates/index.html` | Modify (lines 15-21, 40-46, 84-105, 282-301) | Header dropdown, star icons, favorites state |
| `static/style.css` | Modify (end of file) | Star icon styles |

---

### Task 1: Backend - Favorites API

**Files:**
- Modify: `app.py` — add `import json` (line 1 area), favorites file path constant, read/write helpers, 3 API endpoints (after line 318)

- [ ] **Step 1: Add json import and FAVORITES_FILE constant**

In `app.py`, add `json` to the imports and define the favorites file path after `CODE_DIR`:

```python
import json  # add to existing imports at top
```

After line 12 (`CODE_DIR = ...`), add:

```python
FAVORITES_FILE = Path(__file__).parent / "favorites.json"
```

- [ ] **Step 2: Add read/write helper functions**

After `FAVORITES_FILE` definition, add:

```python
def read_favorites() -> list:
    if FAVORITES_FILE.is_file():
        try:
            return json.loads(FAVORITES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def write_favorites(favs: list):
    FAVORITES_FILE.write_text(json.dumps(favs, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 3: Add GET /api/favorites endpoint**

Before `if __name__ == "__main__":` (line 321), add:

```python
@app.route("/api/favorites")
def favorites():
    return jsonify(read_favorites())
```

- [ ] **Step 4: Add POST /api/favorites endpoint**

```python
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
```

- [ ] **Step 5: Add DELETE /api/favorites endpoint**

```python
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
```

- [ ] **Step 6: Test the API manually**

Start the server and test:

```bash
# GET (should return [])
curl http://localhost:5125/api/favorites

# POST
curl -X POST http://localhost:5125/api/favorites -H "Content-Type: application/json" -d "{\"path\":\"test-repo/src\"}"

# GET (should return ["test-repo/src"])
curl http://localhost:5125/api/favorites

# DELETE
curl -X DELETE http://localhost:5125/api/favorites -H "Content-Type: application/json" -d "{\"path\":\"test-repo/src\"}"

# GET (should return [])
curl http://localhost:5125/api/favorites
```

- [ ] **Step 7: Commit**

```bash
git add app.py
git commit -m "feat: add favorites API endpoints with JSON file storage"
```

---

### Task 2: Frontend - Header Favorites Dropdown

**Files:**
- Modify: `templates/index.html` — HTML header (lines 15-21), JS globals (lines 42-46), `init()` (lines 84-105), add `buildFavOptions()` and `jumpToFavorite()` functions

- [ ] **Step 1: Replace header HTML**

In `templates/index.html`, replace lines 15-21:

```html
<div class="header">
  <h1>Git Viewer</h1>
  <div class="header-controls">
    <select id="repo-select"></select>
    <button id="btn-refresh" onclick="refresh()">↻</button>
  </div>
</div>
```

with:

```html
<div class="header">
  <select id="fav-select" onchange="jumpToFavorite(this.value); this.value='';">
    <option value="">&#9733; Favorites</option>
  </select>
  <div class="header-controls">
    <select id="repo-select"></select>
    <button id="btn-refresh" onclick="refresh()">↻</button>
  </div>
</div>
```

- [ ] **Step 2: Add favorites global variable and DOM ref**

After line 40 (`const repoSelect = $('#repo-select');`), add:

```js
const favSelect = $('#fav-select');
```

After line 46 (`let diffFormat = 'line-by-line';`), add:

```js
let favorites = [];
```

- [ ] **Step 3: Add buildFavOptions function**

After the `buildRepoOptions` function (after line 82), add:

```js
function buildFavOptions() {
  let html = '<option value="">&#9733; Favorites</option>';
  for (const fav of favorites) {
    const parts = fav.split('/');
    // For "category/repo/path" or "repo/path", show as "repo / path"
    // Find the repo name first by matching against known repos
    let label = fav;
    for (const r of repos) {
      if (fav.startsWith(r.name + '/')) {
        const dirPath = fav.substring(r.name.length + 1);
        label = r.name + ' / ' + dirPath;
        break;
      }
      if (fav === r.name) {
        label = r.name;
        break;
      }
    }
    html += `<option value="${esc(fav)}">${esc(label)}</option>`;
  }
  favSelect.innerHTML = html;
}
```

- [ ] **Step 4: Add jumpToFavorite function**

After `buildFavOptions`, add:

```js
function jumpToFavorite(fav) {
  if (!fav) return;
  // Find which repo this favorite belongs to
  for (const r of repos) {
    if (fav.startsWith(r.name + '/') || fav === r.name) {
      const dirPath = fav.startsWith(r.name + '/') ? fav.substring(r.name.length + 1) : '';
      currentRepo = r.name;
      repoSelect.value = currentRepo;
      currentTab = 'files';
      $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === 'files'));
      renderFiles(dirPath);
      return;
    }
  }
}
```

- [ ] **Step 5: Load favorites in init()**

In the `init()` function, after line 85 (`repos = await fetchJson('/api/repos');`), add:

```js
  favorites = await fetchJson('/api/favorites');
```

After line 86 (`repoSelect.innerHTML = buildRepoOptions(repos);`), add:

```js
  buildFavOptions();
```

- [ ] **Step 6: Test the dropdown**

Reload the page. The header should show "★ Favorites" dropdown on the left (empty for now) and the repo select on the right. The "Git Viewer" title should be gone.

- [ ] **Step 7: Commit**

```bash
git add templates/index.html
git commit -m "feat: add favorites dropdown in header replacing title"
```

---

### Task 3: Frontend - Star Icons in File Tab

**Files:**
- Modify: `templates/index.html` — `renderFiles()` function (lines 282-301), add `toggleFavorite()` function
- Modify: `static/style.css` — add star icon styles at end of file

- [ ] **Step 1: Add star icon CSS**

At the end of `static/style.css`, add:

```css
/* Favorite star */
.fav-star {
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  flex-shrink: 0;
  margin-left: auto;
}
.fav-star:hover { opacity: 0.8; }
.fav-star.active { color: var(--yellow); }
.fav-star:not(.active) { color: var(--text-dim); }
```

- [ ] **Step 2: Add toggleFavorite function**

In `templates/index.html`, after the `jumpToFavorite` function, add:

```js
async function toggleFavorite(event, repoName, dirPath) {
  event.stopPropagation();
  const favKey = repoName + '/' + dirPath;
  const isFav = favorites.includes(favKey);
  await fetch('/api/favorites', {
    method: isFav ? 'DELETE' : 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path: favKey}),
  });
  if (isFav) {
    favorites = favorites.filter(f => f !== favKey);
  } else {
    favorites.push(favKey);
  }
  buildFavOptions();
  renderFiles();
}
```

- [ ] **Step 3: Modify renderFiles to show star icons on directory rows**

Replace the directory row template in `renderFiles()`. Change:

```js
      ${(entries || []).map(e => e.type === 'tree'
        ? `<div class="list-row clickable" onclick="renderFiles('${esc(e.path)}')"><span class="tree-icon">${ICON_FOLDER}</span><span>${esc(e.name)}</span></div>`
        : `<div class="list-row clickable" onclick="showBlob('${esc(e.path)}')"><span class="tree-icon">${ICON_FILE}</span><span>${esc(e.name)}</span></div>`
      ).join('')}
```

to:

```js
      ${(entries || []).map(e => e.type === 'tree'
        ? `<div class="list-row clickable" onclick="renderFiles('${esc(e.path)}')"><span class="tree-icon">${ICON_FOLDER}</span><span>${esc(e.name)}</span><span class="fav-star ${favorites.includes(currentRepo + '/' + e.path) ? 'active' : ''}" onclick="toggleFavorite(event, currentRepo, '${esc(e.path)}')">${favorites.includes(currentRepo + '/' + e.path) ? '★' : '☆'}</span></div>`
        : `<div class="list-row clickable" onclick="showBlob('${esc(e.path)}')"><span class="tree-icon">${ICON_FILE}</span><span>${esc(e.name)}</span></div>`
      ).join('')}
```

- [ ] **Step 4: Test the star icons**

1. Navigate to the Files tab
2. Each directory row should show a ☆ on the right side
3. Click ☆ → should toggle to ★ (yellow) and appear in the header dropdown
4. Click ★ → should toggle back to ☆ and be removed from the header dropdown
5. Select a favorite from the header dropdown → should jump to that folder

- [ ] **Step 5: Commit**

```bash
git add templates/index.html static/style.css
git commit -m "feat: add star toggle on directory rows for favorites"
```

---

### Task 4: Service Restart & Final Verification

- [ ] **Step 1: Restart the service**

Windows:
```powershell
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

- [ ] **Step 2: Verify end-to-end**

1. Open http://localhost:5125
2. Confirm "Git Viewer" title is gone and "★ Favorites" dropdown is in its place
3. Go to Files tab → click ☆ on a folder → confirm it turns ★
4. Confirm the folder appears in the header dropdown
5. Switch to a different repo/tab → select the favorite from dropdown → confirm it jumps to the correct repo + folder
6. Click ★ to unfavorite → confirm it's removed from the dropdown
7. Refresh the page → confirm favorites persist (stored in `favorites.json`)

- [ ] **Step 3: Commit final state if any adjustments were needed**

```bash
git add -A
git commit -m "fix: adjust favorites feature after testing"
```
