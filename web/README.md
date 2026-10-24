# Local report workspace

From the repository root, run `bash scripts/run-web.sh`; open
`http://localhost:3000`. Install first with `bash scripts/setup.sh`.
`npm --prefix web run typecheck`, `lint` and `build` validate the web source.

The UI uses the existing green/light/dark theme and native SVG/HTML for the
stability strip and comparison bars. No chart dependency, remote font, analytics
or external inference is needed.

| Route | Behavior |
| --- | --- |
| `/` | Select a local sample or upload native JSONL through the local API; open the saved synthetic run |
| `/report/demo-before` | Saved synthetic findings, simulated reuse, recomputation and provenance |
| `/report/[id]` | A report saved by the API; unknown reports never substitute the synthetic run |
| `/report/[id]/heatmap/[route]` | Downsampled stability with reference-token coordinates and redacted template |
| `/fix` or `/fix/[id]` | Redacted task, source freshness, local verification, golden outcomes and exact-diff approval |
| `/bench` | Measured serving smoke counters; BEFORE/AFTER performance evidence remains pending |
| `/how-it-works` | Method, privacy and limits |

Start `bash scripts/run-api.sh` in another terminal for interactive analysis and
verification. It listens on `127.0.0.1:8000`. Generate `data/demo/` with the README
traffic command first. Private uploads and their reports stay ignored locally;
fix replay currently supports only recorded helpdesk inputs.

`NEXT_PUBLIC_API_BASE_URL` can override the API origin at build/development time.
Only HTTP(S) loopback or HTTPS Modal hosts are accepted; never point private logs
at an arbitrary third-party service. CORS permits the normal local web origins.
The API is an unauthenticated local operator service; the UI has no launch-Devin
or GPU button. Review/approval is a local record and does not merge a PR.

Without the API, the committed `public/demo/workspace.json` supplies only the
reviewed synthetic report, historical task status and measured smoke counters.
Task generation, verification and approval stay disabled. Refresh the snapshot
from the named synthetic report using `python scripts/export_demo.py` in the
project environment. Uploaded/dataset-derived runs are never exported.

The fix evidence section accepts SHA-256 identities of typed artifacts stored in
`eval_results/quality_guard/`. Collect actual goldens separately with
`python -m bench.quality --help`; changed outputs require explicit review via
`cachekit review-quality`. Missing evidence blocks approval. No pass, cost or
speedup is fabricated for the demo.
