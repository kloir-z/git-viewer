# Git Viewer Sleep Inhibit (cc-nosleep 連携) 設計

## 背景と目的

Windows デスクトップを iPhone から (Tailscale + ブラウザで) git-viewer 経由で利用するケースで、Windows の 1 分の無操作スリープが発動してしまう。特に音声再生中はタブがバックグラウンドに行きがちでスリープ抑止が効かない。Claude Code 利用時のスリープ抑止は `C:\code\cc-nosleep` で既に実装済みなので、その deadline ファイル機構に相乗りする形で git-viewer 側からも抑止できるようにする。

## 要件

| 状態 | 抑止 |
|---|---|
| 音声再生中 (タブ visible / hidden 問わず) | ON |
| 音声停止中 + タブ visible | ON |
| 音声停止中 + タブ hidden | OFF (~3分以内にスリープへ) |

- iPhone でブラウザがバックグラウンドに行っても、`<audio>` の再生継続中はスリープしない
- iPhone から音声を停止した瞬間からは「タブ visible 状態が続いていない限り」抑止が外れて、自然スリープに戻る
- 複数ブラウザ・複数タブから同時に使っても破綻しない (cc-nosleep の deadline ファイルは session_id 別)

## 既存メカニズムの再利用方針

`cc-nosleep` は次の構造で動く:

- `keep-awake.ps1` が呼ばれると、stdin JSON の `session_id` を見て `%TEMP%\claude-awake.deadline.<sid>` を `now + N 分` で更新し、watcher が止まっていれば spawn する
- `awake-watcher.ps1` が `claude-awake.deadline.*` を**全件**読んで、未来 deadline が 1 つでもあれば `SetThreadExecutionState` で抑止を維持する
- 全 deadline が expire したら `SetThreadExecutionState(ES_CONTINUOUS)` で抑止解除して watcher 自己終了

**git-viewer から呼ぶ正しい入口は `keep-awake.ps1`**。理由:

- watcher の単一インスタンス化・spawn ロジックが既に正しく実装されている
- deadline ファイル名フォーマットは内部実装なので git-viewer 側で直接書きたくない
- cc-nosleep の README に手動実行例 (`'{"session_id":"manual-test"}' | powershell -File scripts/keep-awake.ps1 -Minutes 2`) があり、stdin 経由の呼び出しは public interface とみなせる
- cc-nosleep 側のコードは**変更しない** (CLAUDE.md の不変条件「Claude Code 以外との統合は非目標」を尊重)

## アーキテクチャ

### コンポーネント

```
[Browser]
  ├─ <audio> element
  ├─ visibilitychange listener
  └─ keep-awake pinger (20秒間隔の setInterval)
            │ POST /api/keep-awake { client_id }
            ▼
[Flask app.py]
  └─ /api/keep-awake handler
            │ subprocess.Popen(powershell.exe keep-awake.ps1 -Minutes 2)
            │ stdin に {"session_id": "git-viewer-<client_id>"} を渡す
            ▼
[cc-nosleep keep-awake.ps1] (変更なし)
  └─ %TEMP%\claude-awake.deadline.git-viewer-<client_id> を更新 + watcher spawn
            ▼
[cc-nosleep awake-watcher.ps1] (変更なし、Claude Code session の deadline と同居)
```

### Ping の発動条件

フロント側で 20 秒間隔の `setInterval` を回す。各 tick で次を判定し、true の時だけ `/api/keep-awake` を POST:

```
shouldKeepAwake = !audio.paused || document.visibilityState === 'visible'
```

- `audio` 要素が無いページ (リポジトリ一覧など) では `audio.paused` の代わりに `false` を使う (= visibility のみで判定)
- `visibilitychange` で hidden に遷移した時に **即座に 1 回判定して必要なら ping 停止**、visible 復帰時には即 ping を撃って TTL を更新する (待ち時間 0 で再開)
- `play` イベントでも即 ping (タブ hidden + 音声再開のケースを取りこぼさない)

### TTL とタイミング

| パラメータ | 値 | 根拠 |
|---|---|---|
| ping 間隔 | 20 秒 | TTL の 1/6。瞬断 1〜2 回の許容 |
| TTL (`-Minutes`) | 2 (= 120 秒) | `keep-awake.ps1 -Minutes` は int 型で 1 分が最小級。1 分だと ping 1 回ロストで切れるので 2 分 |
| watcher tick | 30 秒 (cc-nosleep 既存) | 変更しない |
| Windows idle timer | 60 秒 (ユーザー設定) | 変更しない |

最悪ケース (停止から実スリープまで):

```
ping 停止
  → 最大 120 秒で deadline expire
  → 最大 30 秒後の watcher tick で release
  → 60 秒の Windows idle timer
  ─────────────
  合計 最大 ~3.5 分
```

要件「停止から 2-3 分後にスリープ」と最悪 3.5 分の間に約 30-60 秒のギャップがあるが、これは TTL を 1 分に下げると 1 ping ロストで切れる脆弱性とのトレードオフ。実用上問題なしと判断。

### session_id (client_id) の発行

ブラウザごとにランダム ID を発行し、`sessionStorage` に保存する。

- 同一ブラウザの複数タブが同じ ID を共有しても問題ない (deadline は最新タブの ping で更新される)
- 複数デバイス (PC のブラウザ + iPhone) は別 ID になり、それぞれ独立した deadline ファイルを持つ
- `sessionStorage` (タブ閉じで消える) で十分。`localStorage` だと古い ID が残り続ける可能性がある

ID フォーマット: `git-viewer-<8 桁の hex>` 程度のランダム文字列。`keep-awake.ps1` 側で `[^A-Za-z0-9_\-]` がサニタイズされるので英数 + ハイフンに収める。

### バックエンド `/api/keep-awake`

POST のみ。リクエスト body は `{ "client_id": "<random>" }`。

```python
KEEP_AWAKE_SCRIPT = load_keep_awake_script()  # config から読む or None

@app.route("/api/keep-awake", methods=["POST"])
def keep_awake():
    # Windows 以外 / cc-nosleep 未設定環境では feature OFF
    if sys.platform != "win32" or not KEEP_AWAKE_SCRIPT or not KEEP_AWAKE_SCRIPT.is_file():
        return ("", 204)
    data = request.get_json(silent=True) or {}
    client_id = data.get("client_id", "")
    # サニタイズ: 英数とハイフンのみ、長さ制限
    if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", client_id):
        abort(400)
    session_id = f"git-viewer-{client_id}"
    payload = json.dumps({"session_id": session_id}).encode("utf-8")
    try:
        proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(KEEP_AWAKE_SCRIPT), "-Minutes", "2"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc.stdin.write(payload)
        proc.stdin.close()
        # 待たない (fire-and-forget): keep-awake.ps1 自身は数十ms で終わる
    except OSError:
        # 起動失敗はログのみ。フロントの再生は止めない
        app.logger.warning("keep-awake.ps1 spawn failed", exc_info=True)
    return ("", 204)
```

#### スクリプトパスの設定化

`C:/code/cc-nosleep/scripts/keep-awake.ps1` を直接ハードコードせず、`config.local.json` に `keep_awake_script` キーを追加し、未設定なら sleep 抑止機能を OFF にする。

```json
{
  "code_dir": "C:/code",
  "keep_awake_script": "C:/code/cc-nosleep/scripts/keep-awake.ps1"
}
```

これで Raspberry Pi 上で動かしても (cc-nosleep は Windows 限定) エラーにならない。

#### 失敗時の挙動

- Windows 以外 OR スクリプト未配置 → 即 204 (feature OFF)
- subprocess 起動失敗 → `app.logger.warning` でログだけ出して 204 (フロントの再生は止めない)
- 成功時も 204。レスポンスボディなし

### フロントエンド実装ポイント

- ページロード時に **グローバルに 1 度だけ** `setInterval(tick, 20000)` を起動。再生成しない (audio 要素切り替えに連動させない)
- tick 内で毎回 `document.getElementById('audio-player')` を取り直す。要素が無い or `.paused === true` なら audio 条件 false
- `document.addEventListener('visibilitychange', ...)` で hidden→visible 時に即 1 回 ping
- audio に対しては bubbling phase の `play` イベントを `document.addEventListener('play', ..., true)` で拾う。これも即 ping
- `fetch('/api/keep-awake', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({client_id})}).catch(() => {})` で失敗は黙殺

#### audio 要素の動的な差し替え

`templates/index.html` の `selectFile` 内でファイルを切り替えるたびに `<audio id="audio-player">` を含む HTML を innerHTML で再生成する箇所がある。pinger は audio 要素に直接 listener を貼らず、tick ごとに `document.getElementById('audio-player')` を取り直して `.paused` を見る方式にすることで、要素差し替えの影響を受けない。`play` イベントは `document` の capturing phase で拾うので audio 要素差し替えにも追随する。

## エッジケース

- **複数タブで同じ音声を別の位置から再生**: 各タブの ID が同じ (sessionStorage 共有はタブごと) ので別 ID。問題なし
- **Wi-Fi 瞬断 1 回**: 20 秒 ping が 1 回失敗しても次の tick で復帰。TTL 120 秒なので持つ
- **ブラウザクラッシュ / タブ強制終了**: ping が来なくなり 120 秒で deadline expire。stale cleanup は cc-nosleep watcher が 1 時間後に行う
- **cc-nosleep watcher が Claude Code セッションで既に awake**: deadline ファイルは別名で共存。release-awake.ps1 は自分の sid のものしか消さないので干渉しない
- **PC ローカルのブラウザで開きっぱなし**: タブ visible なら 20 秒おきに ping → ずっと awake。これはユーザー意図通り。閉じれば停止
- **cc-nosleep スクリプトが無い環境** (新規 git clone した PC): config に `keep_awake_script` が無ければ feature 自体が無効。エラーにしない

## 非目標

- cc-nosleep スクリプトを変更すること (cc-nosleep の不変条件として明示されている)
- ディスプレイ ON 維持 (`ES_DISPLAY_REQUIRED`)
- Linux/macOS でのスリープ抑止
- ユーザーごとの ON/OFF 設定 UI (将来必要なら追加)
- iPhone のロック画面メディアコントロール統合 (HTML5 audio の標準挙動に任せる)

## テスト計画

手動テスト (Windows):

1. cc-nosleep が無い状態を作って `/api/keep-awake` POST → 500 にならず 204 を返す
2. cc-nosleep 有りでブラウザから音声再生開始 → `%TEMP%\claude-awake.deadline.git-viewer-*` ができる
3. タブを別ウィンドウに切り替えて hidden にしても、音声再生中は deadline 更新が続く
4. 音声停止 → 約 2 分で deadline expire → watcher が release ログを出す
5. Claude Code を別途起動した状態で git-viewer 側を停止 → watcher は Claude 側の deadline で生き続ける (干渉なし)
6. config に `keep_awake_script` キーを書かない → ping を投げてもエラーにならず 204、ファイルもできない
