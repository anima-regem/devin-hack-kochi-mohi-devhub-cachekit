# Change log

## 2026-10-24T22:39:55+05:30 — Resolve PR #1 against the implemented project

- Changed: integrated corrected Devin Hack Kochi guidance and optional AI-tool
  wording across the seven documentation files in PR #1. Preserved the cachekit
  README, setup/demo commands, submission details, changelog and AI usage history.
- Why: PR #1 started from the old template and conflicts with newer project docs.
  No particular template or AI provider is an event requirement.
- Validation: reviewed exact downloaded PR head d361d19d50d6589966e349804d0654730e3b7940; checked local Markdown
  links, whitespace and preservation of all application files. Current main had
  passed 108 Python tests before this documentation-only resolution; those tests
  are not a new runtime claim for the PR.
- Limitations: remote publication must succeed before the PR is conflict-free
  on GitHub. No application behavior or quality-approval state is changed.

## 2026-10-24T21:53:05+05:30 — Correct Devin Hack Kochi event guidance

- Changed: corrected the current event name and AI tool guidance in `.github/pull_request_template.md`, `AGENTS.md`, `AI_USAGE.md`, `CHANGELOG.md`, `README.md`, `RULES.md`, `SUBMISSION.md`.
- Why: the organizer shared an older event template; Devin Hack Kochi has no
  major AI usage constraints and the template must not require a particular AI provider.
- Scope: preserved project implementation and historical assistance records.
- Removed obsolete template logistics, participation limits, and credit promises; current organizer instructions remain authoritative.
- Validation: reviewed documentation diffs, checked whitespace with `git diff --check`, and checked local Markdown links for new breakage.
- Limitations: maintainer review is pending; application tests were not run for this documentation-only correction.

Record each meaningful project change during the event, newest first. Update this file in the same commit as the change. Use a real timestamp with timezone, for example `YYYY-MM-DDTHH:MM:SS+05:30`.

## Event build log

### 2026-10-24T22:32:02+05:30 — feat: connect local analysis and verification to the report workspace

- Changed: Added bounded local API ingestion, saved report identities/provenance,
  redacted task creation, source freshness, offline verification and exact-diff
  approval. Connected Analyze, Report, Heatmap, Fix and Bench UI routes; exported
  only reviewed synthetic evidence for API-free demo mode. Updated README,
  submission notes, web instructions and screenshot status.
- Why: Make the existing deterministic engine and fail-closed quality workflow
  reviewable through one local workspace, with explicit SIMULATED/MEASURED labels.
- Affected: `engine/cachekit/api*`, workspace persistence, CLI approval helper,
  report heatmap metadata, `web/src/`, public synthetic snapshot and exporter.
  Private uploads/results remain ignored; optional private planning is no longer
  required to generate a fix task from a public checkout.
- Validation: 108 Python tests passed, including 10 API/evidence cases; Ruff passed;
  web typecheck, ESLint and production build passed. Regenerated the actual local
  synthetic report and checked exported values against saved evidence. UI source
  detector warning corrected; diff whitespace and exporter syntax checked.
- Limitations: Browser screenshots/visual validation are unverified because both
  API and Next server binds are denied (EPERM) in this sandbox. No actual fixer
  PR, golden inference, BEFORE/AFTER benchmark, cost or speedup is claimed. The
  historical fix task is stale and unapproved. Publication is recorded separately
  after a successful commit/push; no shared history is rewritten. Staging here
  failed because .git/index.lock creation is denied. A reviewed local incremental
  publisher is prepared for normal Terminal execution.


### 2026-10-24T22:11:13+05:30 — chore: add run scripts and reviewed submission evidence

- Changed: Publish this logical source checkpoint on top of the organizer template.
- Why: Record previously local work with honest current commit timestamps.
- Validation: Public-file allowlist, credential patterns and preserved organizer bytes
  checked before staging; code checks for the complete local workspace are recorded above.
- Limitations: This is a publication checkpoint, not a backdated development record;
  actual fixer/quality/benchmark completion and final screenshots remain pending.


### 2026-10-24T22:11:13+05:30 — feat: scaffold the cachekit web interface

- Changed: Publish this logical source checkpoint on top of the organizer template.
- Why: Record previously local work with honest current commit timestamps.
- Validation: Public-file allowlist, credential patterns and preserved organizer bytes
  checked before staging; code checks for the complete local workspace are recorded above.
- Limitations: This is a publication checkpoint, not a backdated development record;
  actual fixer/quality/benchmark completion and final screenshots remain pending.


### 2026-10-24T22:11:12+05:30 — feat: add fixer handoff and source-bound behavioral verification

- Changed: Publish this logical source checkpoint on top of the organizer template.
- Why: Record previously local work with honest current commit timestamps.
- Validation: Public-file allowlist, credential patterns and preserved organizer bytes
  checked before staging; code checks for the complete local workspace are recorded above.
- Limitations: This is a publication checkpoint, not a backdated development record;
  actual fixer/quality/benchmark completion and final screenshots remain pending.


### 2026-10-24T22:11:12+05:30 — feat: define redacted fix tasks and fail-closed verification gates

- Changed: Publish this logical source checkpoint on top of the organizer template.
- Why: Record previously local work with honest current commit timestamps.
- Validation: Public-file allowlist, credential patterns and preserved organizer bytes
  checked before staging; code checks for the complete local workspace are recorded above.
- Limitations: This is a publication checkpoint, not a backdated development record;
  actual fixer/quality/benchmark completion and final screenshots remain pending.


### 2026-10-24T22:11:12+05:30 — feat: implement offline cache analysis and vLLM simulation

- Changed: Publish this logical source checkpoint on top of the organizer template.
- Why: Record previously local work with honest current commit timestamps.
- Validation: Public-file allowlist, credential patterns and preserved organizer bytes
  checked before staging; code checks for the complete local workspace are recorded above.
- Limitations: This is a publication checkpoint, not a backdated development record;
  actual fixer/quality/benchmark completion and final screenshots remain pending.


### 2026-10-24T22:11:11+05:30 — feat: scaffold Python contracts and reproducible helpdesk fixtures

- Changed: Publish this logical source checkpoint on top of the organizer template.
- Why: Record previously local work with honest current commit timestamps.
- Validation: Public-file allowlist, credential patterns and preserved organizer bytes
  checked before staging; code checks for the complete local workspace are recorded above.
- Limitations: This is a publication checkpoint, not a backdated development record;
  actual fixer/quality/benchmark completion and final screenshots remain pending.


Entries below are retrospective records written at the displayed time. Earlier
implementation was not committed from the coding sandbox because Git metadata
writes were denied. Commit timestamps will reflect actual publication time;
the event timeline is not backdated or reconstructed.

### 2026-10-24T21:54:46+05:30 — Prepare template-preserving publication

- Changed: Restored organizer files from the repository's existing initial commit;
  retained private CacheKit notes under ignored local storage; added run scripts,
  submission details and an honest screenshot status.
- Why: Build on the participant template's history and provide reproducible entry
  points while keeping credentials, raw data and private planning out of Git.
- Validation: Organizer file paths and original contents inspected from
  `origin/main`; shell syntax checked for all run scripts. The implemented engine
  and fix workflow passed the full local Python suite (98 tests) and Ruff.
  Isolated publication-prefix checks passed: foundation tests; analysis tests
  with exact-tokenizer integration skipped because private tokenizer data is not
  included in a public checkpoint. Public allowlist and credential checks passed;
  organizer instructions/rules/checklist match the existing template bytes.
- Limitations: Publication is pending. The API and UI are foundations, no actual
  fixer PR or golden inference exists, and UI screenshots remain pending.

## Template setup — 10 October 2026

- Changed: Added the event README, rules, agent guide, change log, AI usage record, submission checklist, Git ignore rules, and pull request checklist.
- Why: Give participants a consistent starting point for event rules, basic coding patterns, documented changes, and regular commits.
- Validation: Checked local Markdown links, event detail consistency, required documents, and diff whitespace before publishing.
- Limitations: Documentation scaffolding only; no participant project, application, or working demo is included. GitHub publication and template status are verified separately after creation.
