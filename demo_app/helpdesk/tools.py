"""Static tool definitions. The BEFORE builder deliberately scrambles their order."""

from cachekit.models import JsonObject

_DESCRIPTIONS = {
    "lookup_order": "Look up an order's status, dispatch date, and included items.",
    "track_shipment": "Read carrier tracking events for an order.",
    "check_return": "Check return eligibility without creating or modifying a return.",
    "create_return": "Create a return request after the customer confirms the item and reason.",
    "search_policy": "Find an applicable section of the company support handbook.",
    "escalate_ticket": "Create a specialist escalation with a customer-approved summary.",
}

TOOLS: dict[str, JsonObject] = {
    name: {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"reference": {"type": "string"}},
                "required": ["reference"],
                "additionalProperties": False,
            },
        },
    }
    for name, description in _DESCRIPTIONS.items()
}
