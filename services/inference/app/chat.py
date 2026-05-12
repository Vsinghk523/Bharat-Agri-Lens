"""Template-based chat replies.

A deliberately simple keyword matcher. The contract — text in, reply
+ model_version out — is what the real LLM (Gemma + RAG over the
curated agronomy corpus) will slot into when it's ready.

All canned text is English. The API translates to the user's language
via Bhashini on the way out, so this module never sees other locales.
"""

from __future__ import annotations

import re

# Each rule is (pattern, reply). First match wins. Patterns are
# intentionally narrow — keywords actual farmers use rather than
# academic jargon — so the canned replies don't fire on tangentially
# related queries.
RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(pest|insect|bug|caterpillar|aphid|mite|bollworm|whitefly|thrips)\b",
            re.I,
        ),
        "Pest pressure usually shows as chewed leaves, sticky residue, or visible insects "
        "on the underside of leaves. Confirm the species with the Scan feature, then apply "
        "neem oil 3% (5 ml per litre of water) as a weekly foliar spray for early-stage "
        "infestations. For severe outbreaks, contact your local KVK officer for a "
        "CIBRC-approved pesticide recommendation suited to your crop.",
    ),
    (
        re.compile(
            r"\b(leaf|leaves|spot|yellow|wilt|blight|mildew|mold|rust|fungus|fungal)\b",
            re.I,
        ),
        "Leaf symptoms often point to fungal disease, viral infection, or a nutrient gap. "
        "Use the Scan feature for a confirmed diagnosis. General prevention: avoid "
        "overhead irrigation, maintain 30+ cm spacing between plants for airflow, and "
        "rotate crops each season to break the disease cycle.",
    ),
    (
        re.compile(r"\b(water|irrigation|drought|moisture|dry|thirst)\b", re.I),
        "Most field crops need about 25 mm (1 inch) of water per week. Test soil "
        "moisture by inserting your finger 5–7 cm below the surface — if it feels dry, "
        "water deeply rather than frequently. Drip or furrow irrigation in the early "
        "morning loses far less water to evaporation than midday overhead sprinklers.",
    ),
    (
        re.compile(
            r"\b(fertili[sz]er|soil|nitrogen|phosphorus|potassium|nutrient|compost|manure)\b",
            re.I,
        ),
        "Conduct a soil test at your nearest KVK centre before fertilising — "
        "over-application wastes money and pollutes groundwater. Common visible "
        "deficiencies: nitrogen → pale lower leaves, phosphorus → purplish leaf "
        "undersides, potassium → brown leaf edges and tip scorch.",
    ),
    (
        re.compile(r"\b(seed|seedling|sowing|transplant|germinat)\b", re.I),
        "Use certified seed from a recognised supplier whenever possible — saved seed "
        "often carries seed-borne pathogens. Soak seeds in lukewarm water for 4–6 hours "
        "before sowing to break dormancy. Transplant seedlings on a cloudy evening to "
        "reduce transplant shock.",
    ),
]

DEFAULT_REPLY = (
    "Thank you for your question. For a tailored recommendation, please use the Scan "
    "feature with a clear photo of the affected plant. For complex or persistent "
    "problems, your local KVK (Krishi Vigyan Kendra) extension officer can offer "
    "field-tested guidance specific to your region."
)

VERSION = "bal-chat-template-v0"


def generate_reply(message: str, language: str = "en") -> dict[str, str]:
    """Return a canned reply for ``message`` plus the model version."""
    text = (message or "").strip()
    for pattern, response in RULES:
        if pattern.search(text):
            return {"reply": response, "model_version": VERSION}
    return {"reply": DEFAULT_REPLY, "model_version": VERSION}
