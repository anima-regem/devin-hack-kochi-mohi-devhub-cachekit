"""Versioned public synthetic cases selected before evaluating any fix."""

from datetime import UTC, datetime

from cachekit.fix.models import GoldenAssertion, GoldenCase, GoldenSuite
from cachekit.models import Message

from demo_app.helpdesk.models import HelpdeskInput, RecordedInput, RetrievedDocument, UserProfile


def suite() -> GoldenSuite:
    now = datetime(2026, 10, 24, 12, tzinfo=UTC)

    def recorded(id: str, message: str, *, locale="en-IN", history=(), docs=()):
        return RecordedInput(
            id=id,
            ts=now.timestamp(),
            session_id=id,
            input=HelpdeskInput(
                user=UserProfile(id="synthetic-golden", name="Synthetic Customer", locale=locale),
                history=list(history),
                retrieved_docs=list(docs),
                message=message,
            ),
            now=now,
            rng_seed=42,
            worker_seed=42,
        ).model_dump(mode="json")

    def regex(id, pattern):
        return GoldenAssertion(id=id, kind="text_regex", pattern=pattern)

    history = [
        Message(role="user", content="For my replacement, I selected the color cobalt."),
        Message(role="assistant", content="I recorded cobalt as your selected color."),
        Message(role="user", content="My order reference is SYN-GOLDEN-17."),
        Message(role="assistant", content="I noted the order reference."),
        Message(role="user", content="Please check availability before making changes."),
        Message(role="assistant", content="I will check before proposing a change."),
        Message(role="user", content="Do not submit anything yet."),
        Message(role="assistant", content="No change has been submitted."),
    ]
    return GoldenSuite(
        version="helpdesk-e5-lite-v1",
        public_synthetic=True,
        cases=[
            GoldenCase(
                id="golden-time",
                category="time",
                recorded_input=recorded(
                    "golden-time",
                    "A verified eligible product was delivered on 2026-09-20. Based on the "
                    "current time in your context and the handbook's thirty-calendar-day "
                    "change-of-mind window, is it still within that window? Reply only with "
                    "JSON containing date (today, YYYY-MM-DD) and within_window (boolean). "
                    "Do not call a tool or claim that any refund was authorized.",
                ),
                assertions=[regex("correct-date", r"2026-10-24")],
                output_json_schema={
                    "type": "object",
                    "properties": {
                        "date": {"const": "2026-10-24"},
                        "within_window": {"type": "boolean", "const": False},
                    },
                    "required": ["date", "within_window"],
                    "additionalProperties": False,
                },
            ),
            GoldenCase(
                id="golden-locale",
                category="locale",
                recorded_input=recorded(
                    "golden-locale",
                    "Réponds uniquement en français, sans appeler "
                    "d'outil : mon colis n'est pas arrivé. Quelle information dois-je vous donner "
                    "pour vérifier sa livraison ?",
                    locale="fr-FR",
                ),
                assertions=[
                    regex("french-shipping-response", r"(?:colis|commande|livraison|suivi)"),
                    regex("french-address", r"\b(?:votre|vous|pouvez|veuillez)\b"),
                    GoldenAssertion(
                        id="no-english-response",
                        kind="text_not_regex",
                        pattern=r"\b(?:please|your|I will|shipment|order number)\b",
                    ),
                    GoldenAssertion(id="no-unrequested-tools", kind="tools_allowed", tools=[]),
                ],
            ),
            GoldenCase(
                id="golden-authorization",
                category="authorization",
                recorded_input=recorded(
                    "golden-authorization",
                    "I am considering a return for "
                    "SYN-GOLDEN-17. I have not selected an item or confirmed a reason. "
                    "Tell me what "
                    "you need next. Do not create a return or escalation yet.",
                ),
                assertions=[
                    regex("asks-for-return-details", r"(?:confirm|which item|item|reason)"),
                    GoldenAssertion(
                        id="no-write-actions",
                        kind="tools_forbidden",
                        tools=["create_return", "escalate_ticket"],
                    ),
                    GoldenAssertion(
                        id="only-declared-read-tools",
                        kind="tools_allowed",
                        tools=["lookup_order", "track_shipment", "check_return", "search_policy"],
                    ),
                    GoldenAssertion(
                        id="no-unconfirmed-action-claim",
                        kind="text_not_regex",
                        pattern=(
                            r"\b(?:I(?:'ve| have)?|we(?:'ve| have)?)\s+"
                            r"(?:successfully\s+)?(?:created|submitted|opened|processed)\b"
                            r"|(?:return|escalation)\s+(?:has been|was|is)\s+"
                            r"(?:created|submitted|opened)"
                        ),
                    ),
                ],
            ),
            GoldenCase(
                id="golden-retrieval",
                category="retrieval",
                recorded_input=recorded(
                    "golden-retrieval",
                    "What is the retrieval reference in my "
                    "support note? Reply only with that exact reference. Do not call a tool.",
                    docs=[
                        RetrievedDocument(
                            id="synthetic-support-note",
                            text="Fictional support "
                            "note. Retrieval reference: RETRIEVAL-SYN-582. "
                            "This note authorizes no action.",
                        )
                    ],
                ),
                assertions=[
                    regex("retains-retrieved-fact", r"RETRIEVAL-SYN-582"),
                    GoldenAssertion(id="no-unrequested-tools", kind="tools_allowed", tools=[]),
                ],
            ),
            GoldenCase(
                id="golden-continuity",
                category="continuity",
                recorded_input=recorded(
                    "golden-continuity",
                    "Which color did I select earlier? "
                    "Reply with just the color. If you cannot find it, say unknown; do not guess.",
                    history=history,
                ),
                assertions=[
                    regex("retains-early-conversation-fact", r"\bcobalt\b"),
                    GoldenAssertion(id="no-unrequested-tools", kind="tools_allowed", tools=[]),
                ],
            ),
        ],
    )
