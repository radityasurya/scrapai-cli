# Project Rules

These rules are project-specific working agreements for `scrapai-cli`.

## Planning

- Do not create planning documents in repo docs for implementation planning.
- Use the Obsidian Kanban workspace for plans and task tracking.
- Project board: `kanban/scrapai-cli/board.md`
- Plan notes: `kanban/scrapai-cli/notes/`
- Track roadmap-level changes in the Obsidian Kanban project as well, with `ROADMAP.md` mirrored in `kanban/scrapai-cli/ROADMAP.md`.

## Current preference

- For new implementation planning, create or update an Obsidian Kanban card and note first.
- Repo docs should only be updated when the feature is implemented, user-facing, or architectural reality has changed.

## Roadmap tracking

- Keep `ROADMAP.md` represented in the Obsidian Kanban project.
- Use `kanban/scrapai-cli/ROADMAP.md` for roadmap sync and change logging.
- When roadmap items are added, removed, re-scoped, or shipped, update `kanban/scrapai-cli/ROADMAP.md`.
- Do not represent roadmap tracking itself as a Kanban task/card unless there is a real implementation task attached to it.
- Obsidian should capture what changed and why, even if `ROADMAP.md` remains the canonical repo file.

## Completion logging

- When finishing a task, update the related Obsidian Kanban note with a completion summary.
- That summary should include, when relevant: changed files, behavior added/changed, validation performed, and follow-up items.
- If the Kanban card links to a note, treat that note as the place for the task comment/log.

## Reminder

- If planning work starts for this project, mirror it in Obsidian instead of adding draft planning docs under `docs/`.
