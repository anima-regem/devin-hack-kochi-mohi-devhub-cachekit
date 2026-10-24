"""Prompt-only sequential full-attention block cache, modeled after vLLM v1.

All active blocks are pinned before allocation. Free blocks, including cached
ones, form a FIFO eviction queue; completion appends blocks in reverse order.
Hash identities model sharing, not the byte representation of vLLM's hash keys.
"""

import hashlib
from collections import OrderedDict

from cachekit.models import BoundaryModel
from cachekit.render.tokenize import TokenizedRequest
from cachekit.serialization import canonical_json
from cachekit.settings import VllmConfig


class RequestCacheResult(BoundaryModel):
    id: str
    prompt_tokens: int
    cached_tokens: int


class SimulationResult(BoundaryModel):
    total_prompt_tokens: int
    cached_tokens: int
    requests: list[RequestCacheResult]

    @property
    def hit_rate(self) -> float:
        return self.cached_tokens / self.total_prompt_tokens if self.total_prompt_tokens else 0


def block_hashes(request: TokenizedRequest, size: int) -> list[str]:
    parent = hashlib.sha256(request.namespace.encode()).hexdigest()
    result: list[str] = []
    for start in range(0, len(request.token_ids) - size + 1, size):
        parent = hashlib.sha256(
            canonical_json([parent, request.token_ids[start : start + size]]).encode()
        ).hexdigest()
        result.append(parent)
    return result


def simulate(requests: list[TokenizedRequest], config: VllmConfig) -> SimulationResult:
    capacity = config.capacity_blocks - config.reserved_blocks
    if capacity < 1:
        raise ValueError("No usable cache blocks remain after reserved blocks")
    free: OrderedDict[int, None] = OrderedDict.fromkeys(range(capacity))
    physical: dict[int, str] = {}
    index: dict[str, dict[int, None]] = {}
    results: list[RequestCacheResult] = []
    for request in sorted(requests, key=lambda item: (item.ts, item.id)):
        n = len(request.token_ids)
        if n > config.max_model_len:
            raise ValueError(
                "A rendered prompt exceeds max_model_len; requests are never truncated"
            )
        needed = (n + config.block_size - 1) // config.block_size
        if needed > capacity:
            raise ValueError("A prompt cannot fit in the configured sequential KV cache")
        hashes = block_hashes(request, config.block_size)
        reuse_limit = max(0, n - int(config.recompute_last_token)) // config.block_size
        used: list[int] = []
        if not request.skip_cache_read:
            for key in hashes[:reuse_limit]:
                candidates = index.get(key)
                if not candidates:
                    break
                block = next(iter(candidates))
                used.append(block)
                del free[block]
        hit_blocks = len(used)
        for position in range(hit_blocks, needed):
            block, _ = free.popitem(last=False)
            old = physical.pop(block, None)
            if old is not None:
                del index[old][block]
                if not index[old]:
                    del index[old]
            if position < len(hashes):
                key = hashes[position]
                physical[block] = key
                index.setdefault(key, {})[block] = None
            used.append(block)
        for block in reversed(used):
            free[block] = None
        results.append(
            RequestCacheResult(
                id=request.id, prompt_tokens=n, cached_tokens=hit_blocks * config.block_size
            )
        )
    return SimulationResult(
        total_prompt_tokens=sum(r.prompt_tokens for r in results),
        cached_tokens=sum(r.cached_tokens for r in results),
        requests=results,
    )
