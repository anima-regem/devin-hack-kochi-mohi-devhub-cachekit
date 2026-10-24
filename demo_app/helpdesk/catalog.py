"""Fictional support examples, documents, and question bank. No real user data."""

# The Cartesian product gives a fixed bank of varied, reproducible support questions.
_QUESTIONS = (
    "Can I change my delivery address before dispatch?",
    "How can I track my shipment?",
    "My delivery is late. What can I do?",
    "The parcel says delivered, but I cannot find it.",
    "Can I return an item I have opened?",
    "How do I start a return?",
    "Who pays for return shipping?",
    "When should I expect my refund?",
    "Can I exchange this for another model?",
    "My item arrived damaged. What should I send you?",
    "There is a part missing from the package.",
    "How long is the warranty?",
    "Can I request a repair under warranty?",
    "What should I do if the replacement is also faulty?",
    "Can I cancel my order?",
    "I think I was charged twice. Can you check?",
    "Can I get a copy of my invoice?",
    "My promotional code did not apply.",
    "Can you split my shipment?",
    "How do I update my account email?",
    "Can somebody else collect my delivery?",
    "Do you offer an accessible version of the instructions?",
    "Can I return a gift without the original receipt?",
    "How can I escalate an unresolved support ticket?",
    "I ordered several items, but only one arrived.",
)
_PRODUCTS = (
    "a desk lamp",
    "a keyboard",
    "a monitor stand",
    "headphones",
    "a charging dock",
    "a wireless mouse",
    "a laptop sleeve",
    "a desk mat",
    "a USB hub",
    "a webcam",
    "a reading light",
    "a cable organizer",
)
QUESTIONS = tuple(
    f"{question} My order contains {product}." for question in _QUESTIONS for product in _PRODUCTS
)

EXAMPLES = (
    (
        "Change my address.",
        "I can check whether dispatch has started. Please share your order reference; an address "
        "update depends on its current status.",
    ),
    (
        "Where is my parcel?",
        "I can look up the tracking record and explain the latest carrier event. "
        "A delivery estimate is not a guarantee.",
    ),
    (
        "My delivery is late.",
        "I understand the delay is frustrating. I will check the dispatch date and tracking events "
        "before proposing the next step.",
    ),
    (
        "Tracking says delivered.",
        "Please check the delivery location and household first. "
        "I can open a carrier investigation if the parcel is still missing.",
    ),
    (
        "Can I return this?",
        "I can check the delivery date, condition, and product category against the return policy "
        "before confirming eligibility.",
    ),
    (
        "Start a return.",
        "I can help check eligibility and create a return request after you confirm "
        "the item and the reason for returning it.",
    ),
    (
        "Who pays postage?",
        "Return shipping depends on the reason. A verified defect or shipping error is handled "
        "differently from a change of mind.",
    ),
    (
        "Where is my refund?",
        "I can check whether the return was received and the refund issued. Your bank may need "
        "additional processing time.",
    ),
    (
        "I want an exchange.",
        "I can check available stock and eligibility. "
        "I will explain any difference in price before requesting confirmation.",
    ),
    (
        "The item is damaged.",
        "Please keep the packaging if possible. I can record the damage and explain the evidence "
        "needed for a replacement review.",
    ),
    (
        "A part is missing.",
        "I can check the packing list and identify the missing component. "
        "A complete product return may not be necessary.",
    ),
    (
        "Is this under warranty?",
        "I can compare the purchase date and fault description with the warranty terms. Accidental "
        "damage requires separate review.",
    ),
    (
        "Please repair this.",
        "I can check warranty eligibility and the repair process. I cannot promise a repair "
        "completion date before assessment.",
    ),
    (
        "The replacement failed.",
        "I will preserve the previous case details and escalate the repeated fault so you do not "
        "have to explain the issue again.",
    ),
    (
        "Cancel my order.",
        "I can check whether cancellation is still possible. Once dispatch begins, the return "
        "process may be the available option.",
    ),
    (
        "I was charged twice.",
        "I can check the transaction references and distinguish a pending authorization from a "
        "completed duplicate payment.",
    ),
    (
        "Send an invoice.",
        "I can help retrieve the invoice associated with your order. I will not ask for a full "
        "payment card number.",
    ),
    (
        "My code failed.",
        "I can check the promotion dates, eligible products, and exclusions. I will not promise a "
        "discount that the policy does not allow.",
    ),
    (
        "I need accessible instructions.",
        "I can provide the available accessible guide and describe the setup steps "
        "in plain language without relying on diagrams alone.",
    ),
    (
        "Escalate my case.",
        "I can summarize the unresolved issue and previous steps for the specialist team. I will "
        "give you the case reference for follow-up.",
    ),
)
