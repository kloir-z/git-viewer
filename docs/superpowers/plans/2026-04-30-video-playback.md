# Video Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ブラウザネイティブ再生可能な動画ファイル (`mp4`/`webm`/`m4v`/`mov`/`ogv`) をオーディオ再生画面と同レイアウトで再生できるようにし、既存の SRT 表示・再生履歴・keep-awake と統合する。SRT 自動スクロールのみ動画では無効化する。

**Architecture:** フロントエンド (`templates/index.html`) のみ変更。`<audio>` viewer を雛形に `<video>` viewer 分岐を追加し、要素 ID を `audio-player` のまま流用することで既存の SRT/履歴/keep-awake コードをそのまま使う。SRT 自動スクロールは `audio.tagName === 'VIDEO'` で 1 箇所だけ分岐。バックエンドは変更不要 (`Flask.send_file` が `Range` リクエストに既対応)。

**Tech Stack:** Vanilla JS (inline in template), HTML5 `<video>` element, Flask `send_file`.

**前提知識:**
- このリポジトリではフロントエンドの自動テストは整備されていない。検証は **手動ブラウザ確認** で行う (CLAUDE.md の方針に沿う)。
- `app.py` または `templates/index.html` を変更したら、動作確認のため Windows サービスを再起動する。再起動コマンド: `powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"` (CLAUDE.md より)。
- アプリは port 5125 で起動。ブラウザは http://localhost:5125/ を開く。
- テスト用動画ファイルは、`CODE_DIR` 配下の任意の git リポジトリに `.mp4` を 1 つ配置する。ユーザーが既に持っていれば流用してよい。

---

## Task 1: VIDEO_EXTS 定数を追加し、AUDIO_EXTS から webm を移動する

**Files:**
- Modify: `templates/index.html:466-474`

**前提:** `AUDIO_EXTS` には現状 `'webm'` が含まれている (line 468)。webm は実際には動画コンテナとして使われる方が圧倒的に多いので、VIDEO_EXTS に移動する。これにより後続タスクでの拡張子判定の重複を防ぐ。

- [ ] **Step 1: 定数の修正**

`templates/index.html` の line 466-468 周辺を以下のように変更する。

変更前 (line 466-468):
```js
const IMAGE_EXTS = ['jpg','jpeg','png','gif','svg','webp','ico'];
const PDF_EXTS = ['pdf'];
const AUDIO_EXTS = ['mp3','wav','ogg','m4a','flac','aac','opus','webm'];
```

変更後:
```js
const IMAGE_EXTS = ['jpg','jpeg','png','gif','svg','webp','ico'];
const PDF_EXTS = ['pdf'];
const AUDIO_EXTS = ['mp3','wav','ogg','m4a','flac','aac','opus'];
const VIDEO_EXTS = ['mp4','webm','m4v','mov','ogv'];
```

- [ ] **Step 2: サービス再起動**

Windows PowerShell:
```
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

期待: サービスが再起動し、http://localhost:5125/ にアクセスできる。

- [ ] **Step 3: 手動確認 (回帰なし)**

ブラウザで `.mp3` ファイルを開く。期待: 従来通り `<audio>` プレイヤーが表示され、再生できる (AUDIO_EXTS から webm を抜いただけなので mp3 は影響を受けない)。

- [ ] **Step 4: コミット**

```
git add templates/index.html
git commit -m "refactor(viewer): split webm out of AUDIO_EXTS into new VIDEO_EXTS"
```

---

## Task 2: showBlob に video viewer 分岐を追加する

**Files:**
- Modify: `templates/index.html:925-955`

**前提:** `showBlob` 関数内で拡張子による分岐をしている。バイナリ判定 (line 926) に VIDEO_EXTS を含め、動画の場合に `<audio>` 雛形を `<video>` に差し替えた viewer を表示する。**要素 ID は `audio-player` のまま** にすることで既存の SRT/履歴/keep-awake コードをそのまま動かす。

video 分岐は audio 分岐より前に置く (順序は実用上どちらでも構わないが、AUDIO_EXTS と VIDEO_EXTS が重複しなくなったので順序による分岐ハマりはない)。

- [ ] **Step 1: バイナリ判定行に VIDEO_EXTS を追加**

`templates/index.html:926` を以下のように変更する。

変更前 (line 926):
```js
  if (!IMAGE_EXTS.includes(ext) && !PDF_EXTS.includes(ext) && !AUDIO_EXTS.includes(ext) && !TEXT_EXTS.includes(ext) && ext !== '') {
```

変更後:
```js
  if (!IMAGE_EXTS.includes(ext) && !PDF_EXTS.includes(ext) && !AUDIO_EXTS.includes(ext) && !VIDEO_EXTS.includes(ext) && !TEXT_EXTS.includes(ext) && ext !== '') {
```

- [ ] **Step 2: video 分岐を audio 分岐の直前に追加**

`templates/index.html` の line 943 (`// Audio` コメントの直前) に以下のブロックを挿入する。

```js
  // Video
  if (VIDEO_EXTS.includes(ext)) {
    blobView.innerHTML = `
      <div class="section-header" style="margin-top:8px;">${esc(path)}${copyPathBtn(path)}</div>
      <div class="blob-container" style="padding:8px;">
        <video id="audio-player" controls preload="metadata" src="${blobUrl}" style="width:100%; max-height:70vh; background:#000;"></video>
        <div id="playback-log-list" class="playback-log"></div>
        <div id="srt-embed" class="srt-embed-container"></div>
      </div>`;
    setupPlaybackLog(path);
    setupSrtEmbed(path);
    return;
  }

```

挿入後、続く `// Audio` 分岐 (line 944〜) はそのまま変更しない。

- [ ] **Step 3: サービス再起動**

```
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

- [ ] **Step 4: 手動確認 — 動画再生**

事前準備: `CODE_DIR` 配下の任意のリポジトリに `.mp4` ファイルを 1 つ配置する (テスト用)。

ブラウザで http://localhost:5125/ を開き、対象リポジトリ → ファイルツリー経由で `.mp4` を選択。

期待:
- `<video>` プレイヤー (黒背景、幅100%、最大高70vh) が表示される。
- 再生ボタンで再生できる。
- シークバーで任意の位置にジャンプできる (Range リクエストが効いている証拠 — DevTools の Network タブで `/api/blob` への複数リクエストに `206 Partial Content` が返ることを確認できればなお良い)。
- 一時停止できる。

- [ ] **Step 5: 手動確認 — 再生履歴**

動画を 15 秒以上連続再生してから一時停止する。

期待:
- プレイヤーの下に「再生履歴 (1)」のような表示が現れる。
- リポジトリ内、動画と同じディレクトリに `<filename>.playback.jsonl` が作成され、再生範囲のレコードが追記されている。
- 履歴の範囲をクリックすると、その位置にシークして再生が再開する。

- [ ] **Step 6: 手動確認 — keep-awake**

DevTools → Network タブを開いた状態で動画を再生し続ける。

期待:
- `/api/keep-awake` への POST が約 20 秒ごとに飛ぶ (`KEEP_AWAKE_INTERVAL_MS = 20000`)。
- 動画再生中は、ページがバックグラウンドタブでも keep-awake が継続する (`shouldKeepAwake` が `!audio.paused` で true を返すため)。

- [ ] **Step 7: 手動確認 — 非対応形式は従来通り**

`.mkv` や `.avi` など VIDEO_EXTS に含まれない動画ファイル (持っていなければスキップ可) を開く。

期待: 従来通り「バイナリファイル — ダウンロード」表示になる。再生 UI は出ない。

- [ ] **Step 8: コミット**

```
git add templates/index.html
git commit -m "feat(blob): play mp4/webm/m4v/mov/ogv via HTML5 <video>"
```

---

## Task 3: SRT 自動スクロールを動画では無効化する

**Files:**
- Modify: `templates/index.html:604-666`

**前提:** `setupSrtSync` 内の `update()` 関数 (line 638-653) が現在の cue を `current` クラスでハイライトし、`scrollIntoView` で字幕コンテナを自動スクロールしている。動画ではこの自動スクロールが「動画より下にある字幕領域がスクロールしてしまい動画から目を離す必要が出る」ため不要。ハイライトとクリックシークは維持する。

- [ ] **Step 1: isVideo フラグを追加し、scrollIntoView 呼び出しをガードする**

`templates/index.html:604-666` の `setupSrtSync` 関数を以下のように変更する。

変更前 (line 604-653 抜粋):
```js
function setupSrtSync(audio, container, cues) {
  const cueEls = container.querySelectorAll('.srt-cue');
  let currentIdx = -1;
  let followEnabled = true;
  let programmaticScrollUntil = 0;
  let manualPauseTimer = null;
```

変更後 (1 行追加):
```js
function setupSrtSync(audio, container, cues) {
  const cueEls = container.querySelectorAll('.srt-cue');
  const isVideo = audio.tagName === 'VIDEO';
  let currentIdx = -1;
  let followEnabled = true;
  let programmaticScrollUntil = 0;
  let manualPauseTimer = null;
```

そして `update()` 内の自動スクロール部分 (line 647-652) を以下に変更する。

変更前:
```js
    if (followEnabled) {
      // Suppress scroll events fired by smooth scrollIntoView so the manual-
      // scroll handler does not misread them as user input and pause follow.
      programmaticScrollUntil = performance.now() + 800;
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
```

変更後:
```js
    if (followEnabled && !isVideo) {
      // Suppress scroll events fired by smooth scrollIntoView so the manual-
      // scroll handler does not misread them as user input and pause follow.
      programmaticScrollUntil = performance.now() + 800;
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
```

それ以外のコード (highlight 付与、`dblclick` でのシーク、`scroll` ハンドラ等) は変更しない。動画でも字幕クリックシーク・ハイライト表示は維持される。

- [ ] **Step 2: サービス再起動**

```
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

- [ ] **Step 3: 手動確認 — 動画では自動スクロールしない**

事前準備: テスト用 `.mp4` と同じディレクトリに同名 `.srt` ファイル (例: `clip.mp4` と `clip.srt`) を配置。`.srt` には現在の動画再生範囲をカバーする複数の cue が含まれていること。

`.mp4` をブラウザで開き、再生する。

期待:
- 動画下に字幕カードリストが表示される。
- 再生位置に対応する cue カードに `current` クラスのハイライトが付く (CSS で背景色などが変わる)。
- **字幕コンテナの自動スクロールが発生しない**。再生位置が後の cue に進んでも、字幕コンテナ自体のスクロール位置は変わらない (ユーザーが手動でスクロールしない限り)。
- cue カードをダブルクリックするとその位置にシークして再生される (これは従来通り動く)。

- [ ] **Step 4: 手動確認 — オーディオでは従来通り自動スクロールする (回帰なし)**

`.mp3` + 同名 `.srt` の組を開いて再生する。

期待:
- 従来通り、再生位置に応じて字幕コンテナが自動スクロールする (`isVideo === false` なので影響を受けない)。

- [ ] **Step 5: コミット**

```
git add templates/index.html
git commit -m "feat(blob): suppress SRT auto-scroll for video to keep video in view"
```

---

## Self-Review

- スペック動作確認項目1 (mp4 シーク再生): Task 2 Step 4 でカバー
- スペック動作確認項目2 (keep-awake): Task 2 Step 6 でカバー
- スペック動作確認項目3 (再生履歴 15秒以上): Task 2 Step 5 でカバー
- スペック動作確認項目4 (SRT 表示・クリックシーク・自動スクロール無効): Task 3 Step 3 でカバー
- スペック動作確認項目5 (動画でのメモ機能): SRT 表示が動けばメモ機能 (`fetchNotes`/`decorateEmbeddedSrtNotes`) も同じ経路で動くため Task 3 Step 3 で実質確認できる。明示的に追記する場合は cue カードを右クリックや既存のメモ操作 UI でメモ追加できることを確認する。
- スペック動作確認項目6 (.mkv 非対応): Task 2 Step 7 でカバー
- バックエンド変数名リネームは「任意」のためプランから除外 (YAGNI)。
