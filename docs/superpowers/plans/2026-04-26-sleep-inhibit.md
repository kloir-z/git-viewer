# Sleep Inhibit (cc-nosleep 連携) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** git-viewer 利用中 (音声再生中 OR タブ visible) は Windows のスリープを抑止する。`C:\code\cc-nosleep` の `keep-awake.ps1` を git-viewer 専用 session_id で呼び出し、deadline ファイル機構に相乗りする。

**Architecture:** フロント側で 20 秒間隔の `setInterval` を回し、`!audio.paused || document.visibilityState === 'visible'` が true の時だけ `POST /api/keep-awake` を投げる。バックエンドは PowerShell の `keep-awake.ps1 -Minutes 2` を fire-and-forget で起動し、`%TEMP%\claude-awake.deadline.git-viewer-<id>` を更新する。cc-nosleep 側のコードは一切変更しない。

**Tech Stack:** Flask (既存), PowerShell (cc-nosleep 既存), HTML5 audio + vanilla JS (既存)

**Spec:** `docs/superpowers/specs/2026-04-26-sleep-inhibit-design.md`

**Test infrastructure note:** 本プロジェクトには pytest 等のテストハーネスが無いため、各タスクの verify ステップは curl / ファイル存在確認 / 手動ブラウザ操作で代替する。Flask 開発サーバーをローカルで `python app.py` 起動して確認する。

---

## File Structure

| ファイル | 役割 | 操作 |
|---|---|---|
| `app.py` | `load_keep_awake_script()` + `KEEP_AWAKE_SCRIPT` 定数 + `/api/keep-awake` route | Modify |
| `config.local.json.example` | 新キー `keep_awake_script` のドキュメント | Modify |
| `config.local.json` | ローカルパス設定 (gitignored) | Modify (動作確認用、コミット対象外) |
| `templates/index.html` | グローバル pinger の `<script>` ブロック | Modify (末尾の既存 `<script>` 内に追記) |

---

## Task 1: バックエンド設定ローダー追加

**Files:**
- Modify: `app.py:1-30` (import 追加 + `load_keep_awake_script()` 追加)
- Modify: `config.local.json.example`

- [ ] **Step 1.1: app.py の import に `sys` を追加**

`app.py` 1-9 行目を確認し、`import sys` を `import re` の後に挿入する:

```python
import json
import mimetypes
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, send_file
```

- [ ] **Step 1.2: `load_keep_awake_script()` 関数を追加**

既存の `load_code_dir()` (16-27 行目) の直後に以下を追加:

```python
def load_keep_awake_script() -> Path | None:
    """cc-nosleep keep-awake.ps1 のパスを config から取得する。
    未設定 or ファイル不在なら None (= sleep 抑止 feature OFF)。
    """
    if sys.platform != "win32":
        return None
    if not CONFIG_FILE.is_file():
        return None
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    raw = config.get("keep_awake_script")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None
```

- [ ] **Step 1.3: `KEEP_AWAKE_SCRIPT` 定数を初期化**

`CODE_DIR = load_code_dir()` (30 行目) の直下に追加:

```python
CODE_DIR = load_code_dir()
KEEP_AWAKE_SCRIPT = load_keep_awake_script()
```

- [ ] **Step 1.4: `config.local.json.example` に新キーを記載**

`config.local.json.example` を読み、既存の `code_dir` の後に `keep_awake_script` を追加:

```json
{
  "code_dir": "C:/code",
  "keep_awake_script": "C:/code/cc-nosleep/scripts/keep-awake.ps1"
}
```

(既存ファイルの正確なフォーマットを保ち、末尾コメントや改行を変えない)

- [ ] **Step 1.5: 構文確認**

```bash
python -c "import ast; ast.parse(open('C:/code/git-viewer/app.py').read())"
```

Expected: 何も出力されない (構文 OK)。

- [ ] **Step 1.6: 起動確認**

```bash
cd C:/code/git-viewer && python app.py
```

Expected: `* Running on http://...:5125` が出る。すぐ Ctrl+C で止める。`KEEP_AWAKE_SCRIPT` の値が `None` でないことを確認するため、別シェルで:

```bash
python -c "import sys; sys.path.insert(0,'C:/code/git-viewer'); from app import KEEP_AWAKE_SCRIPT; print(KEEP_AWAKE_SCRIPT)"
```

Expected: `C:\code\cc-nosleep\scripts\keep-awake.ps1` が表示される (config.local.json を Step 1.7 で先に更新する場合)。

- [ ] **Step 1.7: ローカル config.local.json も更新 (動作確認用、コミット対象外)**

`config.local.json` (gitignored) に `keep_awake_script` を追加する。Step 1.4 で example に書いたのと同じ内容。

- [ ] **Step 1.8: Commit**

```bash
git add app.py config.local.json.example
git commit -m "feat: add keep_awake_script config loader for cc-nosleep integration"
```

---

## Task 2: `/api/keep-awake` ルート追加

**Files:**
- Modify: `app.py` (末尾近く、既存の API ルート群の後)

- [ ] **Step 2.1: ルート追加位置を確認**

`app.py` を grep して既存ルートの末尾位置を特定:

```bash
grep -n "@app.route" C:/code/git-viewer/app.py
```

新ルートは末尾の `if __name__ == "__main__":` の直前に追加する。

- [ ] **Step 2.2: ハンドラ実装を追加**

末尾 (`if __name__ == "__main__":` の直前) に以下を挿入:

```python
@app.route("/api/keep-awake", methods=["POST"])
def keep_awake():
    """フロントから 20s 間隔で呼ばれ、cc-nosleep の TTL を 2 分に更新する。

    Windows 以外 / cc-nosleep 未設定なら 204 で no-op。
    """
    if KEEP_AWAKE_SCRIPT is None:
        return ("", 204)
    data = request.get_json(silent=True) or {}
    client_id = data.get("client_id", "")
    if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", client_id):
        abort(400)
    session_id = f"git-viewer-{client_id}"
    payload = json.dumps({"session_id": session_id}).encode("utf-8")
    creationflags = (
        subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    )
    try:
        proc = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(KEEP_AWAKE_SCRIPT),
                "-Minutes",
                "2",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        try:
            proc.communicate(input=payload, timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            app.logger.warning("keep-awake.ps1 hung, killed")
    except (OSError, BrokenPipeError):
        app.logger.warning("keep-awake.ps1 spawn failed", exc_info=True)
    return ("", 204)
```

- [ ] **Step 2.3: 構文確認**

```bash
python -c "import ast; ast.parse(open('C:/code/git-viewer/app.py').read())"
```

Expected: エラーなし。

- [ ] **Step 2.4: サーバー起動 + curl で動作確認 (有効な client_id)**

別シェルで:

```bash
cd C:/code/git-viewer && python app.py
```

別シェルで:

```bash
curl -i -X POST http://localhost:5125/api/keep-awake -H "Content-Type: application/json" -d '{"client_id":"abc12345"}'
```

Expected: `HTTP/1.1 204 NO CONTENT`。

その後、deadline ファイルが作られたか確認:

```bash
ls "$TEMP/claude-awake.deadline.git-viewer-abc12345" 2>/dev/null || ls "$env:TEMP/claude-awake.deadline.git-viewer-abc12345"
```

Expected: ファイルが存在する (PowerShell なら `$env:TEMP`、bash なら `$TEMP` 環境変数)。

- [ ] **Step 2.5: 不正な client_id で 400 を確認**

```bash
curl -i -X POST http://localhost:5125/api/keep-awake -H "Content-Type: application/json" -d '{"client_id":"bad id with spaces"}'
```

Expected: `HTTP/1.1 400 BAD REQUEST`。

```bash
curl -i -X POST http://localhost:5125/api/keep-awake -H "Content-Type: application/json" -d '{}'
```

Expected: `HTTP/1.1 400 BAD REQUEST` (空 client_id も regex 不一致)。

- [ ] **Step 2.6: 開発サーバーを停止**

Ctrl+C で `python app.py` を止める。

- [ ] **Step 2.7: Commit**

```bash
git add app.py
git commit -m "feat: add POST /api/keep-awake to refresh cc-nosleep deadline"
```

---

## Task 3: フロントエンド pinger 実装

**Files:**
- Modify: `templates/index.html` (末尾の `<script>` ブロック内)

- [ ] **Step 3.1: 既存 `<script>` ブロック末尾位置を確認**

```bash
grep -n "</script>" C:/code/git-viewer/templates/index.html | tail -5
```

最後の `</script>` の直前に追記する。

- [ ] **Step 3.2: pinger コードを追加**

最後の `</script>` の直前に以下を挿入:

```javascript
// --- cc-nosleep keep-awake pinger ---
(function() {
  const KEEP_AWAKE_INTERVAL_MS = 20000;
  let clientId = sessionStorage.getItem('keepAwakeClientId');
  if (!clientId) {
    clientId = 'c' + Math.random().toString(16).slice(2, 10);
    sessionStorage.setItem('keepAwakeClientId', clientId);
  }

  function shouldKeepAwake() {
    const audio = document.getElementById('audio-player');
    const audioPlaying = audio && !audio.paused;
    return audioPlaying || document.visibilityState === 'visible';
  }

  function ping() {
    if (!shouldKeepAwake()) return;
    fetch('/api/keep-awake', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId }),
      keepalive: true,
    }).catch(() => {});
  }

  setInterval(ping, KEEP_AWAKE_INTERVAL_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') ping();
  });
  document.addEventListener('play', ping, true);
  ping();
})();
```

- [ ] **Step 3.3: 構文確認 (Node で JS 単体パース)**

簡易的に、ブラウザで読み込めば構文エラーは即わかる。Node で確認するなら:

```bash
node --check -e "$(grep -A 999 'cc-nosleep keep-awake pinger' C:/code/git-viewer/templates/index.html | sed -n '/(function/,/})();/p')"
```

Expected: エラー出力なし。複雑なら Step 3.4 のブラウザ動作確認で兼ねてよい。

- [ ] **Step 3.4: サーバー起動 + ブラウザで pinger 動作確認**

```bash
cd C:/code/git-viewer && python app.py
```

ブラウザで `http://localhost:5125/` を開く。DevTools の Network タブで `/api/keep-awake` POST が 20 秒以内に発火するのを確認 (タブ visible なので即 ping → その後 20s 周期)。

Expected: ステータス 204、リクエスト body に `{"client_id":"c..."}`。

- [ ] **Step 3.5: 音声ファイル選択 → 再生で再ping を確認**

ブラウザでリポジトリ内の任意の音声ファイル (`.mp3` など) を選択して再生開始。Network タブで `play` イベント由来の即 ping を確認。

Expected: 再生開始直後に `/api/keep-awake` が POST される。

- [ ] **Step 3.6: タブを別ウィンドウに切り替えて hidden 状態を確認**

DevTools を開いたまま別ウィンドウに切り替え (タブ hidden)。音声を停止しておく。Console で `document.visibilityState` を見るには戻ってから確認するしかないので、このステップは Network タブの ping が止まるかで間接確認する。

Expected: hidden + audio paused では ping が止まる (次の tick で `shouldKeepAwake() === false` になる)。

- [ ] **Step 3.7: 開発サーバーを停止**

Ctrl+C。

- [ ] **Step 3.8: Commit**

```bash
git add templates/index.html
git commit -m "feat: ping /api/keep-awake while audio plays or tab is visible"
```

---

## Task 4: サービス再起動 + エンドツーエンド動作確認

**Files:** なし (動作確認のみ)

- [ ] **Step 4.1: git-viewer サービス再起動**

CLAUDE.md の指示通り:

```bash
powershell -Command "Start-Process powershell -ArgumentList '-Command','Restart-Service git-viewer' -Verb RunAs"
```

Expected: UAC プロンプトの後、サービスが再起動する。エラーが出たら手動で `Get-Service git-viewer` で状態確認。

- [ ] **Step 4.2: ブラウザから音声再生 + deadline ファイル生成確認**

PC ブラウザで `http://localhost:5125/` を開いて音声ファイルを選択・再生。PowerShell で:

```powershell
Get-ChildItem $env:TEMP -Filter 'claude-awake.deadline.git-viewer-*'
```

Expected: 1 つ以上のファイル。`Get-Content <file>` で ISO 8601 の deadline タイムスタンプ (約 2 分後) が入っている。

- [ ] **Step 4.3: cc-nosleep watcher の起動確認**

```powershell
Get-Content $env:TEMP\claude-awake.pid
Get-Process -Id (Get-Content $env:TEMP\claude-awake.pid)
```

Expected: PID が表示され、その PID の powershell.exe が動いている。

```powershell
Get-Content $env:TEMP\claude-awake.log -Tail 5
```

Expected: 直近に `keep-awake called sid=git-viewer-...` や `awake until ...` のログ。

- [ ] **Step 4.4: 音声停止 → 抑止解除確認 (約 3 分待機)**

ブラウザで音声を停止し、タブを閉じる (or 別アプリへ切り替えて hidden に)。約 3 分後:

```powershell
Get-ChildItem $env:TEMP -Filter 'claude-awake.deadline.git-viewer-*'
Get-Content $env:TEMP\claude-awake.log -Tail 10
```

Expected: deadline ファイルが消えている (cc-nosleep watcher の stale cleanup は 1 時間後だが、watcher 自身は deadline expire で release を出す)。ログに `released` または `idle timeout, exiting` のエントリ。

- [ ] **Step 4.5: iPhone から最終動作確認**

iPhone Safari で Tailscale 経由で git-viewer を開き、音声再生 → アプリ切り替えでバックグラウンド化 → スリープ抑止が継続することを確認。再生停止 → 約 3 分でスリープに入ることを確認 (PC のディスプレイ OFF / 起動音確認等で判定)。

Expected: 音声再生中はスリープしない。停止後 2-3 分でスリープ。

- [ ] **Step 4.6: マルチセッション干渉確認 (任意)**

別途 Claude Code を起動した状態で git-viewer 側のブラウザを閉じ、Claude Code の Stop hook が走っても git-viewer の deadline は消えないこと、逆も同様であることを確認:

```powershell
Get-ChildItem $env:TEMP -Filter 'claude-awake.deadline.*'
```

Expected: `git-viewer-*` と Claude session_id 由来のファイルが共存。release-awake は自セッションしか消さない (cc-nosleep の不変条件)。

---

## Self-Review チェック結果

**Spec coverage:**
- [x] 要件「音声再生中ON / タブvisibleON / 両方offで~3分でOFF」→ Task 3 Step 3.2 の `shouldKeepAwake()` で表現
- [x] cc-nosleep keep-awake.ps1 を `-Minutes 2` で呼ぶ → Task 2 Step 2.2
- [x] session_id `git-viewer-<client_id>` フォーマット → Task 2 Step 2.2
- [x] sessionStorage で client_id 永続化 → Task 3 Step 3.2
- [x] 20s ping 間隔 → Task 3 Step 3.2
- [x] visibilitychange + play イベント即 ping → Task 3 Step 3.2
- [x] config.local.json の `keep_awake_script` → Task 1 Step 1.2 + 1.4
- [x] sys.platform != "win32" ガード → Task 1 Step 1.2 (loader 内で `None` 返却)
- [x] CREATE_NO_WINDOW + CREATE_NEW_PROCESS_GROUP → Task 2 Step 2.2
- [x] proc.communicate(timeout=5) → Task 2 Step 2.2
- [x] OSError / BrokenPipeError catch → Task 2 Step 2.2
- [x] サニタイズ regex → Task 2 Step 2.2
- [x] feature OFF 時も 204 → Task 2 Step 2.2 (`KEEP_AWAKE_SCRIPT is None` で早期 return)
- [x] release-awake 不使用 (TTL expire のみ) → Task 4 で動作確認

**Placeholder scan:** TBD/TODO なし。各 Step に実コード or 実コマンド入り。

**Type consistency:** `KEEP_AWAKE_SCRIPT` (Task 1) と `keep_awake()` 内参照 (Task 2) で一致。`client_id` regex とフロント生成側の文字種が一致 (英数 + ハイフン)。

問題なし。
