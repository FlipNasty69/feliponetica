# English Word Order Game

The game is available at `/games/word-order/levels`. It is registered as a Flask blueprint and uses the existing SQLite/openpyxl stack.

## Workbook source

`static/data/muster_structure.xlsx` is the editable source. The importer reads the named tables `tblLevels`, `tblWords`, `tblVerbForms`, `tblPatterns`, `tblPatternSlots`, and `tblChallenges`; it does not depend on fixed worksheet coordinates or a fixed level count. Authored challenges drive gameplay. The vocabulary, verb paradigms, patterns, and ordered pattern slots are stored for future challenge-generation work; the game does not generate unreviewed sentences.

After saving workbook edits, the blueprint checks the source file's modification time and synchronizes changed data on the next game request. To synchronize explicitly:

```powershell
flask --app app word-order sync-data
flask --app app word-order sync-data path\to\workbook.xlsx
flask --app app word-order sync-data --deactivate-missing
```

Missing rows are retained by default. `--deactivate-missing` deactivates omitted words and challenges without deleting them. Invalid tables, duplicate IDs, missing required values, or broken challenge/pattern/level references reject the full import. `Challenge_Count` is ignored and computed from active challenge rows.

The imported content and game progress live in `instance/word_order.sqlite3`; the application creates its schema automatically. The project does not use SQLAlchemy or a migration framework, so the implementation uses normalized SQLite tables and idempotent schema creation consistent with its existing `sqlite3` code.

## Gameplay

The browser receives active shuffled tokens, never the complete answer list. The server normalizes and checks answers, accepts alternatives separated with `||`, and records a single attempt per challenge per session. Level 1 is initially available; a level with at least 80% correct unlocks the next level. Guests keep progress in their signed browser session; logged-in users use their account ID.

## Along vocabulary sequence

The optional named Excel table `along` on the `Challenges` worksheet contains the Along word-order sequence. Its columns are `exercise`, `slot 1` through `slot 9`, and `spanish prompt`. The importer stores each non-empty slot in its authored order in `along_exercises`; if the optional table is absent, the standard workbook import still works. Rows removed from a present table are deactivated, while existing sessions can still finish using their captured exercise IDs.

The Along picture-match set at `/vocab/picture-match/along` links directly to `/games/word-order/along`. It uses the same word-tile interaction and server-side answer checking as regular levels, but Along sessions and scores are kept separate from the level catalog and level progress. Finishing the final exercise displays the celebration on the game page.