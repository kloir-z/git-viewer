# SRT Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.srt` 字幕ファイルを cue カードリストとして表示し、話者色分けと cue 単位のブックマークをサポートする。

**Architecture:** バックエンドは `.srt` をテキスト拡張子として受理するよう 1 行追加するのみ。フロントエンドは `showBlob` に SRT 分岐を追加し、`parseSrt()` で cue 配列を作ってカード列に描画。ブックマークは既存の Markdown 方式（`type: "md"`、cue 配列のインデックスで識別）を再利用する。

**Tech Stack:** Flask（バックエンドは 1 行追加のみ）、vanilla JS（追加ライブラリなし）、CSS カスタムプロパティで話者色をカード単位に注入。

**Testing:** このプロジェクトは自動テスト未導入（`README.md`、`requirements.txt` 参照）。既存の仕様書（`docs/superpowers/specs/2026-04-20-read-bookmark-design.md`）と同様に手動テストで検証する。

---

## Task 1: Backend + JS で `.srt` をテキスト扱いにする

**Files:**
- Modify: `app.py:342-348` （`TEXT_EXTS` 定数）
- Modify: `templates/index.html:466-471` （JS 側 `TEXT_EXTS` 定数）

この Task だけでは SRT は「素のテキスト + hljs 行番号」で表示される（バイナリダウンロードよりは改善）。Task 2 でカード UI に昇格させる。

- [ ] **Step 1: `app.py` の `TEXT_EXTS` に `.srt` を追加**

`app.py:342-348` の `TEXT_EXTS` セットを以下に変更:

```python
TEXT_EXTS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.sh', '.bash', '.json', '.yml', '.yaml',
    '.xml', '.html', '.css', '.toml', '.md', '.txt', '.cfg', '.ini', '.conf',
    '.env', '.service', '.timer', '.csv', '.sql', '.rb', '.go', '.rs', '.java',
    '.c', '.h', '.cpp', '.hpp', '.vue', '.svelte', '.gitignore', '.dockerignore',
    '.dockerfile', '.makefile', '.srt', '',
}
```

追加したのは `'.srt'` のみ。

- [ ] **Step 2: `templates/index.html` の JS 側 `TEXT_EXTS` にも `'srt'` を追加**

`templates/index.html:466-471` の配列を以下に変更:

```javascript
const TEXT_EXTS = [
  'py','js','ts','jsx','tsx','sh','bash','json','yml','yaml','xml','html','css',
  'toml','md','txt','cfg','ini','conf','env','service','timer','csv','sql',
  'rb','go','rs','java','c','h','cpp','hpp','vue','svelte','gitignore',
  'dockerignore','makefile','lock','log','srt',
];
```

追加したのは `'srt'` のみ。

- [ ] **Step 3: サービス再起動**

Windows の場合:

```powershell
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

Raspberry Pi の場合:

```bash
sudo systemctl restart git-viewer.service
```

（ユーザーの環境に合わせていずれか）

- [ ] **Step 4: 手動確認**

ブラウザで `Aivis_Conversation` リポジトリを開き、`projects/20260420_動作確認デモ/out/sample_hello.srt` を選択する。

期待: 「バイナリファイル — ダウンロード」ではなく、素のテキスト（行番号付きコードビュー）として内容が表示される。

- [ ] **Step 5: コミット**

```bash
git add app.py templates/index.html
git commit -m "feat: serve .srt as text instead of binary"
```

---

## Task 2: `parseSrt()` と `speakerColor()` を追加

**Files:**
- Modify: `templates/index.html` （既存の `TEXT_EXTS` / `LANG_MAP` 定数のすぐ下、`splitHighlightedIntoLines` の手前、line 480 付近）

この2つは純粋関数で副作用なし。showBlob に組み込む前に単独で追加してブラウザのコンソールから試せるようにする。

- [ ] **Step 1: `parseSrt()` と `speakerColor()` を追加**

`templates/index.html` の `LANG_MAP` 定義（line 472-479）の直後、空行を挟んで以下を追加する。挿入位置は `// --- Bookmark helpers ---` コメントの手前。

```javascript
function parseSrt(text) {
  const cleaned = text.replace(/^﻿/, '').replace(/\r\n/g, '\n');
  const blocks = cleaned.split(/\n\s*\n+/);
  const timeRe = /(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)/;
  const speakerRe = /^([^\s:：]{1,16})[:：]\s*/;
  const cues = [];
  for (const block of blocks) {
    const raw = block.split('\n');
    let s = 0, e = raw.length;
    while (s < e && raw[s].trim() === '') s++;
    while (e > s && raw[e - 1].trim() === '') e--;
    const lines = raw.slice(s, e);
    if (lines.length === 0) continue;

    let i = 0;
    let index = '';
    if (/^\d+$/.test(lines[i].trim())) {
      index = lines[i].trim();
      i++;
    }
    let start = '', end = '';
    if (i < lines.length) {
      const m = lines[i].match(timeRe);
      if (m) {
        start = m[1];
        end = m[2];
        i++;
      }
    }
    const textLines = lines.slice(i);
    if (textLines.length === 0 && !index && !start) continue;
    let body = textLines.join('\n');
    let speaker = '';
    const spk = body.match(speakerRe);
    if (spk) {
      speaker = spk[1];
      body = body.slice(spk[0].length);
    }
    cues.push({index, start, end, speaker, text: body});
  }
  return cues;
}

function speakerColor(name) {
  if (!name) return '';
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) >>> 0;
  }
  return `hsl(${h % 360}, 55%, 60%)`;
}
```

- [ ] **Step 2: サービス再起動**

Task 1 Step 3 と同じコマンド（OS に応じて選ぶ）。

- [ ] **Step 3: ブラウザコンソールでの動作確認**

ブラウザで Git Viewer を開き、DevTools のコンソールで以下を実行:

```javascript
parseSrt('1\n00:00:00,000 --> 00:00:01,000\nA: hello\n\n2\n00:00:01,000 --> 00:00:02,000\nB: world\n')
```

期待出力:

```
[
  {index: "1", start: "00:00:00,000", end: "00:00:01,000", speaker: "A", text: "hello"},
  {index: "2", start: "00:00:01,000", end: "00:00:02,000", speaker: "B", text: "world"}
]
```

さらに話者色の安定性を確認:

```javascript
speakerColor('A') === speakerColor('A')  // true
speakerColor('A') !== speakerColor('B')  // true
speakerColor('')                         // ""
```

- [ ] **Step 4: コミット**

```bash
git add templates/index.html
git commit -m "feat: add parseSrt and speakerColor helpers"
```

---

## Task 3: `showBlob` に SRT 分岐を追加

**Files:**
- Modify: `templates/index.html:659-732` （`showBlob` 内の `.md` 分岐と text/code `else` 分岐の間に `else if (fileExt === '.srt')` を挿入）

- [ ] **Step 1: SRT 分岐を追加**

`templates/index.html` の `showBlob` 関数、現状:

```javascript
if (fileExt === '.md') {
  // ... Markdown rendering ...
} else {
  // ... text/code rendering ...
}
```

これを次の形に変更（`.md` 分岐と `else` の間に `else if (fileExt === '.srt')` を挿入）:

```javascript
if (fileExt === '.md') {
  // ... 既存の Markdown rendering（変更なし） ...
} else if (fileExt === '.srt') {
  const cues = parseSrt(data.content);
  if (cues.length === 0) {
    blobView.innerHTML = `
      <div class="section-header" style="margin-top:8px;">${esc(path)}<button class="btn-edit" onclick="editBlob('${esc(path)}')">編集</button></div>
      <div class="diff-empty">字幕を読み込めませんでした</div>
      <pre class="blob-container" style="padding:8px;white-space:pre-wrap;">${esc(data.content)}</pre>`;
    return;
  }
  const cardsHtml = cues.map((c, i) => {
    const color = speakerColor(c.speaker);
    const styleAttr = color ? ` style="--speaker-color: ${color};"` : '';
    const speakerBadge = c.speaker ? `<span class="srt-speaker">${esc(c.speaker)}</span>` : '';
    const timeStr = (c.start && c.end) ? `${c.start} → ${c.end}` : '--';
    const idxStr = c.index || '';
    return `
      <div class="srt-cue bm-target" data-bm-idx="${i}"${styleAttr}>
        <div class="srt-meta">
          <span class="srt-index">${esc(idxStr)}</span>
          <span class="srt-time">${esc(timeStr)}</span>
          ${speakerBadge}
        </div>
        <div class="srt-text">${esc(c.text)}</div>
      </div>`;
  }).join('');
  blobView.innerHTML = `
    <div class="section-header" style="margin-top:8px;">${esc(path)}<span id="bm-jump-btn"></span><button class="btn-edit" onclick="editBlob('${esc(path)}')">編集</button></div>
    <div class="blob-container srt-container">${cardsHtml}</div>`;
  blobView.querySelectorAll('.srt-cue').forEach((el, idx) => {
    el.addEventListener('dblclick', (e) => {
      if (e.target.closest('a, button, input, select, textarea, img')) return;
      onBookmarkClick(path, 'md', idx);
    });
  });
  const bm = await fetchBookmark(path);
  applyBookmarkUi(blobView, bm);
} else {
  // ... 既存の text/code rendering（変更なし） ...
}
```

既存の Markdown 分岐と text/code 分岐のコード本体には一切手を加えない。追加するのは上記の `else if (fileExt === '.srt') { ... }` ブロックのみ。

- [ ] **Step 2: サービス再起動**

Task 1 Step 3 と同じ。

- [ ] **Step 3: 手動確認（CSSなしでも DOM は出る）**

ブラウザで `Aivis_Conversation/projects/20260420_動作確認デモ/out/sample_hello.srt` を開く。

期待:
- cue カードの DOM が生成される（スタイル未適用なので見た目は崩れているが、テキストと番号・時刻が順番に見える）
- 「編集」ボタンが表示される
- コンソールにエラーが出ていない

この段階ではコミットせず、CSS と一緒に Task 4 末尾でコミットする（中間状態のスタイルなしカードだけでは価値がないため）。

---

## Task 4: CSS を追加して見た目を整える

**Files:**
- Modify: `static/style.css` （末尾に追記）

- [ ] **Step 1: CSS を追加**

`static/style.css` の末尾に以下を追記:

```css
/* SRT subtitle cards */
.srt-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
}
.srt-cue {
  background: var(--surface);
  border-left: 4px solid var(--speaker-color, var(--border));
  border-radius: 4px;
  padding: 8px 12px;
}
.srt-meta {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 6px;
}
.srt-index,
.srt-time {
  color: var(--text-muted);
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px;
}
.srt-speaker {
  background: var(--speaker-color);
  color: #fff;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
}
.srt-text {
  white-space: pre-wrap;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
}
```

- [ ] **Step 2: サービス再起動**

Task 1 Step 3 と同じ。

- [ ] **Step 3: 手動確認**

ブラウザで以下のファイルを順に開く:

1. `Aivis_Conversation/projects/20260420_動作確認デモ/out/sample_hello.srt`
   - 期待: A と B で左ボーダー色と話者バッジ色が異なる
   - 期待: タイムコードと cue 番号が等幅・muted 色で表示
   - 期待: 本文はサンセリフで読みやすいサイズ
2. `Aivis_Conversation/projects/20260420_半導体量子パラダイムシフト/out/半導体量子パラダイムシフト.srt`
   - 期待: 多数の cue が縦に並び、スクロールしても崩れない
3. 任意の cue を dblclick
   - 期待: `.bookmarked` が付き、ツールバーに「しおりへ」ボタンが出る
4. 別の cue を dblclick
   - 期待: 前のマーカーが消え、新しい cue にマーカーが付く
5. 同じ cue を dblclick
   - 期待: マーカーが消える
6. ページをリロードして開き直す
   - 期待: 設定したしおり位置が復元され、「しおりへ」でジャンプできる
7. 「編集」ボタンを押す
   - 期待: textarea で素の SRT テキストが編集できる（保存→再描画）

- [ ] **Step 4: コミット**

```bash
git add templates/index.html static/style.css
git commit -m "feat: render .srt files as speaker-colored cue cards"
```

---

## Task 5: 異常系の最終確認

**Files:** （変更なし、動作確認のみ）

- [ ] **Step 1: 崩れた SRT の確認**

任意のリポジトリにテスト用ファイルを作るか、既存の SRT を一時的に編集して以下のパターンを確認:

- 完全に空のファイル: フォールバック「字幕を読み込めませんでした」が表示される
- タイムコード行が欠けた cue を含む: 他の cue は正常表示、崩れた cue はタイムコードが `--` と出る
- 話者プレフィックスがない cue（例: 単に `こんにちは` のみ）: 話者バッジが出ず、左ボーダーは `--border` 色になる
- BOM 付きファイル（`﻿` 先頭）: 1 番目の cue の index がちゃんと抽出される

この Task ではコミットは不要（コード変更なし）。問題が見つかったら該当 Task に戻って修正。

---

## 実装後の確認項目（チェックリスト）

- [ ] `.srt` が一覧から開けてバイナリ扱いではなくなった
- [ ] A: / B: のような対話で話者ごとに色が付く
- [ ] 日本語話者名（例: `さくら`）でも色が付く
- [ ] cue 単位でブックマーク set/jump/解除できる
- [ ] 編集ボタンで素のテキスト編集ができる
- [ ] 既存のテキスト/Markdown 表示が壊れていない（.md と .py を開いて回帰確認）
- [ ] コンソールにエラーが出ていない
