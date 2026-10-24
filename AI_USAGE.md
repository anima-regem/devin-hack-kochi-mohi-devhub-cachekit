# AI usage record

If maintaining this record, briefly document the actual contributions of whichever AI tools you use at Devin Hack Kochi. Add a row after each meaningful task or milestone. Keep summaries concise and omit secrets, private data, and full chat transcripts.

## Event build log

These are retrospective records of actual assistance, written at the displayed
time. Human code review remains pending; permission to build is not a completed
review. Exact model identifiers were not recorded.

| Date and time with timezone | Tool / model | Task | Assistance and affected files | Human review / corrections | Validation and result |
| --- | --- | --- | --- | --- | --- |
| 2026-10-24T22:39:55+05:30 | Codex | Resolve PR #1 documentation conflicts | Retained cachekit implementation instructions, submission details and assistance/build history; applied corrected event and optional AI-tool guidance | User authorized conflict resolution; human content review pending | Documentation links, whitespace and source-preservation checks passed locally; remote update pending |
| 2026-10-24T22:32:02+05:30 | Codex | Phase 4 local API and report workspace | Implemented API persistence/guards, analysis/report/heatmap/fix/bench pages, synthetic-only export, provenance and HTTP regression tests; updated public run/demo documentation | Human review pending; removed private DECISIONS requirement from public task setup; corrected heatmap token coordinates and detector warning | 108 Python tests, Ruff, web typecheck/ESLint/build passed; local server binds denied, browser captures unverified; no live Devin or inference; Git staging denied, publication pending |
| 2026-10-24T22:11:13+05:30 | Codex | chore: add run scripts and reviewed submission evidence | Retrospective source publication and documentation; no new model inference | Human code review pending | Allowlist/credential/template checks; complete-workspace validation recorded in the build log |
| 2026-10-24T22:11:13+05:30 | Codex | feat: scaffold the cachekit web interface | Retrospective source publication and documentation; no new model inference | Human code review pending | Allowlist/credential/template checks; complete-workspace validation recorded in the build log |
| 2026-10-24T22:11:12+05:30 | Codex | feat: add fixer handoff and source-bound behavioral verification | Retrospective source publication and documentation; no new model inference | Human code review pending | Allowlist/credential/template checks; complete-workspace validation recorded in the build log |
| 2026-10-24T22:11:12+05:30 | Codex | feat: define redacted fix tasks and fail-closed verification gates | Retrospective source publication and documentation; no new model inference | Human code review pending | Allowlist/credential/template checks; complete-workspace validation recorded in the build log |
| 2026-10-24T22:11:12+05:30 | Codex | feat: implement offline cache analysis and vLLM simulation | Retrospective source publication and documentation; no new model inference | Human code review pending | Allowlist/credential/template checks; complete-workspace validation recorded in the build log |
| 2026-10-24T22:11:11+05:30 | Codex | feat: scaffold Python contracts and reproducible helpdesk fixtures | Retrospective source publication and documentation; no new model inference | Human code review pending | Allowlist/credential/template checks; complete-workspace validation recorded in the build log |
| 2026-10-24T21:54:46+05:30 | Codex | Project implementation | Python contracts, synthetic helpdesk traffic, offline analysis/simulation, CLI, fix/quality/approval workflow, tests and web scaffold | Mohith directed scope and privacy; code review pending | Full local Python suite and Ruff passed; CLI wheel built. Actual fix, quality inference and full UI remain pending. |
| 2026-10-24T21:54:46+05:30 | Codex | Template and publication preparation | Preserved organizer records/history, separated private planning, prepared run scripts and explicit publication allowlist | Mohith confirmed preserving organizer files; review pending | Run-script shell syntax checked; publication and screenshots pending. No real Devin session started. |

Earlier Modal/dataset preparation was reported by Mohith as performed through
Claude Code. This session uses the saved smoke evidence and does not claim to
have repeated that GPU run. No raw request logs or private prompts are included
in this assistance record.

## Template preparation

This historical note describes the older template, not current event rules or AI tool requirements.

On 10 October 2026, Codex prepared this documentation template from the organizer's supplied rules and checked the linked Luma page for the event name and dates. This covered `README.md`, `RULES.md`, `AGENTS.md`, `CHANGELOG.md`, `AI_USAGE.md`, `SUBMISSION.md`, `.gitignore`, and the pull request checklist. Agent validation covered local links, event consistency, required documents, and diff whitespace; organizer review is pending.

This preparation is separate from participant project implementation and participant AI usage during the event.

## Event documentation correction — 2026-10-24T21:53:05+05:30

- Tool: Codex.
- Task: correct the organizer-shared template to Devin Hack Kochi and clarify
  that the event has no major AI usage constraints.
- Affected files: `.github/pull_request_template.md`, `AGENTS.md`, `AI_USAGE.md`, `CHANGELOG.md`, `README.md`, `RULES.md`, `SUBMISSION.md`.
- Human review: pending maintainer review of this pull request.
- Validation: documentation diff, whitespace, and local Markdown link checks;
  no application code changed and no runtime checks were needed.
