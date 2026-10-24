"""Explicit local tokenizer loading. No fallback download or approximate model."""

import hashlib
from importlib.metadata import version
from pathlib import Path

from cachekit.render.tokenize import HFPromptTokenizer


def load_tokenizer(path: Path, *, model: str, revision: str) -> HFPromptTokenizer:
    if not path.is_dir():
        raise ValueError("Tokenizer directory is missing; prefetch the pinned tokenizer explicitly")
    required = ("tokenizer.json", "tokenizer_config.json", "config.json")
    if any(not (path / name).is_file() for name in required):
        raise ValueError(
            "Local tokenizer requires tokenizer.json, tokenizer_config.json, config.json"
        )
    digests = {name: hashlib.sha256((path / name).read_bytes()).hexdigest() for name in required}
    for name in required:
        metadata = path / ".cache" / "huggingface" / "download" / f"{name}.metadata"
        if not metadata.is_file():
            raise ValueError(
                "Pinned tokenizer provenance is missing; use hf download --revision --local-dir"
            )
        lines = metadata.read_text(encoding="utf-8").splitlines()
        if len(lines) < 2 or lines[0] != revision:
            raise ValueError(
                "Tokenizer download revision does not match the configured model revision"
            )
        content = (path / name).read_bytes()
        expected = lines[1]
        actual = (
            hashlib.sha256(content).hexdigest()
            if len(expected) == 64
            else hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
        )
        if actual != expected:
            raise ValueError("Local tokenizer checksum differs from its download metadata")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(path.resolve()), local_files_only=True, trust_remote_code=False, use_fast=True
    )
    if not tokenizer.is_fast or not tokenizer.chat_template:
        raise ValueError("An exact fast tokenizer with a local chat template is required")
    return HFPromptTokenizer(
        tokenizer,
        {
            "model": model,
            "revision": revision,
            "files_sha256": digests,
            "transformers_version": version("transformers"),
            "tokenizers_version": version("tokenizers"),
            "mode": "exact_local_chat_template",
        },
    )
