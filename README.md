# cachekit

Deterministic prompt-cache analysis and a verified source-refactoring workflow.

This is a dependency checkpoint in a current publication batch of work completed
locally. These commits use their real creation times; they do not reconstruct an
earlier event timeline. The final checkpoint contains the complete usage guide.
Organizer files are preserved; private project planning and credentials stay local.

## Available at this checkpoint

- Python contracts, schema/version CLI, health API and fictional BEFORE fixtures.

```sh
uv sync --all-packages --all-extras
uv run --no-sync cachekit --version
uv run --no-sync cachekit schema --model RequestRecord
uv run --no-sync python -m demo_app.traffic --out data/demo
uv run --no-sync pytest
```

- Offline ingestion, full-template tokenization, breaker detection, vLLM
  simulation and report JSON. Prefetch the pinned tokenizer during setup;
  analysis itself never downloads files or calls inference.

```sh
hf download Qwen/Qwen3-4B-Instruct-2507 tokenizer.json tokenizer_config.json config.json \
  --revision cdbee75f17c01a7cc42f958dc650907174af0554 --local-dir data/tokenizer
uv run --no-sync cachekit analyze data/demo/requests_before.jsonl \
  --tokenizer data/tokenizer --out eval_results/report.json
```

- Typed fix tasks and pure content/quality/approval gates.

- Local fixer handoff, scoped subprocess replay, repository tests, saved-output
  quality evaluation and explicit approval CLI. Missing actual quality evidence
  blocks approval. The explicit synthetic inference collector is in bench/quality.py.

- Next.js web scaffold. Run `npm --prefix web install` and
  `npm --prefix web run dev`; report integration remains pending.

## Limitations

Cache rates are SIMULATED. No real fixer PR, passing live golden evidence or
measured BEFORE/AFTER speedup is claimed. API/UI integration and actual screenshots
remain work in progress. Private inputs stay in gitignored data/.

See AI_USAGE.md, CHANGELOG.md and SUBMISSION.md for the current assistance,
publication record and incomplete submission items.
