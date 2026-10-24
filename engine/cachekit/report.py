"""Pure offline analysis orchestration and deterministic report assembly."""

import hashlib

from cachekit import __version__
from cachekit.analyze.breakers import structural_breakers
from cachekit.analyze.classify import HINTS, SAFE, classify
from cachekit.analyze.routes import group_routes
from cachekit.analyze.template import SegmentTemplate, extract_template, project_remaining
from cachekit.models import BackendResult, Finding, Report, RequestRecord
from cachekit.privacy import redact
from cachekit.radix import TokenRadix, downsample
from cachekit.render.canonical import segment_key, segments
from cachekit.render.tokenize import PromptTokenizer, TokenizedRequest, token_position, tokenize
from cachekit.serialization import canonical_json
from cachekit.settings import AnalysisConfig, RunConfig
from cachekit.simulate.rewrite import rewrite
from cachekit.simulate.vllm import simulate


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _severity(tokens: int, fraction: float, config: AnalysisConfig) -> str:
    if tokens >= config.high_stable_tokens and fraction >= config.high_affected_fraction:
        return "high"
    return "medium" if tokens >= config.medium_stable_tokens else "low"


def _templates(records: list[RequestRecord], config: AnalysisConfig) -> list[SegmentTemplate]:
    grouped: dict[str, dict] = {}
    sample_ids = {r.id for r in sorted(records, key=lambda r: r.id)[: config.sample_limit]}
    for record in records:
        for segment in segments(record):
            if segment.role not in {"system", "user"}:
                continue
            key = segment_key(segment)
            entry = grouped.setdefault(key, {"segment": segment, "texts": {}})
            entry["texts"][record.id] = segment.text
    result: list[SegmentTemplate] = []
    by_id = {r.id: r for r in records}
    for key, entry in sorted(grouped.items()):
        texts = entry["texts"]
        sample = {k: v for k, v in texts.items() if k in sample_ids}
        if len(sample) < 2:
            continue
        segment = entry["segment"]
        template = extract_template(
            sample, key=key, kind=segment.kind, index=segment.index, role=segment.role
        )
        project_remaining(template, texts)
        for span in template.spans:
            context = template.text[max(0, span.start - 100) : span.start]
            span.label = classify(
                span, context=context, records=by_id, large_hole_chars=config.large_hole_chars
            )
            span.safe_to_move = span.label in SAFE
        result.append(template)
    return result


def _placements(record: RequestRecord, text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    cursor = 0
    for segment in segments(record):
        if segment.kind == "tools":
            continue
        position = text.find(segment.text, cursor)
        if position < 0:
            raise ValueError(
                "The chat template transforms message text; exact span mapping is unsupported"
            )
        result[segment_key(segment)] = position
        cursor = position + len(segment.text)
    return result


def _rendered_template(
    tokens: dict[str, TokenizedRequest], config: AnalysisConfig
) -> SegmentTemplate:
    ordered = sorted(tokens)
    texts = {key: tokens[key].text for key in ordered[: config.sample_limit]}
    template = extract_template(texts, key="rendered", kind="rendered", index=0, role=None)
    project_remaining(template, {key: value.text for key, value in tokens.items()})
    return template


def _stable_intervals(
    template: SegmentTemplate, tokens: dict[str, TokenizedRequest], min_chars: int
) -> dict[str, list[tuple[int, int]]]:
    result: dict[str, list[tuple[int, int]]] = {key: [] for key in tokens}
    base_cursor = 0
    cursors = dict.fromkeys(tokens, 0)
    gaps: list[tuple[int, int, dict[str, tuple[int, int]]]] = []
    for span in template.spans:
        ranges = {key: (cursors[key], span.ranges[key][0]) for key in tokens}
        gaps.append((base_cursor, span.start, ranges))
        base_cursor = span.end
        cursors = {key: span.ranges[key][1] for key in tokens}
    gaps.append(
        (
            base_cursor,
            len(template.text),
            {key: (cursors[key], len(value.text)) for key, value in tokens.items()},
        )
    )
    for start, end, ranges in gaps:
        content = template.text[start:end]
        if len(content.strip()) < min_chars:
            continue
        if all(
            a <= b and value.text[a:b] == content
            for key, value in tokens.items()
            for a, b in [ranges[key]]
        ):
            for key in tokens:
                result[key].append(ranges[key])
    return result


def _stable_after(request: TokenizedRequest, ranges: list[tuple[int, int]], char: int) -> int:
    return sum(
        left >= char and any(a <= left and right <= b for a, b in ranges)
        for left, right in request.offsets
    )


def _finding(
    route: str,
    breaker: str,
    location: str,
    ids: list[str],
    positions: dict[str, int],
    end_chars: dict[str, int],
    tokens: dict[str, TokenizedRequest],
    stable: dict[str, list[tuple[int, int]]],
    config: AnalysisConfig,
    n_requests: int,
    *,
    safe: bool = False,
) -> Finding:
    counts = [_stable_after(tokens[key], stable[key], end_chars[key]) for key in ids]
    stable_count = min(counts, default=0)
    waste = sum(counts)
    return Finding(
        id=_hash([route, breaker, location])[:24],
        route=route,
        breaker=breaker,
        severity=_severity(stable_count, len(ids) / n_requests if n_requests else 0, config),
        first_divergence_token=min((positions[key] for key in ids), default=0),
        stable_tokens_after=stable_count,
        requests_affected=len(ids),
        tokens_wasted=waste,
        waste_by_backend={
            "vllm": {
                "potential_stable_tokens_recomputed": waste,
                "attribution": "overlapping_potential_not_additive",
            }
        },
        safe_to_move=safe,
        fix_hint=HINTS[breaker],
        evidence=[f"<redacted:{breaker}> at {location}; observed across {len(ids)} requests"],
    )


def analyze(
    records: list[RequestRecord],
    config: RunConfig,
    tokenizer: PromptTokenizer,
    *,
    input_sha256: str,
) -> Report:
    if len({r.id for r in records}) != len(records):
        raise ValueError("Request IDs must be unique")
    groups = group_routes(records, config.analysis.route_prefix_chars)
    actual_tokens = {r.id: tokenize(r, tokenizer) for r in records}
    projected: list[TokenizedRequest] = []
    findings: list[Finding] = []
    heatmaps: dict[str, list[float]] = {}
    previews: dict[str, str] = {}
    grouping: dict[str, str] = {}
    for route, items in groups.items():
        grouping[route] = (
            "explicit_route" if items[0].route is not None else "masked_system_and_tool_set_hash"
        )
        tokens = {r.id: actual_tokens[r.id] for r in items}
        templates = _templates(items, config.analysis)
        full_template = _rendered_template(tokens, config.analysis)
        stable = _stable_intervals(full_template, tokens, config.analysis.min_anchor_chars)
        places = {r.id: _placements(r, tokens[r.id].text) for r in items}
        by_id = {r.id: r for r in items}
        for template in templates:
            for span in template.spans:
                positions: dict[str, int] = {}
                ends: dict[str, int] = {}
                for key, (start, end) in span.ranges.items():
                    offset = places[key][template.key]
                    positions[key] = token_position(tokens[key], offset + start)
                    ends[key] = offset + end
                ids = sorted(positions)
                finding = _finding(
                    route,
                    span.label,
                    f"{template.key}:{span.start}:{span.end}",
                    ids,
                    positions,
                    ends,
                    tokens,
                    stable,
                    config.analysis,
                    len(items),
                    safe=span.safe_to_move,
                )
                # Message questions are not breakers just because later history exists.
                if template.role == "user":
                    source_start = places[template.baseline_id][template.key]
                    following = [
                        (source_start + max(a, span.end), source_start + b)
                        for a, b in template.stable_ranges()
                        if b > span.end
                    ]
                    if (
                        _stable_after(
                            tokens[template.baseline_id], following, source_start + span.end
                        )
                        < config.analysis.medium_stable_tokens
                    ):
                        span.safe_to_move = False
                        continue
                if finding.stable_tokens_after < config.analysis.min_stable_tokens:
                    span.safe_to_move = False
                    continue
                findings.append(finding)
        structural = structural_breakers(items)
        for problem in structural:
            positions = {}
            ends = {}
            for key in problem.request_ids:
                record = by_id[key]
                current = tokens[key]
                if problem.breaker in {"tool_order", "tool_set_varies"}:
                    alternative = record.model_copy(deep=True)
                    alternative.tools = items[0].tools
                    other = tokenize(alternative, tokenizer).token_ids
                    first = next(
                        (
                            i
                            for i, (a, b) in enumerate(zip(current.token_ids, other, strict=False))
                            if a != b
                        ),
                        min(len(current.token_ids), len(other)),
                    )
                    if current.token_ids == other:
                        # Locate the baseline's change using a different observed ordering.
                        different = next((r for r in items if r.tools != record.tools), None)
                        if different is not None:
                            alternative.tools = different.tools
                            other = tokenize(alternative, tokenizer).token_ids
                            first = next(
                                (
                                    i
                                    for i, (a, b) in enumerate(
                                        zip(current.token_ids, other, strict=False)
                                    )
                                    if a != b
                                ),
                                min(len(current.token_ids), len(other)),
                            )
                    char = (
                        current.offsets[first][0]
                        if first < len(current.offsets)
                        else len(current.text)
                    )
                elif problem.breaker.startswith("history_"):
                    first_message = next(
                        (
                            segment
                            for segment in segments(record)
                            if segment.role not in {None, "system"}
                        ),
                        None,
                    )
                    char = (
                        places[key][segment_key(first_message)]
                        if first_message
                        else len(current.text)
                    )
                    first = token_position(current, char)
                else:
                    first, char = 0, 0
                positions[key], ends[key] = first, char
            findings.append(
                _finding(
                    route,
                    problem.breaker,
                    "structural",
                    problem.request_ids,
                    positions,
                    ends,
                    tokens,
                    stable,
                    config.analysis,
                    len(items),
                    safe=problem.breaker == "tool_order",
                )
            )
        sort_tools = any(p.breaker == "tool_order" for p in structural)
        for record in items:
            projected.append(tokenize(rewrite(record, templates, sort_tools=sort_tools), tokenizer))
        reference = tokens[full_template.baseline_id]
        tree = TokenRadix()
        for request in tokens.values():
            tree.insert(request.token_ids)
        stability = tree.prefix_stability(reference.token_ids)
        for i, (start, end) in enumerate(reference.offsets):
            if any(a <= start and end <= b for a, b in stable[reference.id]):
                stability[i] = 1
        heatmaps[route] = downsample(stability, config.analysis.heatmap_points)
        preview = full_template.text
        for span in reversed(full_template.spans):
            preview = preview[: span.start] + "⟦variable⟧" + preview[span.end :]
        previews[route] = redact(preview, config.analysis.redaction_patterns)
    before = simulate(list(actual_tokens.values()), config.vllm)
    after = simulate(projected, config.vllm)
    params = config.vllm.model_dump(mode="json") | {
        "tokenizer": tokenizer.identity,
        "route_grouping": grouping,
        "sample_limit": config.analysis.sample_limit,
        "limitations": [
            "Sequential prompt-only simulation; decode blocks and concurrency are not modeled.",
            "Achievable is a simulated reordering, not a fix or evidence of behavioral safety.",
            "Hole discovery is sampled; static ranges are confirmed against every route request.",
            "Finding waste is overlapping potential recomputation, not additive causal savings.",
            "Personalization requiring review and history repair are not automatically rewritten.",
            "Plain-text full-attention prompts only; hybrid, LoRA and multimodal are unsupported.",
            "Logs are re-rendered for the configured model, not simulated for source providers.",
            "Glaive calls/results use text; native tool-call rendering is not inferred.",
            "Costs are unset: simulated vLLM prompt tokens do not establish GPU dollar savings.",
        ],
    }
    return Report(
        version=__version__,
        input_sha256=input_sha256,
        config_sha256=_hash(
            {"config": config.model_dump(mode="json"), "tokenizer": tokenizer.identity}
        ),
        n_requests=len(records),
        routes=list(groups),
        backends=[
            BackendResult(
                backend="vllm",
                params=params,
                actual_hit_rate=before.hit_rate,
                achievable_hit_rate=after.hit_rate,
                tokens_recomputed_actual=before.total_prompt_tokens - before.cached_tokens,
                tokens_recomputed_achievable=after.total_prompt_tokens - after.cached_tokens,
            )
        ],
        findings=sorted(findings, key=lambda f: (-f.tokens_wasted, f.id)),
        heatmaps=heatmaps,
        template_preview=previews,
    )
