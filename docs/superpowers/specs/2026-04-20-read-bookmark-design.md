# Read Bookmark Design

## Overview

テキスト/コード/Markdown プレビューに「どこまで読んだか」を示すしおり機能を追加する。1ファイルにつき1つのしおりを保存でき、再オープン時はツールバーの「しおりへ」ボタンから位置に移動できる。

## Requirements

- 対象ファイル種別: Markdown (.md) とテキスト/コード
- Markdown はブロック要素（段落・見出し・リスト等）単位でクリックしてセット
- テキスト/コードは行番号ガターをクリックして行単位でセット
- マーカーは行/ブロック左端にアイコン＋帯で表示
- 再オープン時は自動スクロールしない。ツールバーに「しおりへ」ボタンを設置し、クリックでジャンプ
- 1ファイルにつきしおりは1つだけ（しおり方式）。同位置の再クリックで解除、別位置クリックで移動
- 保存はサーバー側 `bookmarks.json`

## Data Storage

プロジェクトルート（`app.py` と同じディレクトリ）に `bookmarks.json` を保存する。`favorites.json` と同じパターンで管理する。`.gitignore` には `bookmarks.json` と併せて `favorites.json` も追加する（現状 favorites.json は untracked のまま放置されているため、このタイミングで揃える）。

形式:

```json
{
  "repo-name": {
    "path/to/file.md": {"type": "md",   "index": 7},
    "src/app.py":      {"type": "text", "index": 142}
  },
  "category/repo": {
    "README.md": {"type": "md", "index": 0}
  }
}
```

- キー1段目: リポジトリ名（`category/repo` 形式を含む）
- キー2段目: リポジトリ内の相対パス
- `type`: `"md"` (Markdown ブロックインデックス、0始まり) または `"text"` (行番号、1始まり)
- `index`: 整数

起動時に読込、更新時は `write_text` で書き出す（`write_favorites` と同じ素朴な書き込み。atomic write は現状行っておらず、本機能でも導入しない）。破損していたら空辞書で起動する。

## Backend API (app.py)

すべてのエンドポイントで `valid_repo(repo)` を呼び、`path` に対しても `..` を含まないことをチェックする（`/api/blob` と同じ方針）。

### GET /api/bookmark

指定ファイルのしおりを取得する。

- Query: `repo=<name>&path=<file>`
- Response: `{"type": "md"|"text", "index": N}` または `{}`（未設定時）

### PUT /api/bookmark

しおりを設定/更新する。

- Request body: `{"repo": "...", "path": "...", "type": "md"|"text", "index": N}`
- Response: `{"ok": true}`
- 同一 repo+path への再 PUT は上書き

### DELETE /api/bookmark

しおりを削除する。

- Request body: `{"repo": "...", "path": "..."}`（favorites API と同じ body 方式で統一）
- Response: `{"ok": true}`
- 未設定のしおりに対する DELETE も 200 を返す

## Frontend (templates/index.html)

### Markdown プレビュー

- `marked.parse()` 後、`#md-body` の直下の子要素に順番に `data-bm-idx="0..N"` を付与
- 各ブロックに CSS `:hover` で左マージンに薄いしおりアイコン表示（目立ちすぎない）
- クリックでサーバーに PUT / 同じ所なら DELETE
- しおり済みブロックには `.bookmarked` クラスを付与し、左4px帯＋アイコン常時表示

### テキスト/コード プレビュー

現状 `<pre><code>` に全文を渡して hljs で一括ハイライトしている部分を以下に変更する:

1. `hljs.highlight(content, {language})` を使い、ハイライト結果 HTML 文字列を取得
2. 改行で分割する際、`<span>` タグが複数行にまたがる（複数行コメント等）と単純な split では壊れるため、行末で未閉じタグを閉じ、行頭で再開する処理を行う。軽量な実装として `hljs.lineNumbersBlock` の代替相当を自前で実装する（ライブラリは追加しない）
3. 2列 flex レイアウトで行番号ガター `.code-gutter` と本文 `.code-line` を生成
4. 各行（ガターと本文の両方）に `data-bm-line="N"` (1始まり) を付与

- ガター列のクリックでセット/解除。本文クリックはテキスト選択のため無反応
- しおり行は `.bookmarked` クラスで左帯＋行番号ハイライト

### ツールバー

セクションヘッダー（ファイル名を表示している部分、既存 `btn-edit` と同じ場所）の右側に「しおりへ」ボタン（📑 アイコン＋ラベル）を配置する。

- しおりあり: ボタン表示、クリックで該当要素に `scrollIntoView({block: 'center'})`
- しおりなし: ボタン非表示（セットはプレビュー領域側で行う）

## Data Flow

```
showBlob(path)
  ├─ fetchJson(blobUrl)                  (既存)
  ├─ fetchJson(/api/bookmark?repo&path)  (並行取得)
  ├─ レンダリング (md or code)
  ├─ bookmark あり → 該当要素に .bookmarked、ジャンプボタン表示
  └─ クリックハンドラ登録

クリック時:
  既存しおりと同一位置 → DELETE  → .bookmarked 除去、ボタン非表示
  異なる位置           → PUT     → 旧位置 .bookmarked 除去、新位置に付与
```

### 編集モード中の挙動

`editBlob` は `blob-view` 全体を textarea に置き換えるため、編集中はしおり UI（マーカー、ジャンプボタン）は表示されない。保存またはキャンセル時に `showBlob` が再実行されてしおり UI が復元される。しおりデータ自体は保持される。

## Error Handling

- しおり取得失敗: silent（`console.error` のみ）。プレビュー自体は継続
- しおり保存/削除失敗: 小さなトースト通知1回
- `bookmarks.json` 破損: サーバーは空辞書で起動
- ファイル編集でインデックスが要素数を超えた場合: マーカー描画をスキップ（`.bookmarked` を付けない）。しおりデータ自体は残し、ユーザーが新しい位置をセットし直すまで保持

## Testing

- 手動テスト
  - Markdown で段落/見出し/リストそれぞれにセット→再読込→ジャンプ
  - コードで行セット→再読込→ジャンプ
  - 同位置再クリックで解除
  - 別位置クリックで移動
  - ファイル編集後に古いしおりが残っても他要素に干渉しないこと
  - `bookmarks.json` を手で破損させても起動すること

## Out of Scope

- 複数しおり（ブックマーク方式）
- しおり一覧ビュー
- テキストハッシュによる編集耐性
- 自動スクロール位置保存

## Impact

- `app.py`: 新規 API ハンドラ3本、`bookmarks.json` I/O ヘルパー
- `templates/index.html`: `showBlob` 内の Markdown/コード分岐を拡張、クリックハンドラ、ジャンプボタン。コードレンダリングは行ガター方式に書き換え
- `static/style.css`: `.bookmarked`、`.code-gutter`、`.code-line`、ホバー時のしおりアイコン
- `.gitignore`: `bookmarks.json` と `favorites.json` を追加
