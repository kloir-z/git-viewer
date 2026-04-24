# Audio ↔ SRT 同期表示 Design

## Overview

`.mp3` / `.wav` を開いたとき、同ディレクトリに同名の `.srt` があれば、再生バーと再生履歴の下に字幕カードリストを描画し、再生位置に対応する cue をハイライトする。長尺の対話音声を聞きながら該当箇所の字幕を自動追従スクロールで確認できるようにする。

既存の `parseSrt()` / `speakerColor()` / `.srt-cue` 系スタイルを再利用し、バックエンドは無変更。

## Requirements

- `.mp3` / `.wav` を `showBlob` で表示したとき、同ディレクトリの同名 `.srt` を自動検出して埋め込み表示する
- 検出候補は 2 つ: `foo.mp3` → `foo.srt`（優先）、`foo.mp3.srt`（フォールバック）
- どちらも存在しない場合は字幕領域を空のままにし、エラーや警告は出さない
- 再生位置に対応する cue に `.current` クラスを付け、視認可能な強調表示をする
- 現 cue が変わったら自動で `scrollIntoView({block:'center', behavior:'smooth'})` で追従する
- ユーザーが手動スクロールしたら追従を一時停止し、5 秒後に復帰する。音声シーク時は即復帰する
- SRT 領域は `max-height: 60vh` の内部スクロール領域とし、再生バー・再生履歴が常に画面内に残るようにする
- 音声埋め込みの SRT は **表示専用**。dblclick ブックマークは無効。「編集」ボタンも出さない

## Non-Goals

- cue クリックでの再生位置ジャンプ
- 音声埋め込み SRT のブックマーク・編集（単独で `.srt` を開けば既存機能が使える）
- WebVTT (`.vtt`) 対応
- 複数言語字幕の切替
- 字幕検索 UI

## Backend

変更なし。`/api/blob` は既に `.srt` を UTF-8 テキストの JSON (`{content: ...}`) として返す実装（SRT Rendering 設計で導入済み）。同名 SRT の存在確認も GET で行い、404 を候補スキップのシグナルとして使う。

## Frontend

### 検出

```js
async function loadSiblingSrt(audioPath) {
  const slash = audioPath.lastIndexOf('/');
  const dir = slash >= 0 ? audioPath.slice(0, slash + 1) : '';
  const base = slash >= 0 ? audioPath.slice(slash + 1) : audioPath;
  const stem = base.replace(/\.[^./]+$/, '');
  const candidates = [dir + stem + '.srt', dir + base + '.srt'];
  for (const p of candidates) {
    try {
      const data = await fetchJson(
        `/api/blob?repo=${encodeURIComponent(currentRepo)}&path=${encodeURIComponent(p)}`
      );
      if (data && typeof data.content === 'string') return { path: p, text: data.content };
    } catch (_) { /* 404 等は次の候補へ */ }
  }
  return null;
}
```

- `foo.srt` を先、`foo.mp3.srt` を後の優先順で試行
- いずれも失敗なら `null`。呼び元は何も描画しない

### DOM 構造

`showBlob` の audio 分岐を以下で差し替える:

```html
<div class="section-header">{path}</div>
<div class="blob-container">
  <audio id="audio-player" controls preload="metadata" src="{blobUrl}" style="width:100%;"></audio>
  <div id="playback-log-list" class="playback-log"></div>
  <div id="srt-embed" class="srt-embed-container"></div>
</div>
```

`loadSiblingSrt` が成功したら `#srt-embed` に以下を挿入:

```html
<div class="srt-embed-header">字幕 (<span class="srt-embed-filename">foo.srt</span>)</div>
<div class="srt-cue" data-start="0" data-end="4.869" style="--speaker-color: hsl(210 55% 60%);">
  <div class="srt-meta">
    <span class="srt-time">00:00:00,000 → 00:00:04,869</span>
    <span class="srt-speaker">A</span>
  </div>
  <div class="srt-text">こんにちはー！...</div>
</div>
...
```

- 既存 `parseSrt()` / `speakerColor()` を再利用
- `.srt-index`（番号）は出さない — 軽量ビューとして省略
- `data-bm-idx` / dblclick ハンドラ / 「編集」ボタンは**付けない**
- 各 cue に `data-start` / `data-end`（秒、小数 3 桁）を付与してデバッグを容易にする

### 秒変換

```js
function timeToSeconds(tc) {
  if (!tc) return NaN;
  const m = tc.match(/^(\d+):(\d+):(\d+)[,.](\d+)$/);
  if (!m) return NaN;
  return (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3]) + (+m[4]) / Math.pow(10, m[4].length);
}
```

- `,` / `.` 両対応
- ミリ秒桁数は任意（通常 3 桁、稀に異桁）
- 不正な `tc` は `NaN` を返す → `findIdx` の比較 (`t >= NaN` は `false`) で自動的にスキップされる

### setupSrtEmbed

```js
async function setupSrtEmbed(audioPath) {
  const container = document.getElementById('srt-embed');
  const audio = document.getElementById('audio-player');
  if (!container || !audio) return;

  const result = await loadSiblingSrt(audioPath);
  if (!result) return;

  const parsed = parseSrt(result.text);
  if (parsed.length === 0) {
    container.innerHTML = `<div class="srt-embed-empty">字幕を読み込めませんでした</div>`;
    return;
  }
  const cues = parsed.map(c => ({
    ...c,
    startSec: timeToSeconds(c.start),
    endSec: timeToSeconds(c.end),
  }));

  const cardsHtml = cues.map(c => {
    const color = speakerColor(c.speaker);
    const styleAttr = color ? ` style="--speaker-color: ${color};"` : '';
    const speakerBadge = c.speaker ? `<span class="srt-speaker">${esc(c.speaker)}</span>` : '';
    const timeStr = (c.start && c.end) ? `${esc(c.start)} → ${esc(c.end)}` : '--';
    return `<div class="srt-cue" data-start="${c.startSec}" data-end="${c.endSec}"${styleAttr}>
      <div class="srt-meta"><span class="srt-time">${timeStr}</span>${speakerBadge}</div>
      <div class="srt-text">${esc(c.text)}</div>
    </div>`;
  }).join('');

  const srtName = result.path.split('/').pop();
  container.innerHTML = `<div class="srt-embed-header">字幕 (<span class="srt-embed-filename">${esc(srtName)}</span>)</div>${cardsHtml}`;

  setupSrtSync(audio, container, cues);
}
```

- `showBlob` の audio 分岐最後で `setupPlaybackLog(path)` の直後に `setupSrtEmbed(path)` を呼ぶ
- `await` はするが呼び出し元は `return` しているので UI ブロックしない

### 同期ロジック (setupSrtSync)

```js
function setupSrtSync(audio, container, cues) {
  const cueEls = container.querySelectorAll('.srt-cue');
  let currentIdx = -1;
  let followEnabled = true;
  let programmaticScrollUntil = 0;
  let manualPauseTimer = null;

  const resumeFollow = () => {
    followEnabled = true;
    clearTimeout(manualPauseTimer);
    manualPauseTimer = null;
  };
  const pauseFromManualScroll = () => {
    followEnabled = false;
    clearTimeout(manualPauseTimer);
    manualPauseTimer = setTimeout(resumeFollow, 5000);
  };

  container.addEventListener('scroll', () => {
    if (performance.now() < programmaticScrollUntil) return;
    pauseFromManualScroll();
  }, { passive: true });

  const findIdx = (t) => {
    if (currentIdx >= 0 && currentIdx < cues.length) {
      const c = cues[currentIdx];
      if (t >= c.startSec && t <= c.endSec) return currentIdx;
    }
    for (let i = 0; i < cues.length; i++) {
      if (t >= cues[i].startSec && t <= cues[i].endSec) return i;
    }
    return -1;
  };

  const update = () => {
    const idx = findIdx(audio.currentTime);
    if (idx === currentIdx) return;
    if (currentIdx >= 0 && cueEls[currentIdx]) cueEls[currentIdx].classList.remove('current');
    currentIdx = idx;
    if (idx < 0) return;
    const el = cueEls[idx];
    if (!el) return;
    el.classList.add('current');
    if (followEnabled) {
      programmaticScrollUntil = performance.now() + 800;
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  };

  audio.addEventListener('timeupdate', update);
  audio.addEventListener('seeked', () => { resumeFollow(); update(); });
}
```

### 落とし穴と対策

| 落とし穴 | 対策 |
|---|---|
| `scrollIntoView({behavior:'smooth'})` 中の scroll イベント連発で「手動スクロール検知」が誤発火 | `programmaticScrollUntil` で発火後 800ms 間の scroll イベントを無視 |
| 毎 `timeupdate` で cue 全走査すると cue 数が多いとき重い | `currentIdx` からの近傍チェックを先に行い、ほぼ 1 ステップで決着 |
| cue 間の gap で前の cue がハイライトされ続ける | `findIdx` が `-1` を返すようにして `.current` を外す |
| ファイル切替時の `timeupdate` リスナ残留 | `#srt-embed` ごと `showBlob` で作り直され、古い要素は DOM から外れるため `timeupdate` 自体が発火対象外となり GC される |

### 追従復帰条件まとめ

| トリガー | 挙動 |
|---|---|
| 手動スクロール検知 | 5 秒タイマー開始、`followEnabled = false`。スクロールが連続すればタイマーは毎回振り直される |
| 5 秒経過 | `followEnabled = true`（次の cue 遷移で追従再開） |
| 音声シーク (`seeked`) | 即 `followEnabled = true` + update で追従 |

## Styling (static/style.css)

```css
.srt-embed-container {
  margin-top: 10px;
  border-top: 1px solid var(--border);
  padding-top: 8px;
  max-height: 60vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.srt-embed-header {
  position: sticky;
  top: 0;
  background: var(--bg);
  color: var(--text-muted);
  font-size: 11px;
  padding: 4px 0;
  z-index: 1;
}
.srt-embed-empty {
  color: var(--text-dim);
  font-size: 12px;
  padding: 8px 0;
}
.srt-embed-container .srt-cue {
  transition: background-color 120ms, border-left-color 120ms;
}
.srt-embed-container .srt-cue.current {
  background: var(--surface-hover, rgba(255,255,255,0.06));
  border-left-width: 6px;
  box-shadow: 0 0 0 1px var(--speaker-color, var(--border)) inset;
}
```

## Error Handling

| ケース | 挙動 |
|---|---|
| 同名 SRT が両方とも存在しない | `#srt-embed` を空のまま残す |
| `/api/blob` が失敗 | `catch` で次の候補へ、両方失敗なら空 |
| `parseSrt` が 0 件 | `#srt-embed` に「字幕を読み込めませんでした」のみ表示、同期は仕込まない |
| cue の `startSec` / `endSec` が `NaN` | `findIdx` の比較で自然にスキップ（表示はされるがハイライト対象外） |
| 別の音声を開く | `#srt-embed` ごと DOM が差し替えられるため旧 audio のイベントは自動で GC 対象 |

## Testing (手動)

- `Aivis_Conversation/projects/20260424_バイアスとは何か_第5章/out` 配下の `.mp3` を開き、下に字幕リストが出ること
- 再生開始 → 現 cue が強調され、画面中央付近に追従スクロールすること
- 再生バーのシーク → `seeked` で即追従復帰し、飛び先の cue がハイライトされること
- 手動ホイールスクロール → 追従が止まること、5 秒後に自動復帰すること
- 手動スクロール停止中に cue 境界を跨いでも追従は再開しないこと（5 秒経過後の次遷移で再開）
- 同名 `.srt` がない `.mp3` を開く → 下は空欄のまま、エラーも警告も出ないこと
- `.wav` でも同様に動くこと
- `foo.srt` と `foo.mp3.srt` が両方あるディレクトリで `foo.srt` が優先されること
- 1000 cue 以上の長尺 SRT でハイライト追従が破綻しないこと
- cue 間の gap で現ハイライトが外れること
- iOS Safari で `timeupdate` ベースの更新が動くこと

## Impact

- `app.py`: 変更なし
- `templates/index.html`:
  - `showBlob` の audio 分岐に `#srt-embed` コンテナを追加し、`setupPlaybackLog(path)` の後に `setupSrtEmbed(path)` を呼ぶ
  - `timeToSeconds(tc)` を追加
  - `loadSiblingSrt(audioPath)` を追加
  - `setupSrtEmbed(audioPath)` を追加
  - `setupSrtSync(audio, container, cues)` を追加
- `static/style.css`:
  - `.srt-embed-container` / `.srt-embed-header` / `.srt-embed-empty` / `.srt-embed-container .srt-cue` / `.srt-embed-container .srt-cue.current` を追加
