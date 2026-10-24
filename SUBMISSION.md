# Project submission

Complete this file during the hackathon and use it to prepare your submission through the method announced by the organizers. Do not submit your project to the template repository.

## Project

- **Project name:** cachekit
- **Short description:** A deterministic prompt-cache analyzer that diagnoses lost reuse, generates redacted source-refactoring tasks, and verifies candidate fixes with content checks and a required behavioral guard. Intended for developers running LLM applications.
- **Code repository URL:** https://github.com/mohi-devhub/cachekit
- **Final submitted implementation commit SHA:** Pending final implementation and publication. The template commit is not the submitted implementation.
- **Working demo URL or local demo steps:** Local CLI: after setup, `bash scripts/demo.sh`. API/UI foundations: `bash scripts/run-api.sh` and `bash scripts/run-web.sh` in separate terminals. No hosted demo is claimed.
- **Demo access requirements:** Python, uv, Node.js and the pinned public tokenizer. Installation uses network access; ordinary synthetic analysis needs no credentials, GPU or external LLM.

## Participants

Participate solo or in a team of up to 4. Remove unused rows.

| Participant name | GitHub handle | Contribution |
| --- | --- | --- |
| Mohith | [mohi-devhub](https://github.com/mohi-devhub) | Solo builder; project direction and review. Implementation assistance documented in AI_USAGE.md. |

## Run and demonstrate

- **Prerequisites and versions:** Python requirement in `pyproject.toml` and `.python-version`; Node requirement in `web/package.json`; uv and npm.
- **Install command:** `bash scripts/setup.sh`.
- **Required environment variable names:** None for synthetic offline analysis. Optional fixer/deployment variables are listed as names only in `.env.example`; keep real values local.
- **Start command:** `bash scripts/demo.sh` for the implemented CLI workflow; API and web start scripts above expose scaffolds.
- **Demo walkthrough:** Generate fictional BEFORE traffic, render with the pinned local Qwen tokenizer, inspect the saved SIMULATED cache report, prepare a redacted fix task, and run verification. Missing actual behavioral evidence leaves the candidate unapproved.
- **Checks performed and results:** Full local Python suite, Ruff, real-tokenizer offline/reproducibility tests and CLI wheel build passed during implementation. Run scripts have been syntax checked; network installation and live API/UI launching are not verified in this sandbox. Re-run `bash scripts/check.sh` in the configured participant environment.
- **Screenshots:** [Pending actual UI captures](screenshots/README.md). No mock screenshot is presented as an implemented interface.
- **Known limitations or incomplete features:** Actual agent fix/PR, golden model inference, BEFORE/AFTER measurements, report API/UI integration and final submission are pending. Saved cache rates are simulated. The existing GPU smoke test establishes serving/cache reuse only.
- **Libraries and APIs:** Python/uv, Pydantic, Typer, FastAPI, pytest/Ruff, Transformers/tokenizers, httpx/jsonschema, Next.js/React/Tailwind; [vLLM](https://github.com/vllm-project/vllm) and [Modal](https://modal.com/) for the selected serving profile; [Devin API](https://docs.devin.ai/api-reference/overview) adapter tested with mocked responses, no real session started.
- **Public datasets:** [SWE-agent trajectories](https://huggingface.co/datasets/nebius/SWE-agent-trajectories) (CC BY 4.0; respect upstream/model terms), [Glaive function calling](https://huggingface.co/datasets/glaiveai/glaive-function-calling-v2) (Apache-2.0), and [WildChat](https://huggingface.co/datasets/allenai/WildChat-1M) (ODC-BY). Only SWE-agent/Glaive conversion is implemented so far; downloads/raw data and dataset-derived previews remain local. Public demo evidence uses fictional synthetic inputs.
- **AI usage record:** [AI_USAGE.md](AI_USAGE.md)
- **Development change log:** [CHANGELOG.md](CHANGELOG.md)

## Submission checklist

- [ ] The project implementation started from scratch at the event.
- [ ] I participated solo or with no more than 4 team members in total.
- [x] Codex was used during development and its usage is documented.
- [ ] The code repository URL, short description, and working demo are provided.
- [ ] README setup and demo instructions match the submitted code.
- [x] Actual checks and known limitations are documented.
- [ ] Meaningful changes are documented and committed throughout development.
- [ ] The final implementation is committed and pushed, and its SHA is recorded above.
- [ ] No credentials or private data are included in the repository or demo instructions.
- [ ] The organizers' announced submission method and timing have been followed.

Upstream event reference: [DevDay Exchange Community: Kochi on Luma](https://luma.com/z10nz8gp). The preserved template describes its original October event; Mohith supplied this template for the Devin Hacks Kochi project described in the README. Eligibility, the active event schedule and final submission must follow the current organizers' instructions; pending checklist items are not asserted as complete.
