import json
from pathlib import Path

import pytest
from cachekit.ingest.config import load_config
from cachekit.ingest.tokenizer import load_tokenizer
from cachekit.models import RequestRecord
from cachekit.settings import RunConfig


class CharacterTokenizer:
    """Known-answer synthetic vocabulary; never offered as a CLI model fallback."""

    identity = {"mode": "synthetic_character_fixture", "name": "unit-test-only"}

    def render(self, record: RequestRecord) -> str:
        parts = []
        if record.tools:
            parts.append("Tools\n" + "\n".join(json.dumps(t, sort_keys=True) for t in record.tools))
        if record.system:
            parts.append("System\n" + record.system)
        parts.extend(m.role + "\n" + m.content for m in record.messages)
        return "\n".join(parts) + "\nassistant\n"

    def encode_offsets(self, text: str) -> tuple[list[int], list[tuple[int, int]]]:
        return [ord(c) for c in text], [(i, i + 1) for i in range(len(text))]


@pytest.fixture
def config() -> RunConfig:
    config = load_config()
    config.vllm.capacity_blocks = 4096
    return config


@pytest.fixture
def char_tokenizer() -> CharacterTokenizer:
    return CharacterTokenizer()


@pytest.fixture(scope="session")
def qwen_tokenizer():
    path = Path(__file__).resolve().parents[2] / "data" / "tokenizer"
    if not path.is_dir():
        pytest.skip("Prefetch the pinned Qwen tokenizer to run the integration test")
    config = load_config()
    return load_tokenizer(path, model=config.vllm.model, revision=config.vllm.revision)
