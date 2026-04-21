# SRT Rendering Design

## Overview

`.srt` 字幕ファイルを、現状のバイナリ扱い（ダウンロードリンクのみ）から、cue 単位のカードリストとして表示できるようにする。aivis 系リポジトリの対話 SRT を念頭に、話者プレフィックスを検出して色分けする。既存のしおり機構（Markdown と同じブロック方式）で cue 単位のブックマークをサポートする。

## Requirements

- `.srt` をテキストとして `/api/blob` が JSON を返す（現状はバイナリで送出）
- `showBlob` に SRT 専用ブランチを追加し、cue ごとのカードリストで描画する
- 各カードは `[番号] + [開始 → 終了] + [話者バッジ] + [本文]` を表示
- 本文1行目が `^([^\s:：]{1,16})[:：]\s` にマッチしたら話者として抽出し、本文からは取り除く
- 話者ごとに stable な色（話者文字列のハッシュから HSL）で左ボーダーと話者バッジを着色
- cue 単位のブックマークを既存の `type: "md"` で保存（index は cue 配列のインデックス、0 始まり）
- 既存の「編集」ボタンは維持し、素の SRT テキストを textarea で編集できる
- 崩れた cue（タイムコード行が読めない等）もテキストは表示する（落とさない）

## Backend (app.py)

- `TEXT_EXTS` に `'.srt'` を追加するのみ。これで既存の `/api/blob` が UTF-8 の JSON で `content` を返すようになる。

サーバー側 API の追加・変更はなし。

## Parser

`parseSrt(text)` は以下の配列を返す純粋関数（フロントエンドに実装）:

```
[{ index: "1", start: "00:00:00,000", end: "00:00:04,869",
   speaker: "A", text: "こんにちはー！..." }, ...]
```

アルゴリズム:

1. `\r\n` を `\n` に正規化し、`\n\s*\n+` で cue ブロックに分割
2. 各ブロックを行単位に分解
3. 先頭行が数字なら `index` として採用、そうでなければ `index = ""`
4. 次行がタイムコードパターン `(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)` にマッチすれば `start` / `end` を抽出、マッチしなければ `start = end = ""` とし、その行も本文に含める
5. 残り行を `\n` で結合して本文にする
6. 本文先頭行に `^([^\s:：]{1,16})[:：]\s*` があれば `speaker` として抽出し、本文から除去。なければ `speaker = ""`

空ファイルや cue 0 件の場合は空配列を返す。

## Frontend (templates/index.html)

### TEXT_EXTS への追加

JS 側の `TEXT_EXTS` 配列にも `'srt'` を追加。これを忘れると `showBlob` のバイナリ早期リターンに落ちる。

### showBlob の分岐

既存の Markdown / テキスト分岐と並べて、`fileExt === '.srt'` の分岐を追加する。

レンダリング:

```html
<div class="section-header">{path}<span id="bm-jump-btn"></span>
  <button class="btn-edit" onclick="editBlob(...)">編集</button>
</div>
<div class="blob-container srt-container">
  <div class="srt-cue bm-target" data-bm-idx="0" style="--speaker-color: hsl(...)">
    <div class="srt-meta">
      <span class="srt-index">1</span>
      <span class="srt-time">00:00:00,000 → 00:00:04,869</span>
      <span class="srt-speaker">A</span>
    </div>
    <div class="srt-text">こんにちはー！...</div>
  </div>
  ...
</div>
```

- 各カードに `data-bm-idx` と `.bm-target` を付与
- dblclick ハンドラで `onBookmarkClick(path, 'md', idx)` を呼ぶ（Markdown と同じ）
- リンク等の上では無反応にする条件分岐は Markdown と同じ（`e.target.closest('a, button, input, select, textarea, img')` を除外）
- 話者が空の cue は speaker バッジを出さず、左ボーダーは `--border` 色にフォールバック
- 話者色は安定ハッシュ → HSL(`hue = hash % 360`, `saturation = 55%`, `lightness = 60%`)。ダーク背景上で視認できる中間輝度に固定
- タイムコード表示は `,` と `.` を両方許容するが、表示時は原文のまま（正規化しない）

### ブックマークとの統合

- `bookmarkTarget(blobView, 'md', index)` は既存実装で `[data-bm-idx="<index>"]` を取るので、手を加えずに SRT カードも対象になる
- `applyBookmarkUi` / `.bookmarked` の CSS も Markdown と同じルールで動く（左帯＋薄背景）

### 既存分岐との関係

現状 `showBlob` 後半は `if (fileExt === '.md') { ... } else { /* text/code */ }` になっている。`.srt` を `TEXT_EXTS` に入れたままだと `else` 側のコード風表示が走るため、`.md` 分岐の**後ろ**・text/code `else` の**前**に `else if (fileExt === '.srt')` 分岐を追加する。

## Styling (static/style.css)

追加するクラス:

- `.srt-container` — 縦にカードを並べる。`display: flex; flex-direction: column; gap: 8px; padding: 8px`
- `.srt-cue` — 背景 `var(--surface)`、左ボーダー `4px solid var(--speaker-color, var(--border))`、角丸、`padding: 8px 12px`
- `.srt-meta` — 横並び。番号・時刻は等幅＋muted 色。話者バッジは `--speaker-color` 背景で白文字
- `.srt-index` — `color: var(--text-muted); font-family: monospace; font-size: 11px`
- `.srt-time` — `color: var(--text-muted); font-family: monospace; font-size: 11px`
- `.srt-speaker` — `background: var(--speaker-color); color: #fff; padding: 0 6px; border-radius: 10px; font-size: 11px; font-weight: 600`
- `.srt-text` — `white-space: pre-wrap; font-size: 14px; line-height: 1.5` で改行保持

既存の `.bm-target` / `.bookmarked` は Markdown と共通で適用される。SRT カード向けの追加調整は不要。

## Error Handling

- `parseSrt` は完全に防御的。どこかで正規表現が外れても全体を落とさず、崩れた cue もテキストだけ表示
- パース結果が 0 件: 「字幕を読み込めませんでした」のメッセージを出しつつ、素の content を pre で並べるフォールバック（編集導線は維持）
- BOM は `content.replace(/^﻿/, '')` で除去してからパース
- 文字コードは既存の `/api/blob` が UTF-8 固定で読むため、Shift_JIS の SRT は文字化けしうるが現状は対象外（他のテキストファイルと同じ扱い）

## Testing

手動テスト:

- aivis 系の対話 SRT（A/B 交互）を開いて、話者ごとに色が分かれること
- 日本語の話者名（例: `さくら:`）でも色が安定して付くこと
- 話者プレフィックスがない字幕でも読めること
- 崩れた cue（タイムコード行が欠落）を含んでも他の cue が落ちないこと
- BOM 付き SRT が先頭から崩れないこと
- cue を dblclick でブックマーク設定→再読込→「しおりへ」ジャンプ
- 同じ cue を再 dblclick で解除
- 「編集」ボタンで素のテキストを編集して保存→再描画されること
- 空ファイルやパース不能ファイルでフォールバック表示されること

## Out of Scope

- 音声同期再生（同名 `.mp3` / `.wav` の検出、再生位置に応じた cue ハイライト）
- SRT 内インラインタグ（`<i>`, `<b>` 等）の解釈
- WebVTT (`.vtt`) 対応
- SRT パース結果の検証（番号順序・時刻整合など）
- 話者色のユーザー設定

## Impact

- `app.py`: `TEXT_EXTS` に `.srt` を追加するのみ
- `templates/index.html`:
  - JS 側 `TEXT_EXTS` に `'srt'` 追加
  - `parseSrt(text)` 関数を追加
  - `showBlob` に SRT 分岐を追加（Markdown 分岐の手前）
  - SRT カードに dblclick ハンドラを登録（Markdown と同じ `onBookmarkClick(path, 'md', idx)`）
- `static/style.css`: `.srt-container` / `.srt-cue` / `.srt-meta` / `.srt-index` / `.srt-time` / `.srt-speaker` / `.srt-text`
