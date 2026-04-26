# File Notes (サイドカーメモ機能) 設計

## 背景と目的

git-viewer でテキストファイル（コード・MD・SRT 等）を閲覧していて、特定箇所に対してメモを残したくなることがある。自分用の備忘でも、レビュー指摘を AI エージェント／第三者に申し送る用途でも使える。MP3/WAV と SRT の関係に倣い、**対象ファイルと同階層に置くサイドカー Markdown ファイル**にメモを蓄積する仕組みを作る。

## 要件

- 対象ファイルの隣に `<filename.ext>.notes.md` を作成し、メモはセクション単位で書く
- 対象ファイルの種別ごとに「メモを付ける単位（アンカー）」が変わる:
  - **SRT**: 字幕タイムコード単位
  - **MD**: 文単位（既存の md-sentence-bookmark と同じ単位）
  - **テキスト/コード（その他 `TEXT_EXTS` 全般）**: 行範囲単位
- メモ閲覧側 UI:
  - 該当行/字幕/文の右側に吹き出しアイコン 💬 を表示
  - クリックでメモを展開・編集
  - メモのないアンカーには「追加」ボタンが出る
  - ファイル一覧（左ペイン）には件数バッジ（💬3 等）を表示
- メモ編集側機能: 作成 / 編集 / 削除（セクション単位）
- 1 アンカー 1 メモ。複数の話題はメモ本文内で箇条書き等で区切る運用
- 対象ファイル本体が編集されてアンカーがズレた場合の挙動:
  - **テキスト/コード**: スナップショット (full text) と比較し、不一致なら元位置 ±50 行を検索して自動再アンカー。見つからなければ「未解決メモ」扱い
  - **MD**: `S<index>` でマッチしなければスナップショット (full text) でフォールバック検索。見出しの「冒頭 30 文字」は人間/AI 向けの可読性のためで、マッチには使わない
  - **SRT**: タイムコード完全一致のみ。不一致なら未解決
  - 未解決メモはファイル UI 上で別領域（「未解決メモ」一覧）に表示。自動削除しない
- 作成/更新日時は記録しない（git で追える）
- `.notes.md` は元ファイルと同じ git 管理（`.gitignore` に追加しない）

## 非目標

- `.notes.md` 全体を対象とした上級者編集モード（必要なら `.notes.md` をそのまま開いて編集すれば足りる）
- バイナリファイル（画像・PDF・音声等）へのメモ付与
- メモのコメントスレッド／返信構造
- 複数ユーザー間の同時編集制御（単独ユーザー想定）
- メモのフルテキスト検索 UI（将来必要なら追加）
- `.notes.md` 自体に対するメモ（再帰的サイドカー）

## `<filename.ext>.notes.md` ファイルフォーマット

### 命名規則

- 対象ファイルが `foo/bar.srt` なら `foo/bar.srt.notes.md`
- 拡張子を含めたフルファイル名にサフィックス `.notes.md` を付与する。これにより `bar.srt` と `bar.txt` のメモが衝突しない
- `.notes.md` 自体にはメモを付けられない（無限再帰防止）

### ファイル全体構造

```markdown
# Notes for <filename.ext>

## <アンカー1>

<!--snapshot:{...JSON...}-->

メモ本文（フリーフォーム Markdown）

## <アンカー2>

<!--snapshot:{...JSON...}-->

メモ本文

## Unresolved

### <元アンカー>

<!--snapshot:{...JSON...}-->

未解決理由: <自動付記>

メモ本文
```

ルール:

- ファイル先頭の `# Notes for <filename.ext>` は人間向けタイトル。パーサは行頭 `# ` を見出し検出に使うが、内容は表示用としてのみ使用する
- 解決済みセクションは `## <アンカー>` で始まる
- 未解決セクションは `## Unresolved` の下に `### <元アンカー>` のサブセクションとして集約する
- 各セクション本文の冒頭にスナップショット用の HTML コメント `<!--snapshot:{JSON}-->` を 1 行で埋め込む（後述）
- 同一見出しのセクションは存在しない（1 アンカー 1 メモ）。重複検出時はパーサ側で先勝ちにし、警告ログを残す
- アンカー形式（後述の正規表現）に合致しない `##` 見出しはパーサが無視する。これによりユーザーが任意の見出しを追加しても壊れない
- セクションの並び順: `# Notes for ...` → 解決済みセクション群（種別ごとに座標順: 行番号 / `start_ms` / `index` の昇順）→ `## Unresolved` → 未解決サブセクション群（同様に座標順）。`PUT` 時はサーバ側がこの順序を維持してシリアライズする

### アンカー見出し書式

| 種別 | 見出し書式 | 例 |
|---|---|---|
| SRT | `## <開始タイム> --> <終了タイム>` | `## 00:01:23,456 --> 00:01:30,000` |
| MD | `## S<index> "<冒頭テキスト...>"` | `## S42 "これはサンプルの文章で、もう少し長..."` |
| テキスト/コード（範囲） | `## L<start>-<end>` | `## L10-15` |
| テキスト/コード（単行） | `## L<n>` | `## L10` |

冒頭テキストの長さ: 30 文字 + 省略記号 `...`（30 文字以下なら省略記号なし）。改行・連続空白は単一空白に正規化、ダブルクォートは `\"` でエスケープ。

#### 見出しパース正規表現

```python
HEADING_LINES = re.compile(r"^L(\d+)(?:-(\d+))?$")
HEADING_MD = re.compile(r'^S(\d+)(?:\s+"((?:[^"\\]|\\.)*)")?$')
HEADING_SRT = re.compile(r"^(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})$")
HEADING_UNRESOLVED = re.compile(r"^Unresolved$")
```

`## ` または `### ` を取り除いた残りに対して上記を順に試す。どれにも合致しなければ「アンカーでない見出し」として無視。

### スナップショット (`<!--snapshot:{JSON}-->`) 仕様

スナップショットは「アンカー解決」と「未解決判定」の両方に使う構造化データ。HTML コメントなので Markdown レンダラに無視され、人間が編集する際にも可視で扱える。

#### 種別ごとの中身

```json
// テキスト/コード（行範囲）
{"kind": "lines", "start": 10, "end": 15, "text": "fn foo(x: u32) -> u32 {\n    x + 1\n}\n"}

// MD（文単位）
{"kind": "md_sentence", "index": 42, "text": "これはサンプルの文章で、もう少し長いとき省略する。"}

// SRT（タイムコード）
{"kind": "srt", "start_ms": 83456, "end_ms": 90000, "cue_index": 12, "text": "字幕本文"}
```

- `text` は対象範囲のテキストそのもの（改行含む）。マッチング正規化（後述）に使う
- SRT の `cue_index` は SRT ファイル内の連番（1 始まり）。タイムコード一致が外れたケースの参考情報として保持するが、未解決判定には使わない（要件どおりタイムコード完全一致のみ）
- MD の `index` は md-sentence-bookmark の `data-bm-idx` と同じ採番ロジックで決まる値

#### スナップショット書式の制約

- HTML コメント開始 `<!--snapshot:` の直後に JSON、末尾 `-->` で閉じる
- JSON は 1 行に圧縮（改行を含めない。`text` 内の改行は `\n` エスケープで表現）
- 改行を許してしまうとパースが複雑化するため、必ず 1 行ルールで運用する

### 未解決セクションへの移行

サーバが `.notes.md` を読み出して各セクションを解決しようとしたとき、解決失敗したものを `## Unresolved` 配下に移す:

- 元のアンカー見出し（`## L10-15` 等）はそのまま `### L10-15` に降格
- `<!--snapshot:...-->` はそのまま保持（再アンカー時の手がかり）
- 「未解決理由: <自動付記>」を 1 行追加（例: `未解決理由: ファイルの行数が10未満になったため`）
- ユーザー本文はそのまま保持

逆方向の昇格（未解決→解決）は、ユーザーが手動でアンカーを書き直すか、UI 上で再アンカー操作した場合に発生する。スキャン時の自動昇格は行わない（誤マッチを避けるため）。

## アンカー解決ロジック

### 共通フロー

サーバ側で `GET /api/notes` 時に各セクションを以下の順で解決する:

1. アンカー見出しから種別と座標を抽出
2. 対象ファイルの最新内容を読み出す
3. 種別ごとの解決ロジックを適用
4. 成功 → 解決済みリストへ。失敗 → 未解決リストへ
5. 解決中にスナップショットの位置がズレた場合は、`.notes.md` 上のアンカー見出しを**書き換えて保存**する（自動再アンカー）

### テキスト/コード（行ベース）

```
def resolve_lines(file_lines, snap):
    # 1) スナップショットの内容と現在のテキストが完全一致するか確認
    current = "\n".join(file_lines[snap.start - 1 : snap.end])
    if normalize(current) == normalize(snap.text):
        return Resolved(snap.start, snap.end)

    # 2) ±50 行以内で同じテキストブロックを検索
    snap_lines = snap.text.splitlines()
    block_size = len(snap_lines)
    search_min = max(1, snap.start - 50)
    search_max = min(len(file_lines) - block_size + 1, snap.end + 50)

    candidates = []
    for i in range(search_min, search_max + 1):
        chunk = "\n".join(file_lines[i - 1 : i - 1 + block_size])
        if normalize(chunk) == normalize(snap.text):
            candidates.append(i)

    if not candidates:
        return Unresolved(reason="行範囲のテキストが見つからなかった")

    # 3) 元の位置に最も近いものを選ぶ
    best = min(candidates, key=lambda i: abs(i - snap.start))
    return Resolved(best, best + block_size - 1, relocated=True)
```

`normalize`: 末尾改行の有無を吸収するため、各行の末尾空白を除去し、最終改行を除いた文字列で比較する。これ以上の正規化（インデント変更等）はしない（誤マッチを増やすため）。

スナップショット欠損時のフォールバック（`.notes.md` を手で書いてスナップショットがない場合）: 元の `start..end` がファイル範囲内にあれば解決済みとみなす。範囲外なら未解決。

### MD（文単位）

```
def resolve_md_sentence(rendered_sentences, snap):
    # 1) S<index> がそのまま生きているか
    if snap.index < len(rendered_sentences):
        if normalize(rendered_sentences[snap.index]) == normalize(snap.text):
            return Resolved(index=snap.index)

    # 2) 冒頭テキストでフォールバック
    matches = [
        i for i, s in enumerate(rendered_sentences)
        if normalize(s) == normalize(snap.text)
    ]
    if not matches:
        return Unresolved(reason="同一の文が見つからなかった")
    if len(matches) == 1:
        return Resolved(index=matches[0], relocated=True)

    # 3) 複数候補時は元 index に最も近いもの
    best = min(matches, key=lambda i: abs(i - snap.index))
    return Resolved(index=best, relocated=True)
```

`rendered_sentences` の生成: サーバ側では Markdown を文単位に分割しない（フロントの marked.js + `splitMdIntoSentences` がやる仕事）。よって MD のアンカー解決は**フロント側で行う**。サーバは見出しから抽出した `index` と `snap.text` を返すだけで、解決判定はフロントの `splitMdIntoSentences` 後に行う。

つまり実装上、API が返すデータに「アンカー（生）」「スナップショット」「種別」を含め、未解決判定はクライアント側で行う方が筋が良い。種別ごとに次の方針:

- **SRT / テキスト/コード**: サーバ側で対象ファイルを読めるので、サーバ側で解決判定して結果を返す。自動再アンカーによる `.notes.md` 書き換えもサーバ側で行う
- **MD**: サーバはアンカーとスナップショットを返すだけ。フロント側の `showBlob()` でレンダリング後に解決判定。自動再アンカー（heading 書き換え）はクライアントから `POST /api/notes/relocate`（後述）を呼んで実現する。レイテンシ削減のため、表示自体はフォールバック結果に基づき即座に行い、書き戻しはバックグラウンドで投げる

### SRT

```
def resolve_srt(cues, snap):
    target = (snap.start_ms, snap.end_ms)
    for cue in cues:
        if (cue.start_ms, cue.end_ms) == target:
            return Resolved(cue=cue)
    return Unresolved(reason="該当タイムコードの字幕が見つからなかった")
```

`cues` は `.srt` をパースした結果。タイムコードのフォーマット差異（`,` vs `.`、空白）はパース段階で吸収済み（ミリ秒整数で比較）。

### 自動再アンカー時の書き戻し

サーバ側で `relocated=True` だった場合、`.notes.md` の該当セクション見出しを新しい座標に置き換えて即座に保存する。これにより次回以降のスキャンが速くなる。

書き戻しのアトミック性: `.notes.md` への書き込みは `tempfile + os.replace` でアトミックに行う（途中で落ちても破損しない）。

並行アクセス制御: 単独ユーザー想定なので排他ロックまでは要らないが、最低限「読み出し→書き込み」の間にユーザーが手動で `.notes.md` を編集してしまった場合の競合は考慮する。具体的には:

- `GET /api/notes` 時に `.notes.md` の `mtime` を返す
- `PUT /api/notes` のリクエストにその `mtime` を `if_match_mtime` として含めてもらう
- サーバ側で書き込み直前に `mtime` を再取得し、不一致なら 409 Conflict で拒否
- フロント側はリロードしてやり直し

これは編集系すべて（`PUT`, `DELETE`）に適用する。

## アーキテクチャ

### コンポーネント

```
[Browser]
  ├─ ファイル一覧 (左ペイン)
  │   └─ メモ件数バッジ取得 (notes index)
  ├─ ファイル表示 (中央/右ペイン)
  │   ├─ 行/字幕/文の右側に 💬 マーカー
  │   ├─ 「メモを追加」ボタン (該当アンカーにメモが無い場合)
  │   ├─ メモ展開・編集 UI (モーダル or インラインパネル)
  │   └─ 「未解決メモ」一覧パネル
  └─ /api/notes 系を呼び出し
            ▼
[Flask app.py]
  ├─ GET /api/notes?repo=&path=
  ├─ PUT /api/notes
  ├─ DELETE /api/notes
  ├─ GET /api/notes/index?repo=&path=  (件数取得)
  ├─ ヘルパ: notes.py (パーサ・シリアライザ・解決ロジック)
  │   ├─ parse_notes_md(text) -> NotesDoc
  │   ├─ serialize_notes_md(NotesDoc) -> str
  │   ├─ resolve_anchors(NotesDoc, target_file) -> ResolvedNotesDoc
  │   └─ atomic_write_notes(path, NotesDoc) -> mtime
  └─ 既存 /api/blob, /api/tree 等は変更しない
```

`notes.py` は新規モジュール。`app.py` から `from notes import ...` で使う。app.py の肥大化を避けるため、パース／シリアライズ／解決の純粋ロジックはここに切り出す。

### データフロー（メモ閲覧）

1. ファイル選択 → フロントが `GET /api/blob` でファイル本体を取得
2. 並行して `GET /api/notes?repo=&path=` を呼ぶ
3. サーバ:
   - `<path>.notes.md` が存在しなければ `{"resolved": [], "unresolved": [], "mtime": null}` を即返す
   - 存在すればパース → 種別ごとに解決判定
   - 自動再アンカーが発生したらアトミック書き戻し → 新しい `mtime` を含めて返す
4. フロント:
   - 解決済みメモを該当行/字幕/文の横に 💬 アイコンで表示
   - 未解決メモはパネルに集約表示
   - MD の場合のみ、フロント側でレンダリング後に再度解決判定（必要なら `PUT /api/notes` で書き戻し）

### データフロー（メモ作成・編集・削除）

```
ユーザーが「メモを追加」をクリック
  → モーダル表示。アンカーは現在の選択箇所から自動決定
  → ユーザーがメモ本文を入力 → 保存
  → フロントがアンカー・スナップショット・本文を組み立てて PUT /api/notes
  → サーバ: 既存セクションがあれば上書き、無ければ追加
  → アトミック書き込み → 新 mtime 返却
  → フロント: マーカー再描画
```

削除も同様（`DELETE /api/notes`）。最後の 1 セクションを削除した場合はファイル全体を削除する。`# Notes for ...` ヘッダ行と未解決セクションが残っているなら削除しない。

### API 詳細

#### `GET /api/notes?repo=<name>&path=<file>`

レスポンス:

```json
{
  "mtime": 1714200000.0,
  "kind": "lines",
  "resolved": [
    {
      "anchor": {"kind": "lines", "start": 10, "end": 15},
      "snapshot": {"kind": "lines", "start": 10, "end": 15, "text": "..."},
      "body": "メモ本文 Markdown",
      "relocated": false
    }
  ],
  "unresolved": [
    {
      "raw_anchor": "L120-130",
      "snapshot": {"kind": "lines", "start": 120, "end": 130, "text": "..."},
      "body": "メモ本文",
      "reason": "行範囲のテキストが見つからなかった"
    }
  ]
}
```

トップレベルの `kind` はファイル種別判定の結果（`"lines"` | `"md_sentence"` | `"srt"`）。フロントはこれを見て描画方針を切り替える。

`.notes.md` が存在しない場合は `{"mtime": null, "kind": "<種別>", "resolved": [], "unresolved": []}`。

#### MD ファイルでの挙動

`path` の拡張子が `.md` の場合、サーバは `S<index>` の解決判定をスキップして、すべての MD セクションを `resolved` リストに以下の形で入れて返す:

```json
{
  "anchor": {"kind": "md_sentence", "index": 42, "heading_text": "これはサンプルの文章で、もう少し長..."},
  "snapshot": {"kind": "md_sentence", "index": 42, "text": "<full sentence>"},
  "body": "メモ本文",
  "relocated": false,
  "client_resolve": true
}
```

`client_resolve: true` のフラグでフロントに「この `index` は仮値、自分でレンダリング後に解決して」と伝える。フロントは `splitMdIntoSentences` 後に `snapshot.text` でマッチング → 必要なら `POST /api/notes/relocate` で書き戻し。

スナップショット欠損 (`snapshot` が `null`) の MD セクションは index のみで判定。これも未解決判定はフロント任せ。

#### `PUT /api/notes`

リクエスト:

```json
{
  "repo": "<name>",
  "path": "<file>",
  "if_match_mtime": 1714200000.0,
  "anchor": {"kind": "lines", "start": 10, "end": 15},
  "snapshot": {"kind": "lines", "start": 10, "end": 15, "text": "..."},
  "body": "新しいメモ本文"
}
```

挙動:

- 既存セクションがあれば本文と snapshot を上書き
- 無ければ追加。アンカー位置順（テキストは行番号、SRT はタイムコード、MD は index）でソートして挿入
- `.notes.md` が存在しなければ新規作成（`# Notes for <filename>` ヘッダ付き）
- `if_match_mtime` 不一致 → 409 Conflict
- `if_match_mtime: null` で `.notes.md` が既に存在する場合 → 409（クライアントの状態が古い）
- レスポンス: `{"mtime": <新mtime>}`

#### `DELETE /api/notes`

リクエスト:

```json
{
  "repo": "<name>",
  "path": "<file>",
  "if_match_mtime": 1714200000.0,
  "anchor": {"kind": "lines", "start": 10, "end": 15}
}
```

挙動:

- 該当セクションを削除
- 削除後、resolved/unresolved 両方が空になったらファイルごと削除
- `if_match_mtime` 不一致 → 409
- レスポンス: `{"mtime": <新mtime or null>}`（ファイルごと削除なら null）

#### `POST /api/notes/relocate`

MD のフロント側自動再アンカー専用。サーバ側で対象 MD を再レンダリングできないため、クライアントが新アンカーを通知してサーバが見出しだけ書き換える。

リクエスト:

```json
{
  "repo": "<name>",
  "path": "<file>",
  "if_match_mtime": 1714200000.0,
  "old_anchor": {"kind": "md_sentence", "index": 42},
  "new_anchor": {"kind": "md_sentence", "index": 40},
  "new_heading_text": "これはサンプルの文章で、もう少し長..."
}
```

挙動:

- 該当セクションを見つけて見出しのみ `## S40 "<new_heading_text>"` に書き換え
- 本文・スナップショットは保持
- `if_match_mtime` 不一致 → 409
- 該当セクションが見つからない → 404
- レスポンス: `{"mtime": <新mtime>}`

このエンドポイントは MD 専用。テキスト/コード・SRT の再アンカーはサーバ側で `GET /api/notes` 内に閉じて行う。

#### `GET /api/notes/index?repo=<name>&path=<dir>`

ファイル一覧バッジ用。指定ディレクトリ直下の各ファイルについて、`<file>.notes.md` の有無とメモ件数（resolved + unresolved の合計）を返す:

```json
{
  "files": {
    "main.py": 3,
    "video.srt": 1
  }
}
```

実装は単純に `<dir>` 内の `*.notes.md` を列挙して、それぞれをパースして件数を数える。1 ディレクトリあたりの注釈ファイル数は通常少ないので逐次処理で十分。

`/api/tree` のレスポンスを拡張する選択肢もあるが、メモ機能だけのために tree を肥大化させたくないので独立エンドポイントにする。

### バックエンドの既存仕組みとの関係

- `valid_repo()` でパス検証 → 既存どおり
- `path` のバリデーション (`..` 拒否、絶対パス拒否) → 既存パターンを踏襲
- ファイル書き込み → `PUT /api/blob` と同じパスチェック規則を再利用
- `.notes.md` の MIME 判定: 既存の `TEXT_EXTS` に `.md` が含まれているのでそのまま `/api/blob` で開ける。ユーザーが直接編集することも妨げない

## UI

### マーカー表示

- **テキスト/コード**: 行番号の右側ガターに 💬 アイコン。複数行にまたがるメモは開始行に 1 つだけ表示
- **MD**: 文単位の `<span class="bm-target">` の右側にインライン表示
- **SRT**: 字幕表示の右側に表示（既存の SRT レンダラに依存）

クリック時の挙動: 同じ場所で展開（インラインパネル or モーダル）。編集・削除ボタンが含まれる。

メモが存在しないアンカーへの「追加」ボタン: 別のアイコン（`+💬` のような薄いプレースホルダ）でホバー時に出る、もしくは右クリックメニュー。詳細は実装フェーズで調整。

### 未解決メモパネル

ファイル表示の下部または右側に折りたたみ可能なパネル「未解決メモ (N)」。クリックで展開し、各メモを以下の形式で表示:

```
[L120-130] (理由: 行範囲のテキストが見つからなかった)
スナップショット: fn foo(x: u32) -> u32 {...
本文: <メモ本文>
[再アンカー] [削除]
```

「再アンカー」: ユーザーがファイル内の新しい範囲を選択して紐付け直す UI（実装は段階的でよい。最初は手動で `.notes.md` を編集してもらう運用も可）。

### ファイル一覧バッジ

左ペインのファイル名の右側に `💬3` のような小さなバッジ。0 件なら表示しない。バッジは `GET /api/notes/index` で取得。

## セキュリティと堅牢性

- **パストラバーサル**: 既存の `valid_repo` + `repo_path.resolve()` チェックで防御。`.notes.md` のパスも同じく `repo_path` 配下に収まることを確認
- **巨大スナップショット**: 1 セクション内の `text` フィールド長に上限を設ける（例: 50KB）。それを超えるアンカーは作成不可（API レイヤで弾く）。テキスト/コードで超巨大関数を選択するケースを想定
- **`.notes.md` の壊れ JSON**: スナップショット JSON のパース失敗時はそのセクションを「スナップショット欠損」扱いとし、見出しの座標だけでベストエフォート解決
- **書き込み権限**: 既存の `PUT /api/blob` が動いている時点で当該ディレクトリへの書き込み権限はある前提。失敗時は 500 を返す
- **書き込み中の SIGINT 等**: `tempfile + os.replace` でアトミックに書き込めば破損しない
- **同時書き込み**: `if_match_mtime` チェックで楽観的ロック。複数タブで同じファイルを開いて両方からメモを書き換えると後勝ちが拒否される

## エッジケース

| ケース | 挙動 |
|---|---|
| 対象ファイルが削除された | `.notes.md` は残る。サーバはファイル不在を検知したら全セクション未解決として返す |
| `.notes.md` だけ存在し対象が無い | 上記と同じ |
| `.notes.md` 自体が壊れている | パース失敗。500 ではなく `{"resolved":[], "unresolved":[], "parse_error": "..."}` を返してフロントで警告表示 |
| 対象ファイルがバイナリ（誤って `.notes.md` を作成） | サーバは `TEXT_EXTS` チェックで弾く（`.notes.md` 作成自体を拒否）。既に存在する場合は読み出しのみ可、編集は不可 |
| 同一ファイル名で大文字小文字違い | 通常のファイルシステム挙動に従う（Windows は同一視、Linux は別物）。git-viewer は OS に従う |
| シンボリックリンク経由 | `repo_path.resolve()` で実体パスに正規化されるので、リポジトリ外を指していれば 403 |
| `.notes.md` を直接編集される | `mtime` ベースで楽観的ロックがかかるので、UI 側の操作とは衝突せず、単に 409 が返る |
| 1 ファイルに大量のメモ（数百件） | パースは線形だが現実的な件数なら問題なし。10,000 件規模を想定するなら別設計（YAGNI なので保留） |
| MD の `splitMdIntoSentences` の挙動が変わる | 既存しおりと同じく index 体系がズレる。冒頭テキストフォールバックで多くは救えるが、稀に未解決化する |
| SRT のタイムコードが微秒単位で変わる | 完全一致のみなので未解決になる。意図通り（ユーザーに気づいてもらう） |

## テスト計画

### 単体テスト（`notes.py`）

`tests/test_notes.py` を追加:

1. `parse_notes_md` ラウンドトリップ: パース→シリアライズで等価
2. アンカー見出し書式の正規化（30 文字 + `...`、ダブルクォートエスケープ）
3. スナップショット JSON エンコード/デコード（改行を含む `text`、Unicode）
4. テキスト/コードの解決ロジック:
   - 完全一致時に `relocated=False`
   - ±50 行内に再配置時に `relocated=True`
   - 範囲外で未解決
   - 複数候補時に元位置に最も近いものを選択
5. SRT 解決: 完全一致 / 不一致
6. アトミック書き込み: 途中失敗で元ファイルが残る

### 統合テスト（手動）

1. 新規ファイルにメモ追加 → `.notes.md` 生成、件数バッジ表示
2. 既存メモ編集 → 上書きされる
3. メモ削除 → セクション消失、最後の 1 件消すと `.notes.md` ごと削除
4. ファイル本体に行を追加してメモがズレる → 自動再アンカー
5. ファイル本体を大幅に変更 → 未解決メモ一覧に表示
6. SRT のタイムコードが完全一致しないと未解決
7. MD の文を編集して `S<index>` がズレる → 冒頭テキストでフォールバック
8. 複数タブで同じファイルを編集 → 409 Conflict が出る
9. `.notes.md` を手動編集 → サーバが許容（壊れ JSON はベストエフォート）
10. パストラバーサル（`../etc/passwd` 等）→ 403
11. 巨大スナップショット（50KB 超）→ API が拒否

## 実装順序の見当（writing-plans へ持ち越し）

1. `notes.py` のパーサ・シリアライザ（テスト先行）
2. アンカー解決ロジック（テスト先行）
3. `/api/notes` 系エンドポイント
4. フロントの読み込み・マーカー表示（編集 UI なし）
5. フロントの作成・編集・削除 UI
6. ファイル一覧バッジ
7. 未解決メモパネル
8. MD のフロント側解決判定統合

詳細な実装計画は別途 `docs/superpowers/plans/2026-04-26-file-notes.md` に書き出す。
