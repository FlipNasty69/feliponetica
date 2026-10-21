# Question Builder

Question Builder is available at `/question-game/game` and is registered as a Flask game blueprint.

## Workbook-driven exercises

`static/data/question_game.xlsx` supplies the exercise content. Every worksheet whose name begins with `level 1` (case-insensitive) is automatically listed as an exercise after a learner chooses Level 1. Adding a new worksheet with that prefix makes it available without code changes.

Each exercise worksheet uses its first column for the Spanish prompt. Non-empty cells in the remaining columns are the ordered answer words for that row; blank cells are skipped. Column headers are used as slot labels, with generic word labels when headers are blank or numeric. Header rows, rows without a prompt, and note columns are not treated as exercises or answer slots. Each row can have a different number of answer words, and the interface creates the matching number of slots. Add answer columns to extend future exercises with more complex questions.

Prompts and answers are read directly from worksheet rows. The workbook is the source of truth; English/Spanish verb forms are not generated from hard-coded mappings.

## Round behavior

Questions with the same final answer word share a batch and a shuffled word bank. Each unique answer word appears only once in that bank, and choices return after every prompt. The browser receives prompts and slot labels, not answer sequences. Answers are checked on the server when all slots are filled. Correct answers score 10 points.
