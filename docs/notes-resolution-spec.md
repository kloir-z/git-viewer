# Notes resolution spec

セクション (アンカー) ごとに「反映済み / 未反映 / 反映不要」の状態を持たせるための仕様。`*.notes.md` のフォーマットを壊さないよう、既存の snapshot HTML コメント内に `resolution` フィールドを追加する形を取る。

## 動機

`output.srt.notes.md` のような notes ファイルには、複数のセクションが混在する:

- 読み崩れを `YOMI_DICT` に反映すべきもの (未反映 → 反映済み に遷移する)
- 演出フィードバック (script-author の制約に反映する)
- 個人感想で反映対象外のもの

これを区別せずに溜めると「どこまで読んだ / 何が残っているか」が読み手にわからない。セクション単位でステータスを持たせて棚卸し可能にする。

## スキーマ

各セクションの snapshot JSON に `resolution` フィールドを (任意で) 追加する。

```json
{
  "kind": "srt",
  "start_ms": 281260,
  "end_ms": 290300,
  "cue_index": 35,
  "text": "...",
  "created_at": "2026-05-22T08:23:23+09:00",
  "updated_at": "2026-05-22T08:23:23+09:00",
  "resolution": {
    "status": "done",
    "resolved_at": "2026-05-23T14:00:00+09:00",
    "ref": "16a1943"
  }
}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `status` | `"todo"` \| `"done"` \| `"wontfix"` | ○ | 反映状態 |
| `resolved_at` | ISO-8601 文字列 | done/wontfix で推奨 | status を todo 以外に遷移させた時刻 (`set_resolution` は JST `+09:00` で自動生成) |
| `ref` | 文字列 | 任意 | 反映先へのポインタ。commit hash / PR URL / 「個人感想のため対象外」のような自由文 |

### 後方互換

`resolution` フィールドが**無い**セクションは `{"status": "todo"}` として扱う (`get_resolution()` のデフォルト)。既存の notes ファイル (5/22 以前のもの) はそのまま「未反映」扱いになる。

### 最小化規則

`set_resolution(snap, "todo")` を呼ぶと `resolution` フィールド自体が削除される。todo == 既定状態なので明示的に書かない。これによりまだ何もしていないセクションの snapshot が肥大化しない。

## API (notes.py)

```python
from notes import (
    RESOLUTION_STATUSES,        # ("todo", "done", "wontfix")
    get_resolution,              # snapshot -> {"status": ..., "resolved_at"?: ..., "ref"?: ...}
    set_resolution,              # snapshot を in-place で書き換え
    count_sections_by_status,    # NotesDoc -> {"todo": N, "done": N, "wontfix": N}
)

# 反映済みにマーク (commit hash を ref に残す)
set_resolution(section.snapshot, "done", ref="16a1943")

# 反映対象外にマーク (理由を ref に残す)
set_resolution(section.snapshot, "wontfix", ref="個人感想のため対象外")

# todo に戻す (resolution フィールドを削除)
set_resolution(section.snapshot, "todo")

# 1 ファイル分の棚卸し
from notes import load_notes, count_sections_by_status
doc = load_notes("projects/<dir>/output.srt.notes.md")
print(count_sections_by_status(doc))
# {"todo": 2, "done": 5, "wontfix": 3}
```

`get_resolution()` は常に新しい dict を返すので、戻り値を変更しても元の snapshot は影響を受けない。

## parse / serialize との関係

`encode_snapshot` / `decode_snapshot` / `parse_notes_md` / `serialize_notes_md` は snapshot dict をそのまま JSON で round-trip するので、`resolution` フィールドを追加してもパーサ側のコード変更は不要。手で md を編集して `resolution` を書き込んでも問題なく読み込まれる。

## 運用例

1. notes を作る (まだ何もしていない) → snapshot に `resolution` 無し = `todo` 扱い
2. YOMI_DICT に反映するコミットを切る → `set_resolution(snap, "done", ref="<short-hash>")`
3. 個人感想のセクションを棚卸し → `set_resolution(snap, "wontfix", ref="個人感想")`
4. 進捗を見たいとき → `count_sections_by_status(doc)`

## まだやっていないこと (今後の拡張余地)

- UI 側: セクションヘッダにステータスバッジを出す / クリックで status 切替 (PATCH /api/notes/resolution など)
- `/api/notes/index` の拡張: ファイル別の status 集計を返す
- CLI: `python scripts/notes_status.py projects/*/output.srt.notes.md` で全ファイルの集計を一覧

データ層 (`notes.py` ヘルパー + フォーマット規約) はこの spec で完結する。UI / API / CLI 拡張はそれぞれ別タスクで追加可能。
