"""BEFORE builder with the six documented planted cache-breakers.

The handbook is loaded once as an immutable package resource. build_request itself
does no I/O and reads neither the clock nor global random state. Re-render it in a
process using the recorded worker_seed to reproduce the intentional set ordering.
"""

from copy import deepcopy
from datetime import datetime
from importlib.resources import files
from random import Random

from cachekit.models import JsonObject

from demo_app.helpdesk.catalog import EXAMPLES
from demo_app.helpdesk.models import ChatRequest, HelpdeskInput
from demo_app.helpdesk.tools import TOOLS

POLICY_TEXT = files("demo_app.helpdesk").joinpath("policy.txt").read_text(encoding="utf-8")


def build_request(inp: HelpdeskInput, *, now: datetime, rng: Random) -> JsonObject:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    examples = "\n\n".join(f"Customer: {q}\nAgent: {a}" for q, a in rng.sample(EXAMPLES, 3))
    context = "\n\n".join(f"Document {doc.id}\n{doc.text}" for doc in inp.retrieved_docs)
    system = (
        f"Current time: {now.isoformat()}\n"
        f"Customer: {inp.user.name} (id {inp.user.id}, tier {inp.user.tier})\n"
        f"Locale: {inp.user.locale}\n\n"
        f"Support examples\n{examples}\n\n"
        f"Retrieved context\n{context}\n\n"
        f"Company support handbook\n{POLICY_TEXT}"
    )
    # Intentionally unsorted, as specified in docs/05. Never copy this into a real app.
    tools = [deepcopy(TOOLS[name]) for name in set(TOOLS)]
    return ChatRequest(
        messages=[
            {"role": "system", "content": system},
            *[message.model_dump(exclude_none=True) for message in inp.history[-6:]],
            {"role": "user", "content": inp.message},
        ],
        tools=tools,
    ).model_dump(mode="json", exclude_none=True)
