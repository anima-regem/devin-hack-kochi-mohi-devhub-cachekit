import pytest
from cachekit.analyze.breakers import structural_breakers
from cachekit.analyze.classify import classify
from cachekit.analyze.routes import group_routes
from cachekit.analyze.template import VariableSpan, extract_template
from cachekit.models import RequestRecord
from cachekit.privacy import redact
from cachekit.radix import TokenRadix
from cachekit.report import analyze
from cachekit.serialization import canonical_json


def records(values: list[str], *, before: bool = True) -> list[RequestRecord]:
    policy = "Company policy: follow the approved returns process.\n" * 24
    return [
        RequestRecord(
            id=str(i),
            ts=i,
            route="test",
            session_id=str(i),
            messages=[
                {"role": "system", "content": value + "\n" + policy if before else policy + value},
                {"role": "user", "content": "question"},
            ],
        )
        for i, value in enumerate(values)
    ]


def label(values: list[str], context: str = "") -> str:
    items = records(values)
    span = VariableSpan(
        start=0,
        end=1,
        values={r.id: v for r, v in zip(items, values, strict=True)},
        ranges={r.id: (0, len(v)) for r, v in zip(items, values, strict=True)},
    )
    return classify(span, context=context, records={r.id: r for r in items}, large_hole_chars=200)


@pytest.mark.parametrize(
    "positive,context,expected,negative",
    [
        (
            ["2026-10-24T12:01:01+00:00", "2026-10-24T12:02:02+00:00"],
            "Current time:",
            "timestamp",
            ["2026-99-99", "2026-99-98"],
        ),
        (
            ["12345678-1234-4123-8123-123456789012", "87654321-1234-4123-8123-123456789012"],
            "",
            "request_id",
            ["plain text", "another value"],
        ),
        (['{"a":1,"b":2}', '{"b":2,"a":1}'], "", "json_key_order", ['{"a":1}', '{"a":2}']),
        (["a b", "a  b"], "", "whitespace_template", ["refund allowed", "refund denied"]),
        (["Alex", "Morgan"], "Customer:", "user_identity", ["hello", "world"]),
        (
            [
                "Question: " + "x" * 120 + "\nAnswer: " + "y" * 120,
                "Question: " + "a" * 120 + "\nAnswer: " + "b" * 120,
            ],
            "Examples:",
            "few_shot_sampling",
            ["small", "tiny"],
        ),
        (
            ["retrieved A " + "x" * 220, "retrieved B " + "y" * 220],
            "Context:",
            "rag_before_static",
            ["small", "tiny"],
        ),
    ],
)
def test_classification_positive_and_near_miss(positive, context, expected, negative) -> None:
    assert label(positive, context) == expected
    assert label(negative) != expected


def test_clean_route_has_no_findings_and_no_achievable_gap(config, char_tokenizer) -> None:
    items = records(["Stable system."] * 3)
    result = analyze(items, config, char_tokenizer, input_sha256="a" * 64)
    assert result.findings == []
    assert result.backends[0].actual_hit_rate == result.backends[0].achievable_hit_rate


def test_timestamp_before_policy_detected_and_tail_does_not_claim_policy_waste(
    config, char_tokenizer
) -> None:
    values = ["Current time: 2026-10-24T12:01:01+00:00", "Current time: 2026-10-24T12:02:02+00:00"]
    result = analyze(records(values), config, char_tokenizer, input_sha256="a" * 64)
    finding = next(f for f in result.findings if f.breaker == "timestamp")
    assert finding.stable_tokens_after > 1000
    assert result.backends[0].achievable_hit_rate > result.backends[0].actual_hit_rate
    tail = analyze(records(values, before=False), config, char_tokenizer, input_sha256="a" * 64)
    assert not any(f.breaker == "timestamp" for f in tail.findings)


def test_routes_ignore_tool_order_but_preserve_explicit_labels() -> None:
    items = records(["Current time: 2026-10-24", "Current time: 2026-10-25"])
    for record in items:
        record.route = None
    items[0].tools = [{"name": "a"}, {"name": "b"}]
    items[1].tools = [{"name": "b"}, {"name": "a"}]
    assert len(group_routes(items, 160)) == 1
    items[1].route = "another"
    assert len(group_routes(items, 160)) == 2


def test_tool_order_and_set_checks_have_clean_negatives() -> None:
    items = records(["stable", "stable"])
    items[0].tools = [{"name": "a"}, {"name": "b"}]
    items[1].tools = list(reversed(items[0].tools))
    assert "tool_order" in {b.breaker for b in structural_breakers(items)}
    items[1].tools = [{"name": "a"}]
    assert "tool_set_varies" in {b.breaker for b in structural_breakers(items)}
    items[1].tools = items[0].tools
    assert not structural_breakers(items)


def test_history_append_is_clean_but_sliding_and_rewrite_are_detected() -> None:
    def history(id, texts):
        return RequestRecord(
            id=id,
            ts=int(id),
            session_id="s",
            messages=[
                {"role": "user" if i % 2 == 0 else "assistant", "content": text}
                for i, text in enumerate(texts)
            ],
        )

    before = history("0", ["one", "reply", "two"])
    appended = history("1", ["one", "reply", "two", "reply two", "three"])
    assert not structural_breakers([before, appended])
    sliding = history("2", ["two", "reply two", "three", "reply three", "four"])
    assert "history_truncation" in {b.breaker for b in structural_breakers([appended, sliding])}
    edited = history("2", ["edited", "reply", "two", "reply two", "three"])
    assert "history_rewrite" in {b.breaker for b in structural_breakers([appended, edited])}


def test_tenant_note_requires_actual_tenant_metadata_and_missing_salt() -> None:
    items = records(["stable", "stable"])
    assert not structural_breakers(items)
    for index, r in enumerate(items):
        r.meta["tenant_id"] = str(index)
    assert "cross_tenant_shared_prefix" in {b.breaker for b in structural_breakers(items)}
    for r in items:
        r.params["cache_salt"] = r.meta["tenant_id"]
    assert not structural_breakers(items)


def test_alignment_variable_lengths_and_insertions_dont_hide_policy() -> None:
    template = extract_template(
        {
            "a": "Time: x\nPolicy stays exactly the same.\n",
            "b": "Time: much longer\nPolicy stays exactly the same.\n",
        },
        key="s",
        kind="system",
        index=0,
        role="system",
    )
    assert template.spans
    assert any("Policy" in template.text[a:b] for a, b in template.stable_ranges())


def test_redaction_and_radix_prefix_counts() -> None:
    assert redact("a@example.com", [r"\S+@\S+"]) == "<redacted>"
    tree = TokenRadix()
    tree.insert([1, 2, 3])
    tree.insert([1, 2, 4])
    tree.insert([1])
    assert tree.prefix_stability([1, 2, 3]) == [1, 2 / 3, 1 / 3]


def test_report_is_byte_identical_when_input_iteration_order_changes(
    config, char_tokenizer
) -> None:
    items = records(["Current time: 2026-10-24", "Current time: 2026-10-25"])
    a = analyze(items, config, char_tokenizer, input_sha256="a" * 64)
    b = analyze(list(reversed(items)), config, char_tokenizer, input_sha256="a" * 64)
    assert canonical_json(a) == canonical_json(b)
    assert all(len(values) <= 2000 for values in a.heatmaps.values())


def test_report_redacts_configured_stable_and_variable_secrets(config, char_tokenizer):
    items = records(["Current time: 2026-10-24", "Current time: 2026-10-25"])
    for record in items:
        record.messages[0].content += "\nCUSTOM_PRIVATE_SENTINEL\n"
    config.analysis.redaction_patterns.append("CUSTOM_PRIVATE_SENTINEL")
    report = analyze(items, config, char_tokenizer, input_sha256="a" * 64)
    payload = canonical_json(report)
    assert "CUSTOM_PRIVATE_SENTINEL" not in payload
    assert "<redacted>" in payload
    assert all("2026-10-2" not in line for f in report.findings for line in f.evidence)
