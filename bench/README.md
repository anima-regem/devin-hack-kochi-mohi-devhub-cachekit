# Benchmark harness

The GPU preparation result is saved in `../eval_results/modal_smoke.json`.
It confirms serving and prefix reuse; it contains no latency or speedup claim.

`quality.py` is the explicit core E5-lite inference collector. Run
`PYTHONPATH=engine python3 -m bench.quality --help` from the repository, or use the
installed workspace. It submits only fixed public synthetic golden cases to
local vLLM or Modal, using exact prompt token IDs and the task's recorded
generation settings. A real deployment manifest is required. No live quality run
has been performed during implementation; mocked test outputs are not results.

The replay client, metrics scraper, and Modal serving module remain for the
measurement phase. Ordinary `cachekit analyze` and `cachekit verify` never invoke
this runner or perform inference. Missing/stale/failed quality evidence prevents
fix approval. Use `python -m bench.quality --help` and `cachekit verify --help`
for the collection and verification options.
