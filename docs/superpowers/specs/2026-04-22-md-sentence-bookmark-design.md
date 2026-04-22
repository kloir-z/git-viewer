# Markdown Sentence-level Bookmark Design

## Overview

Markdown プレビューのしおり対象を、現状の「ブロック要素（段落・リスト項目）単位」から「文単位」に細かくする。1 段落が長文の場合に段落丸ごとが 1 しおりになってしまう問題を解消する。md ソースには手を加えず、`marked.parse()` 直後の DOM 後処理だけで対応する。

## Requirements

- `<p>` `<li>` `<blockquote>` 内の段落 `<th>` `<td>` の中身を、文単位の `<span class="bm-target" data-bm-idx="N">` に分割する
- 見出し `<h1>`〜`<h6>` は 1 単位のまま（短いため文分割不要）
- `<pre>` `<code>` は 1 単位のまま（コード内に句点があっても分割しない）
- 句点判定:
  - `。` `！` `？` は常に文末
  - `.` `!` `?` は「直後が空白・改行・要素末尾の場合のみ」文末（`3.14`, `https://example.com/foo.bar`, `e.g.` 等の誤検出を避ける）
- インライン要素（`<a>` `<code>` `<em>` `<strong>` `<img>` 等）は文の途中にあれば、その文の span 内に丸ごと含める
- ダブルクリックで しおりセット/解除（既存 UI 踏襲）
- インデックス連番 `data-bm-idx` は文 span 単位で振る（`<li>` が 3 文を含むなら `<li>` 自体には付かず、内部の 3 個の span に 0,1,2 が振られる）

## Non-goals

- ソース markdown の編集や保存形式の変更
- 言語別（英語/日本語）のより高度な文境界検出（NLP 不要、句読点ベースで十分）
- インライン要素が文末を跨ぐケース（`<a>本文。続き</a>`）の完全対応 — span をネストできないため、リンク全体を前文に含めて妥協する（実用上稀）

## Architecture

実装範囲は `templates/index.html` の `showBlob()` 内 Markdown 分岐のみ（現状 745〜761 行付近の「`<li>` を個別ターゲットに展開」のロジック）。

### 処理フロー

1. `marked.parse(data.content)` で HTML を生成（既存）
2. `mdBody.innerHTML` にセット（既存）
3. `rewriteMdAssets`, `hljs.highlightElement` を適用（既存）
4. **新規**: `splitMdIntoSentences(mdBody)` を呼び出し、文単位 span に分割しつつ `data-bm-idx` を連番で付与
5. 全 `[data-bm-idx]` 要素に dblclick リスナーを付け、`onBookmarkClick(path, 'md', idx)` を呼ぶ（既存と同じ）
6. `fetchBookmark` → `applyBookmarkUi` で復元（既存）

### `splitMdIntoSentences(root)` の動作

```
let counter = 0;
walk(root):
  if 要素が <pre>, <code>, <h1>〜<h6>:
    要素全体に data-bm-idx=counter++ を付け、子は再帰しない
  elif 要素が <p>, <li>, <blockquote>, <th>, <td>:
    splitElementIntoSentences(要素, counter) を実行し counter を進める
    （要素自体には data-bm-idx を付けない）
    子要素については再帰しない（既に処理済み）
  else:
    子要素について再帰
```

`<blockquote>` 内に `<p>` がある場合は `<p>` 側で分割する（`<blockquote>` 自体は素通り）。実装上は再帰時に `<blockquote>` の子を辿るパスでよい。

### `splitElementIntoSentences(el, startIdx)` の動作

DOM ベースで以下を行う:

1. `el` の全テキストノードを TreeWalker で取得し、各テキストノード内の文末位置を検出
2. 文末位置でテキストノードを分割（`Text.splitText(offset)` を使用）
3. 文末を含むテキストノード（およびその後ろの空白テキストノード）までを「1 文の境界」とし、それまでに出現した子ノード（テキスト・インライン要素）を `<span class="bm-target" data-bm-idx="N">` でラップする
4. 最後の文末以降に余ったノードがあれば、それも 1 個の span にまとめる
5. 文が 1 つしか検出されなかった場合（句点がない短文）は、要素の中身全体を 1 個の span でラップする
6. 各 span の `data-bm-idx` は引数 `startIdx` から連番で振り、最終的に使った数を呼び出し元に返す

### 句点検出の正規表現

```js
// グローバル検索で文末位置を列挙
const SENT_END = /[。！？]|[.!?](?=\s|$)/g;
```

- `[。！？]` は単独で文末
- `[.!?]` は後続が空白文字または末尾の時のみ文末
- 文末位置は「マッチ末尾の次の文字位置」を採用（句読点自体は前の文に含める）
- テキストノードを跨いで文末判定する必要はない（句読点は単一テキストノード内に収まる前提。インライン要素直前で文が終わるケースは句読点もそのテキストノードにあるため成立）

### 既存関数への影響

- `bookmarkTarget(blobView, type, index)` (templates/index.html:601): 変更不要。`md` 型は `[data-bm-idx="N"]` で querySelector するため、対象が `<li>` から `<span>` に変わっても動作する
- `applyBookmarkUi`, `onBookmarkClick`, `jumpToBookmark`: 変更不要

## Style

現在 `static/style.css:428-432` の `.markdown-body .bookmarked` は block 前提で `border-left: 4px solid #f0c04a; padding-left: 8px; background: rgba(240, 192, 74, 0.08);` が指定されている。`<span>`（インライン）に適用すると左帯が「文頭の最初の行頭」だけに出てしまい意図と合わないので、span 用の指定を追加する。

セレクタを以下のように分ける:

```css
/* インライン文単位: 文字背景のみ */
.markdown-body span.bookmarked {
  background: rgba(240, 192, 74, 0.25);
  border-radius: 2px;
  box-shadow: 0 0 0 2px rgba(240, 192, 74, 0.25);
}

/* ブロック単位（見出し・コードブロック）は従来どおり */
.markdown-body :not(span).bookmarked {
  border-left: 4px solid #f0c04a;
  padding-left: 8px;
  background: rgba(240, 192, 74, 0.08);
}
```

既存の `.markdown-body .bookmarked` 指定は `:not(span)` 版に置き換える。

## Backward compatibility

既存しおり (`bookmarks.json` 内の `type: "md"`, 旧 index) は新方式ではインデックス体系がズレる。これは「リスト項目を個別ターゲット化」した時 (3f6e14f) と同じ既知の挙動で、ユーザーは付け直しが必要。マイグレーションは行わない。

## Testing

手動確認項目:
1. 句点を含む長段落で、句点ごとにダブルクリックしてしおりがセット/解除できる
2. リスト項目内に複数文がある場合、文ごとに個別にしおりが付く
3. URL や小数点 (`3.14`) を含む段落で誤分割されない
4. リンク・強調・インラインコードを含む文がしおり可能
5. 見出しは 1 単位のままダブルクリックでしおりが付く
6. コードブロック内は分割されず、ブロック全体が 1 単位
7. しおり保存後、再オープンで「しおりへ」ボタンから正しい文に戻れる
8. 既存しおりがある md ファイルで開いて、ズレが発生しても画面が崩れない（位置が合わなければ「しおりへ」ボタンが消えるだけ）
