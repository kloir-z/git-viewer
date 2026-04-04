# Folder Favorites Design

## Overview

ファイルタブのディレクトリにお気に入り機能を追加する。ヘッダーの「Git Viewer」タイトルを削除し、代わりにお気に入りフォルダへのジャンプ用ドロップダウンを配置する。

## Requirements

- ファイルタブのディレクトリ一覧で、各フォルダ行に星マーク（☆/★）を表示
- 星マーククリックでお気に入りの登録/解除をトグル
- お気に入りはリポジトリをまたいでグローバルに管理
- ヘッダーにお気に入りドロップダウンを配置し、選択で該当フォルダにジャンプ
- `<h1>Git Viewer</h1>` を削除

## Data Storage

- サーバー側に `favorites.json` を保存（`app.py` と同じディレクトリ）
- 形式: JSON配列

```json
["repo-name/path/to/dir", "category/repo/src/components"]
```

- 各エントリは `リポジトリ名/フォルダパス` の文字列
- リポジトリ名が `category/repo` 形式の場合、エントリは `category/repo/path/to/dir` となる

## Backend API

### GET /api/favorites

お気に入り一覧を返す。

- Response: `["repo/path", ...]`

### POST /api/favorites

お気に入りを追加する。

- Request body: `{"path": "repo/dir/path"}`
- Response: `{"ok": true}`
- 既に登録済みの場合は何もせず成功を返す

### DELETE /api/favorites

お気に入りを解除する。

- Request body: `{"path": "repo/dir/path"}`
- Response: `{"ok": true}`
- 未登録の場合は何もせず成功を返す

## Frontend Changes

### Header

変更前:
```html
<div class="header">
  <h1>Git Viewer</h1>
  <div class="header-controls">
    <select id="repo-select"></select>
    <button id="btn-refresh" onclick="refresh()">↻</button>
  </div>
</div>
```

変更後:
```html
<div class="header">
  <select id="fav-select">
    <option value="">★ Favorites</option>
    <!-- お気に入りエントリ -->
  </select>
  <div class="header-controls">
    <select id="repo-select"></select>
    <button id="btn-refresh" onclick="refresh()">↻</button>
  </div>
</div>
```

- `<h1>Git Viewer</h1>` を `<select id="fav-select">` に置き換え
- 先頭オプション: `★ Favorites`（デフォルト選択、ジャンプなし）
- 各オプション: `リポジトリ名 / フォルダパス` を表示
- 選択時: リポジトリを切替 → ファイルタブに遷移 → 該当フォルダを開く
- ジャンプ後、ドロップダウンは `★ Favorites` に戻す（何度でも選択可能にするため）

### File Tab - Star Icons

- ディレクトリ行のフォルダアイコン横に星マークを表示
- お気に入り済み: ★（黄色 `var(--yellow)`）
- 未登録: ☆（グレー `var(--text-dim)`）
- クリックで POST/DELETE API を呼び出し → 星の表示を切替 → ヘッダードロップダウンを再描画
- 星マークのクリックはフォルダへの移動を発火させない（イベント伝播を停止）

## State Management

- `let favorites = []` — グローバル変数でお気に入り一覧を保持
- `init()` 時に `GET /api/favorites` で取得
- お気に入り変更時にグローバル変数とドロップダウンの両方を更新

## Interaction Flow

```
1. ページ読込 → GET /api/favorites → favorites変数に保存 → ドロップダウン描画
2. ファイルタブでフォルダ一覧表示 → favorites変数を参照して★/☆を描画
3. ★クリック → POST or DELETE /api/favorites → favorites変数を更新 → ★表示切替 → ドロップダウン再描画
4. ドロップダウン選択 → repoSelect.value切替 → ファイルタブに遷移 → renderFiles(path)
```
