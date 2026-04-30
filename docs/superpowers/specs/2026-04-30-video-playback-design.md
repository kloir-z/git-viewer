# Video Playback Design

## 目的

ローカルリポジトリ配下の動画ファイルを、ブラウザ上でストリーミング再生 (シーク可) できるようにする。既存のオーディオ再生画面と同等の UX を提供し、メモ・再生履歴・keep-awake と統合する。

## スコープ

- ブラウザがネイティブで再生できる動画形式のみ対応 (`mp4`/`webm`/`m4v`/`mov`/`ogv`)。再生不可な形式 (`.mkv`/`.avi`/`.wmv` など) は従来通りバイナリとして配信する (ダウンロードボタン表示)。
- サーバ側のトランスコードは行わない (Pi上で非実用)。
- 字幕の自動スクロール (現在再生位置に追従するハイライト/スクロール) は **動画では行わない**。動画が画面外に押し出されると視聴できなくなるため。
- それ以外のオーディオ画面の機能 (同名 `.srt` の表示・クリックシーク・メモ機能・再生履歴 `.playback.jsonl`・再生中の keep-awake) はすべて再利用する。

## アーキテクチャ

### バックエンド (`app.py`)

`/api/blob` エンドポイントは既に `send_file()` でバイナリを返しており、Flask 2.x の `send_file` は `conditional=True` がデフォルトのため、HTTP `Range` リクエストに対応している。動画ファイルもこのパスを通るため、ストリーミング/シークは追加実装なしで動作する。

変更は実質ゼロ。任意で `_playback_log_path` 内の局所変数名 `audio_full` を `media_full` 等にリネームする (動画も扱う旨を明示するため)。

### フロントエンド (`templates/index.html`)

#### 拡張子定数の追加

```js
const VIDEO_EXTS = ['mp4','webm','m4v','mov','ogv'];
```

#### viewer 分岐の追加

`loadBlob` 内で許可拡張子チェック (line 926付近) に `VIDEO_EXTS` を追加。

動画 viewer 本体は、既存のオーディオ用 HTML テンプレート (line 944-949 周辺) をベースに **要素タグだけ `<audio>` → `<video>` に差し替える**。

```html
<video id="audio-player" controls preload="metadata" src="${blobUrl}"
       style="width:100%; max-height:70vh; background:#000;"></video>
<div id="playback-log-list" class="playback-log"></div>
```

要素 ID を `audio-player` のまま流用することがキー。既存の SRT 表示・再生履歴・keep-awake のコードはすべてこの ID を `getElementById` で取得しており、`HTMLMediaElement` の API (`currentTime`/`paused`/`play()`/`addEventListener('timeupdate', ...)` 等) は `<audio>` と `<video>` で完全共通のため、そのまま動く。

#### 自動スクロール無効化

`setupSrtSync` (line 604) 内の現在再生位置に追従して字幕をスクロールする処理を、対象が `<video>` のときだけスキップする。判定:

```js
const isVideo = mediaEl.tagName === 'VIDEO';
```

字幕クリック→シーク、ハイライト表示などの「スクロールしない」装飾は維持してよい (動画でも有用)。スクロール (`scrollIntoView` 等) のみ抑止する。

#### 既存コード (変更不要)

- `<source>/<video>/<audio>` 要素のクリーンアップ処理 (line 460) は既に video/audio 両対応。
- 再生履歴 (`setupPlaybackLog`/`refreshPlaybackLog`) は ID 経由で要素を取得し、`HTMLMediaElement` の標準 API しか使っていないため変更不要。
- keep-awake 判定 (line 1814 周辺) も同 ID を使うため、動画再生中も自動で発動する。

## 動作確認項目

1. `.mp4` ファイルを開いて、再生・一時停止・シーク (Range リクエスト) ができる。
2. 再生中に keep-awake が発動する (Pi では PowerShell スクリプトが起動しないので、最低限「ブラウザのスリープ抑止リクエストが送信される」ことを確認)。
3. 15秒以上連続再生で `<filename>.playback.jsonl` に履歴が追記され、UI上の「再生履歴」にも表示される。範囲クリックでシークできる。
4. 同名 `.srt` がある場合、動画下に字幕テキストが表示される。クリックでシーク可能。**現在再生位置に追従した自動スクロールは行われない**。
5. メモ機能 (字幕行へのメモ追加) が動画でも動作する。
6. `.mkv` など非対応形式は従来通り「ダウンロード」UIになる (再生は試みない)。

## 設計方針 (なぜこの形か)

- **新規の動画専用ロジックを設けない**。`<audio>` を `<video>` に差し替えるだけで成立させる。要素 ID を共有することで既存の SRT/履歴/keep-awake コードを丸ごと流用できる。
- 自動スクロール抑止は SRT 同期処理側に分岐を1つ足すだけ。動画⇔オーディオ間で挙動が「ほぼ同じだが1点だけ違う」状態を、コード上も「ほぼ同じだが1点だけ分岐」で表現する。
- 非対応動画フォーマットへの対応 (トランスコード等) は YAGNI で見送る。必要になったら後付けで判断する。
