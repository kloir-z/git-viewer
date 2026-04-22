# Markdown Sentence-level Bookmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Markdown プレビューのしおり対象を、現在の「ブロック要素単位」から「文単位」に細かくする。長い段落を句点ごとにダブルクリックでしおり化できるようにする。

**Architecture:** `templates/index.html` の `showBlob()` 内、Markdown 分岐の DOM 後処理を差し替える。`marked.parse()` 直後の HTML を再帰的に走査し、`<p> <li> <th> <td>` の中身を文末（`。！？` および空白前の `.!?`）で `<span class="bm-target" data-bm-idx="N">` にラップする。見出し・コードブロックは 1 単位のまま。CSS にインライン span 用ハイライトを追加。

**Tech Stack:** vanilla JS（既存ファイル `templates/index.html`、`static/style.css`）。バックエンド変更なし。テストインフラは存在しないので確認は手動（既存プラン群と同じ）。

Spec: `docs/superpowers/specs/2026-04-22-md-sentence-bookmark-design.md`

---

### Task 1: インラインしおり用 CSS を追加

**Files:**
- Modify: `static/style.css:428-432`

- [ ] **Step 1: 既存の `.markdown-body .bookmarked` ルールを差し替え**

現状 (`static/style.css:428-432`):

```css
.markdown-body .bookmarked {
  border-left: 4px solid #f0c04a;
  padding-left: 8px;
  background: rgba(240, 192, 74, 0.08);
}
```

これを以下に置き換える:

```css
/* ブロック単位（見出し・コードブロック）の従来表示 */
.markdown-body :not(span).bookmarked {
  border-left: 4px solid #f0c04a;
  padding-left: 8px;
  background: rgba(240, 192, 74, 0.08);
}
/* インライン文単位の表示 */
.markdown-body span.bookmarked {
  background: rgba(240, 192, 74, 0.25);
  border-radius: 2px;
  box-shadow: 0 0 0 2px rgba(240, 192, 74, 0.25);
}
```

- [ ] **Step 2: 動作確認はタスク 4 でまとめて行う**

ここではコミットしない（次タスクと一緒にコミット）。

---

### Task 2: 文単位分割ヘルパを追加

**Files:**
- Modify: `templates/index.html`（`bookmarkTarget` の直前、つまり 600 行目付近に新規関数群を追加）

- [ ] **Step 1: ヘルパ関数を追加**

`function bookmarkTarget(blobView, type, index) {` の直前に以下を挿入する:

```js
// ----- Markdown 文単位しおり -----

// 句点判定: 全角は常に文末。半角 . ! ? は後続が空白/末尾なら文末。
const MD_SENT_END = /[。！？]|[.!?](?=\s|$)/g;

// 文単位に分割しないコンテナ（中身を再帰)
const MD_CONTAINER_TAGS = new Set(['UL','OL','BLOCKQUOTE','TABLE','THEAD','TBODY','TR']);
// 1 単位のままで data-bm-idx を付ける（中身は再帰しない）
const MD_ATOMIC_TAGS = new Set(['H1','H2','H3','H4','H5','H6','PRE','HR']);
// 文単位に分割する
const MD_SPLIT_TAGS = new Set(['P','LI','TH','TD']);

function isBlockChild(node) {
  if (node.nodeType !== 1) return false;
  const t = node.tagName;
  return MD_CONTAINER_TAGS.has(t) || MD_ATOMIC_TAGS.has(t) || MD_SPLIT_TAGS.has(t);
}

// テキストノード列内で文末位置を見つけ、文ごとに span でラップする。
// nodes: parent の連続するインライン子ノード列（テキスト + インライン要素）
// parent: ラップ後の span を挿入する親要素
// ctx: { counter: number } — 連番を進める
function wrapInlineRunIntoSentences(parent, nodes, ctx) {
  // 1) テキストノード内の文末で splitText し、句点直後で「フラッシュ点」を作る
  // フラッシュ点 = そのノードまでで現在の文 span を確定する境界
  const flushAfter = new Set(); // 各境界でラップ対象に含める末尾ノード(参照)

  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n.nodeType !== 3) continue; // テキストノードのみ
    let text = n.nodeValue;
    let offsetBase = 0;
    let cur = n;
    MD_SENT_END.lastIndex = 0;
    let m;
    while ((m = MD_SENT_END.exec(text)) !== null) {
      const cut = m.index + m[0].length - offsetBase;
      if (cut < cur.nodeValue.length) {
        const tail = cur.splitText(cut);
        flushAfter.add(cur);
        // 後続イテレーション用に nodes 配列にも tail を挿入
        nodes.splice(i + 1, 0, tail);
        // 次の検索は tail 側を新しい起点にする
        offsetBase = m.index + m[0].length;
        cur = tail;
        text = text; // 元の text に対して continue
      } else {
        // ちょうどノード末尾で文末
        flushAfter.add(cur);
      }
    }
  }

  // 2) nodes を順に走査し、文末ノードまでを 1 spans として束ねる
  const spans = [];
  let bucket = [];
  for (const n of nodes) {
    bucket.push(n);
    if (n.nodeType === 3 && flushAfter.has(n)) {
      spans.push(bucket);
      bucket = [];
    }
  }
  if (bucket.length > 0) spans.push(bucket);

  // 3) 空白だけの span は前の span に併合（行末の改行などが単独 span にならないように）
  const merged = [];
  for (const group of spans) {
    const onlyWs = group.every(n => n.nodeType === 3 && /^\s*$/.test(n.nodeValue));
    if (onlyWs && merged.length > 0) {
      merged[merged.length - 1].push(...group);
    } else {
      merged.push(group);
    }
  }

  // 4) 実際に DOM を span で置換
  // 最初の要素の直前に span を挿入し、グループ内の各ノードを span に move
  const firstAnchor = nodes[0];
  if (!firstAnchor) return;
  for (const group of merged) {
    const span = document.createElement('span');
    span.className = 'bm-target';
    span.setAttribute('data-bm-idx', String(ctx.counter++));
    parent.insertBefore(span, group[0]);
    for (const n of group) span.appendChild(n);
  }
}

function markAtomic(el, ctx) {
  el.setAttribute('data-bm-idx', String(ctx.counter++));
  el.classList.add('bm-target');
}

function splitElementIntoSentences(parent, ctx) {
  // parent の子を走査。連続するインラインノード列を 1 つのまとまりとして
  // wrapInlineRunIntoSentences に渡し、ブロック子に出会ったら processMdBlock に再帰。
  const children = [...parent.childNodes];
  let inlineRun = [];
  for (const child of children) {
    if (isBlockChild(child)) {
      if (inlineRun.length > 0) {
        wrapInlineRunIntoSentences(parent, inlineRun, ctx);
        inlineRun = [];
      }
      processMdBlock(child, ctx);
    } else {
      inlineRun.push(child);
    }
  }
  if (inlineRun.length > 0) {
    wrapInlineRunIntoSentences(parent, inlineRun, ctx);
  }
}

function processMdBlock(node, ctx) {
  if (node.nodeType !== 1) return;
  const tag = node.tagName;
  if (MD_CONTAINER_TAGS.has(tag)) {
    for (const child of [...node.children]) processMdBlock(child, ctx);
    return;
  }
  if (MD_ATOMIC_TAGS.has(tag)) {
    markAtomic(node, ctx);
    return;
  }
  if (MD_SPLIT_TAGS.has(tag)) {
    splitElementIntoSentences(node, ctx);
    return;
  }
  // それ以外は素通り（marked が出力する想定外タグ。安全側に倒し何もしない）
}

function splitMdIntoSentences(root) {
  const ctx = { counter: 0 };
  for (const child of [...root.children]) processMdBlock(child, ctx);
  return ctx.counter;
}
```

- [ ] **Step 2: シンタックスチェック**

ブラウザで templates/index.html を読み込めば JS パースエラーは即座に出る。タスク 4 で動作確認するためここではコミットしない。

---

### Task 3: `showBlob()` の md 分岐を新ヘルパに差し替え

**Files:**
- Modify: `templates/index.html:745-761`

- [ ] **Step 1: 既存の「UL/OL の LI を個別ターゲットに展開」ロジックを置換**

現状 (`templates/index.html:745-761`):

```js
    // UL/OL は中の LI を個別のしおり対象に展開（大きなリスト全体が 1 つのしおりになるのを避ける）
    const targets = [];
    for (const child of mdBody.children) {
      if (child.tagName === 'UL' || child.tagName === 'OL') {
        for (const li of child.children) targets.push(li);
      } else {
        targets.push(child);
      }
    }
    targets.forEach((el, idx) => {
      el.setAttribute('data-bm-idx', String(idx));
      el.classList.add('bm-target');
      el.addEventListener('dblclick', (e) => {
        if (e.target.closest('a, button, input, select, textarea, img')) return;
        onBookmarkClick(path, 'md', idx);
      });
    });
    const bm = await fetchBookmark(path);
    applyBookmarkUi(blobView, bm);
```

これを以下に置き換える:

```js
    // 文単位 / 見出し単位 / コードブロック単位で data-bm-idx を付与
    splitMdIntoSentences(mdBody);
    mdBody.querySelectorAll('[data-bm-idx]').forEach(el => {
      const idx = Number(el.getAttribute('data-bm-idx'));
      el.addEventListener('dblclick', (e) => {
        if (e.target.closest('a, button, input, select, textarea, img')) return;
        onBookmarkClick(path, 'md', idx);
      });
    });
    const bm = await fetchBookmark(path);
    applyBookmarkUi(blobView, bm);
```

---

### Task 4: 動作確認 + コミット

- [ ] **Step 1: サービスを再起動**

Windows (開発機):

```
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

- [ ] **Step 2: ブラウザで Markdown プレビューを開いて手動確認**

確認項目:

1. 句点（`。`）を 2 つ以上含む段落を開く → 各文の上にカーソルを合わせるとハイライト範囲が文ごとに切り替わる
2. 文をダブルクリック → その文だけ黄色背景でハイライトされる
3. 同じ文を再ダブルクリック → 解除される
4. 別の文をダブルクリック → 移動する（しおりは 1 ファイル 1 個）
5. リスト項目内に `これは一文目。これは二文目。` のような複数文がある md を表示 → 文ごとにしおりが付く
6. URL を含む段落（例: `https://example.com/path` を含む文）→ URL 内の `.` で分割されない
7. 小数 `3.14` を含む段落 → 分割されない
8. 英文 `Hello. World.` を含む段落 → `Hello.` と `World.` で分割される
9. 見出し（`# 見出し`）→ 1 行全体に黄色帯（既存表示）が出る
10. コードブロック → ブロック全体に黄色帯（既存表示）が出る、内部の文では分割されない
11. リンクを含む文 `これは [link](url) を含む文。` → リンクごとしおり可能
12. しおり保存 → ページ再読込 → ツールバーの「しおりへ」ボタンで該当文へジャンプできる

- [ ] **Step 3: 既知の妥協点も確認**

- 既存しおり付き md を開いた場合: インデックスがずれる可能性あり。「しおりへ」ボタンが表示されないだけで画面は崩れない
- インライン要素が文末を跨ぐ稀なケース（`<a>本文。続き</a>` のようなリンク内に句点）: span がネストできずリンク全体が前文に含まれる。実用上稀なので許容

- [ ] **Step 4: コミット**

```bash
git add templates/index.html static/style.css
git commit -m "$(cat <<'EOF'
feat: bookmark Markdown prose at the sentence level

paragraphs and list items split inline content at 。！？ and at .!?
followed by whitespace, wrapping each sentence in a span that takes
the bookmark. Headings and code blocks remain whole. Existing
bookmarks may drift since the index space changed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```
