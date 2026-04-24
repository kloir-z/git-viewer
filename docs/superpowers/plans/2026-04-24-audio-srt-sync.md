# Audio ↔ SRT 同期表示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.mp3` / `.wav` を開いたとき、同ディレクトリの同名 `.srt` を自動検出して再生バー・再生履歴の下に字幕を埋め込み表示し、再生位置に応じて現 cue をハイライト＋自動スクロール追従する。

**Architecture:** フロントエンド専用変更。既存の `parseSrt()` / `speakerColor()` / `.srt-cue` スタイルを再利用。`showBlob` の audio 分岐に `#srt-embed` コンテナを追加し、`setupSrtEmbed(path)` が SRT 候補を 2 パターン試して検出 → 描画 → `setupSrtSync()` で `timeupdate` を購読して現 cue に `.current` を付ける。プログラム起因スクロールの検知で手動スクロール判定の誤発火を防ぐ。

**Tech Stack:** Flask (バックエンド、無変更) / 素の JavaScript (インライン) / CSS (GitHub Dark テーマ)。

**Testing Strategy:** このプロジェクトには自動テストが存在しないため、各タスクの検証は Windows サービス再起動 (`powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"`) → ブラウザでの手動シナリオ確認で行う。対象データは `Aivis_Conversation/projects/20260424_バイアスとは何か_第5章/out` 配下の `.mp3` + 同名 `.srt`。

**Spec:** `docs/superpowers/specs/2026-04-24-audio-srt-sync-design.md`

---

## File Structure

- `templates/index.html` — 以下を追加:
  - `timeToSeconds(tc)` … SRT タイムコード → 秒
  - `loadSiblingSrt(audioPath)` … 同名 SRT を探索してテキストを返す
  - `setupSrtEmbed(audioPath)` … ロード＋描画＋同期セットアップのオーケストレータ
  - `setupSrtSync(audio, container, cues)` … `timeupdate` 購読とスクロール追従
  - `showBlob` の audio 分岐: `#srt-embed` コンテナを追加し `setupSrtEmbed(path)` を呼ぶ
- `static/style.css` — 以下を追加:
  - `.srt-embed-container` / `.srt-embed-header` / `.srt-embed-empty`
  - `.srt-embed-container .srt-cue` トランジション
  - `.srt-embed-container .srt-cue.current` ハイライト

既存関数 (`parseSrt`, `speakerColor`, `esc`, `fetchJson`) は変更しない。`app.py` も無変更。

---

## Task 1: 埋め込みコンテナのスケルトンと土台 CSS

**目的:** audio 分岐に空の `#srt-embed` コンテナが出る状態にする。この段階では何も描画されないが、レイアウト崩れがないこと、スクロール領域の挙動が確認できること。

**Files:**
- Modify: `templates/index.html` (`showBlob` の audio 分岐、現状 810-820 行付近)
- Modify: `static/style.css` (末尾に追加)

- [ ] **Step 1: `showBlob` の audio 分岐に `#srt-embed` コンテナを追加**

`templates/index.html` の audio 分岐を以下に書き換える:

```js
  // Audio
  if (AUDIO_EXTS.includes(ext)) {
    blobView.innerHTML = `
      <div class="section-header" style="margin-top:8px;">${esc(path)}</div>
      <div class="blob-container" style="padding:8px;">
        <audio id="audio-player" controls preload="metadata" src="${blobUrl}" style="width:100%;"></audio>
        <div id="playback-log-list" class="playback-log"></div>
        <div id="srt-embed" class="srt-embed-container"></div>
      </div>`;
    setupPlaybackLog(path);
    return;
  }
```

- [ ] **Step 2: 土台 CSS を `static/style.css` の末尾に追加**

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
.srt-embed-container:empty {
  display: none;
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
```

`:empty` を入れて、まだ何も描画されない Task 1 時点ではコンテナごと非表示になるようにする（`border-top` が空白のまま見えてしまうのを防ぐ）。

- [ ] **Step 3: サービス再起動**

Windows 用:

```bash
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

- [ ] **Step 4: ブラウザで手動確認**

1. `http://<raspi-or-localhost>:5125/` を開く
2. `Aivis_Conversation/projects/20260424_バイアスとは何か_第5章/out/*.mp3` のいずれかをツリーから開く
3. 期待: 再生バー + 再生履歴の下は空欄（`:empty` で非表示なので border-top も見えない）。レイアウト崩れなし
4. 開発者ツールで `#srt-embed` 要素が DOM に存在し、`max-height: 60vh; overflow-y: auto` が適用されていることを確認

- [ ] **Step 5: コミット**

```bash
git add templates/index.html static/style.css
git commit -m "feat: add SRT embed container scaffold on audio view"
```

---

## Task 2: SRT 検出と描画 (同期はまだ)

**目的:** 同ディレクトリの同名 `.srt` を自動検出し、cue カードリストを `#srt-embed` に描画する。`.current` ハイライトや追従スクロールは Task 3 で追加。

**Files:**
- Modify: `templates/index.html` (関数 3 個を `speakerColor` の直後に追加、`showBlob` の audio 分岐で呼び出し)

- [ ] **Step 1: `timeToSeconds` を追加**

`templates/index.html` の `speakerColor` 関数の直後（現状 533 行付近、`// --- Bookmark helpers ---` コメントの直前）に追加:

```js
function timeToSeconds(tc) {
  if (!tc) return NaN;
  const m = tc.match(/^(\d+):(\d+):(\d+)[,.](\d+)$/);
  if (!m) return NaN;
  return (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3]) + (+m[4]) / Math.pow(10, m[4].length);
}
```

- [ ] **Step 2: `loadSiblingSrt` を追加**

`timeToSeconds` の直後に追加:

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

- [ ] **Step 3: `setupSrtEmbed` を追加（同期呼び出しはまだ無し）**

`loadSiblingSrt` の直後に追加:

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

  // 同期ロジックは Task 3 で追加
}
```

- [ ] **Step 4: `showBlob` audio 分岐で `setupSrtEmbed(path)` を呼ぶ**

`templates/index.html` の audio 分岐の `setupPlaybackLog(path);` の次行に `setupSrtEmbed(path);` を追加:

```js
    setupPlaybackLog(path);
    setupSrtEmbed(path);
    return;
```

- [ ] **Step 5: サービス再起動**

```bash
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

- [ ] **Step 6: ブラウザで手動確認**

1. 同名 `.srt` が存在する `.mp3` を開く → 再生バー下に cue カードが並ぶこと。話者色が cue 左ボーダーに出ていること
2. 同名 `.srt` が存在しない `.mp3` を開く → 空欄のまま。コンソールにエラーが出ないこと（候補フェッチの 404 はネットワークタブに出るが `catch` で握りつぶされるのでコンソールは綺麗）
3. `foo.mp3.srt` のような末尾追加タイプの命名を作成して検証:
   - 一時的に `.../out/foo.srt` を `.../out/foo.mp3.srt` にリネーム（Windows エクスプローラーで OK）
   - 同じ mp3 を開き直す → 字幕が出ること
   - リネームを戻す
4. `foo.srt` と `foo.mp3.srt` の両方がある状態を一時的に作成し、`foo.srt` が優先されることを確認（ネットワークタブで候補 1 本目が 200 を返していること）
5. `.wav` でも同じ動作になることを確認（出力プロジェクトに `.wav` があれば）

- [ ] **Step 7: コミット**

```bash
git add templates/index.html
git commit -m "feat: render sibling SRT below audio player"
```

---

## Task 3: 再生同期ハイライト + 自動スクロール追従

**目的:** `setupSrtSync` を追加し、再生位置に応じて `.current` クラスを付け替え、現 cue が画面中央に来るよう追従スクロールする。手動スクロール検知で追従を一時停止、5 秒後 or シークで復帰。

**Files:**
- Modify: `templates/index.html` (`setupSrtSync` を `setupSrtEmbed` の直後に追加、`setupSrtEmbed` の末尾で呼び出す)
- Modify: `static/style.css` (`.current` の強調スタイルを追加)

- [ ] **Step 1: `setupSrtSync` を追加**

`templates/index.html` の `setupSrtEmbed` の直後に追加:

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

- [ ] **Step 2: `setupSrtEmbed` の末尾で `setupSrtSync` を呼ぶ**

`setupSrtEmbed` の `container.innerHTML = ...` の次行（関数閉じ括弧の直前）に追加:

```js
  container.innerHTML = `<div class="srt-embed-header">字幕 (<span class="srt-embed-filename">${esc(srtName)}</span>)</div>${cardsHtml}`;

  setupSrtSync(audio, container, cues);
}
```

- [ ] **Step 3: `.current` ハイライト CSS を追加**

`static/style.css` 末尾の Task 1 で追加したブロックに追記:

```css
.srt-embed-container .srt-cue {
  transition: background-color 120ms, border-left-color 120ms;
}
.srt-embed-container .srt-cue.current {
  background: var(--surface-hover, rgba(255,255,255,0.06));
  border-left-width: 6px;
  box-shadow: 0 0 0 1px var(--speaker-color, var(--border)) inset;
}
```

- [ ] **Step 4: サービス再起動**

```bash
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

- [ ] **Step 5: ブラウザで手動確認（主要シナリオ）**

以下を順に確認:

1. **ハイライト基本動作**
   - 同名 `.srt` がある `.mp3` を開き、再生開始
   - 現 cue の背景が変わり、左ボーダーが太くなること
   - 再生が進むたびに `.current` が次の cue に移ること

2. **自動スクロール追従**
   - 長尺 SRT（数十～数百 cue）で再生を進める
   - 現 cue が画面中央付近に smooth スクロールで追従すること
   - DevTools で `#srt-embed` の `scrollTop` が動いていることを確認

3. **手動スクロール検知**
   - 再生中にホイールで `#srt-embed` 内をスクロール
   - 追従が止まること（scroll イベント後の `.current` 遷移で `scrollIntoView` が呼ばれないこと）
   - 5 秒間待つ → 追従が自動復帰し、次の cue 遷移時に画面中央へスクロールすること

4. **プログラム起因スクロールの誤発火がないこと**
   - 再生を中断せずに長時間流す → 追従が自然に続くこと（「スクロールするたびに pauseFromManualScroll が誤発火して追従が止まる」症状が出ないこと）。これが出たら `programmaticScrollUntil` の 800ms が短い可能性

5. **シークで即復帰**
   - 手動スクロール中（追従停止中）に audio シークバーで別の位置へジャンプ
   - `seeked` で追従が即復帰、飛び先の cue がハイライトされ画面中央に来ること

6. **cue 間 gap**
   - 無音区間（次の cue まで間が空くファイル）で再生位置が gap に入ったとき、ハイライトが一旦外れて次の cue で戻ること

7. **同名 SRT なしの音声**
   - 字幕が無い `.mp3` を開いて再生 → エラーなし、埋め込み領域は空欄のまま

8. **ファイル切替**
   - 音声 A を再生中、別の音声 B に切替 → B の字幕が描画され、ハイライトは B の再生位置で動くこと（A のイベントリスナーが残って二重更新などしていないこと）

9. **iOS Safari（可能なら）**
   - iPhone で同じ mp3 を開き、再生→ `timeupdate` ベースのハイライトが動くこと
   - `scrollIntoView({behavior:'smooth'})` が効かない場合でも、即時ジャンプとしては機能すること

- [ ] **Step 6: コミット**

```bash
git add templates/index.html static/style.css
git commit -m "feat: sync SRT highlight and scroll with audio playback"
```

---

## Self-Review

**Spec coverage:**

- ✅ 同名 SRT 検出（`foo.srt` → `foo.mp3.srt` フォールバック） → Task 2 Step 2 (`loadSiblingSrt`)
- ✅ SRT が無い時は現状通り → Task 2 Step 3 で `result` が null なら return、`:empty` CSS でコンテナ非表示
- ✅ cue 描画（番号省略、話者色、dblclick/編集なし） → Task 2 Step 3
- ✅ `.current` ハイライト → Task 3 Step 1 (update 関数) + Step 3 CSS
- ✅ 自動スクロール追従 → Task 3 Step 1 (scrollIntoView 呼び出し)
- ✅ 手動スクロール検知 5 秒タイマー → Task 3 Step 1 (`pauseFromManualScroll`)
- ✅ プログラム起因スクロール抑止 → Task 3 Step 1 (`programmaticScrollUntil`)
- ✅ シークで即復帰 → Task 3 Step 1 (`seeked` listener)
- ✅ cue gap で `.current` 外す → Task 3 Step 1 (`findIdx` が -1 を返し update が早期 return 前に remove)
- ✅ 内部スクロール領域 `max-height: 60vh` → Task 1 Step 2
- ✅ 編集ボタン・ブックマーク無し → Task 2 Step 3 の cardsHtml に何も追加しない

**Placeholder scan:** TBD / TODO / "appropriate" の文言なし。全コードブロックは実コード。

**Type consistency:**
- `cues` は `{index, start, end, speaker, text, startSec, endSec}` の配列で、Task 2 で生成 → Task 3 で消費。一貫
- `cueEls` は `container.querySelectorAll('.srt-cue')` の NodeList。`cueEls[idx]` でアクセス（NodeList はインデックスアクセス可）
- `findIdx` の戻り値 `-1` は `currentIdx` の初期値と同じセマンティクス（「現 cue なし」）で、update の分岐と整合
- `result` は `{path, text}` または `null`。`setupSrtEmbed` で両ケースを処理

---

## Out of Scope（仕様書より再掲）

- cue クリックでの再生位置ジャンプ
- 音声埋め込み SRT でのブックマーク・編集
- WebVTT (`.vtt`) 対応
- 複数言語字幕の切替
- 字幕検索・ジャンプ UI
