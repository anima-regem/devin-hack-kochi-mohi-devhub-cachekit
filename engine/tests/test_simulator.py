import pytest
from cachekit.render.tokenize import TokenizedRequest
from cachekit.settings import RunConfig
from cachekit.simulate.vllm import simulate


def request(
    id: str, tokens: list[int], *, namespace: str = "test", skip: bool = False
) -> TokenizedRequest:
    return TokenizedRequest(
        id=id,
        ts=float(id),
        text="",
        token_ids=tokens,
        offsets=[],
        namespace=namespace,
        skip_cache_read=skip,
    )


def params(config: RunConfig, *, capacity: int = 8):
    return config.vllm.model_copy(
        update={"block_size": 4, "capacity_blocks": capacity, "reserved_blocks": 0}
    )


def test_cold_then_full_blocks_only(config: RunConfig) -> None:
    tokens = list(range(9))
    result = simulate([request("1", tokens), request("2", tokens)], params(config))
    assert [r.cached_tokens for r in result.requests] == [0, 8]
    assert result.total_prompt_tokens == 18
    assert result.hit_rate == 8 / 18


def test_exact_block_boundary_recomputes_last_block_for_logits(config: RunConfig) -> None:
    result = simulate([request("1", list(range(8))), request("2", list(range(8)))], params(config))
    assert [r.cached_tokens for r in result.requests] == [0, 4]


def test_partial_match_cannot_hit_a_block(config: RunConfig) -> None:
    result = simulate(
        [request("1", [1, 2, 3, 4, 5]), request("2", [1, 2, 3, 9, 5])], params(config)
    )
    assert result.cached_tokens == 0


def test_salt_and_model_namespaces_do_not_share(config: RunConfig) -> None:
    result = simulate(
        [
            request("1", list(range(9)), namespace="tenant-a"),
            request("2", list(range(9)), namespace="tenant-b"),
        ],
        params(config),
    )
    assert result.cached_tokens == 0


def test_reverse_release_keeps_prefix_when_suffix_is_evicted(config: RunConfig) -> None:
    result = simulate(
        [
            request("1", list(range(9))),
            request("2", [90, 91, 92, 93, 94]),
            request("3", list(range(9))),
        ],
        params(config, capacity=3),
    )
    assert [r.cached_tokens for r in result.requests] == [0, 0, 4]


def test_partial_block_occupies_real_capacity(config: RunConfig) -> None:
    with pytest.raises(ValueError, match="cannot fit"):
        simulate([request("1", list(range(13)))], params(config, capacity=3))


def test_reserved_block_and_context_limit_are_enforced(config: RunConfig) -> None:
    limited = params(config, capacity=3).model_copy(update={"reserved_blocks": 1})
    with pytest.raises(ValueError, match="cannot fit"):
        simulate([request("1", list(range(9)))], limited)
    with pytest.raises(ValueError, match="max_model_len"):
        simulate(
            [request("1", list(range(9)))], params(config).model_copy(update={"max_model_len": 8})
        )


def test_logprob_request_skips_reads_and_order_uses_timestamp_then_id(config: RunConfig) -> None:
    tokens = list(range(9))
    result = simulate(
        [request("3", tokens), request("1", tokens), request("2", tokens, skip=True)],
        params(config),
    )
    assert [r.id for r in result.requests] == ["1", "2", "3"]
    assert [r.cached_tokens for r in result.requests] == [0, 0, 8]


def test_empty_and_short_requests(config: RunConfig) -> None:
    assert simulate([], params(config)).hit_rate == 0
    assert (
        simulate([request("1", [1, 2, 3]), request("2", [1, 2, 3])], params(config)).cached_tokens
        == 0
    )
