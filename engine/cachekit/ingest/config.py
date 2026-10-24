"""Local configuration I/O, kept outside pure analysis and simulation."""

from importlib.resources import files
from pathlib import Path

import yaml

from cachekit.settings import AnalysisConfig, RunConfig, VllmConfig


def load_config(directory: Path | None = None) -> RunConfig:
    root = directory if directory is not None else files("cachekit").joinpath("config")
    backends = yaml.safe_load(root.joinpath("backends.yaml").read_text(encoding="utf-8"))
    rules = yaml.safe_load(root.joinpath("analysis.yaml").read_text(encoding="utf-8"))
    rules.pop("source", None)
    rules.pop("verified_on", None)
    profile = {key: entry["value"] for key, entry in backends["vllm"].items()}
    return RunConfig(
        vllm=VllmConfig.model_validate(profile), analysis=AnalysisConfig.model_validate(rules)
    )
