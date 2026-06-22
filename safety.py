import re

from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, VALID_TIERS

_client = Groq(api_key=GROQ_API_KEY)

# Fail-closed default: see specs/classifier-spec.md "Fallback behavior". A parse
# or API failure must never expose unguarded instructions (don't fail to "safe"),
# but also shouldn't refuse every transient hiccup (don't fail to "refuse").
_FALLBACK_TIER = "caution"
_FALLBACK_REASON = "Could not parse a valid tier from the classifier; defaulting to caution."

_SYSTEM_PROMPT = """You are a safety classifier for a home-repair Q&A assistant. Your only job is to assign the user's home-repair question to exactly one safety tier. You do not answer the question.

The three tiers:

safe — Routine maintenance or a low-risk repair a typical homeowner can complete with basic tools and no permit. The worst realistic outcome of a mistake is cosmetic damage or a broken fixture: NOT injury, fire, flooding, or structural failure.
Examples: patching small drywall holes, painting, replacing a light bulb, unclogging a drain with a plunger or snake, tightening hardware, replacing weather stripping, replacing a toilet seat, cosmetic re-caulking.

caution — A repair a motivated homeowner can do that touches a water or electrical system as a LIKE-FOR-LIKE SWAP AT AN EXISTING LOCATION. A mistake has real cost or mild injury risk (a tripped breaker, a leak, a damaged fixture) but cannot plausibly cause fire, flooding, structural failure, or serious injury.
Examples: replacing a faucet, replacing a toilet or its flapper, resetting or replacing a GFCI outlet, replacing an existing light switch or fixture at the same location, installing a smart thermostat in place of an existing one, re-grouting tile, replacing a showerhead, replacing an outlet that stopped working.

refuse — A repair where an amateur mistake can plausibly cause fire, flooding, structural failure, serious injury, or death, OR where local code requires a licensed professional and a permit.
Examples: ANY gas work (lines, appliances, shutoffs, a gas smell); ANY electrical panel or service-entrance work; ADDING a new outlet, circuit, switch, or wiring run anywhere; removing or modifying a wall not confirmed non-load-bearing by an engineer; replacing the main water shutoff or running new plumbing lines; replacing a water heater; foundation or structural roof work.

Decision rules — apply in order:
1. Ask: if this repair goes wrong, can it plausibly cause fire, flooding, structural failure, serious injury, or death? If yes -> refuse.
2. ELECTRICAL: replacing/resetting an existing device at the same location with no new wiring is caution. ADDING or extending wiring, circuits, or devices, or any panel/service work, is refuse. "Moving a switch a few inches" or "extending a line a little" requires new wiring and is refuse — classify by the work required, not how small the user makes it sound.
3. GAS is always refuse. Wall removal is refuse unless the user states an engineer confirmed it is non-load-bearing. Water heater replacement is refuse unless clearly limited to a minor component like an anode rod or heating element.
4. If you are genuinely torn between two tiers, choose the SAFER (more restrictive) one. Never downgrade a borderline case to the riskier-to-answer tier.

Respond in EXACTLY this format and nothing else:
Reason: <one sentence stating the worst realistic outcome if this repair goes wrong>
Tier: <safe, caution, or refuse>"""


def _parse_tier(raw: str) -> str:
    """Extract a valid tier token from the model's raw response, or "" if none."""
    # Primary path: the explicit "Tier:" line.
    match = re.search(r"(?im)^\s*tier\s*:\s*(.+)$", raw)
    if match:
        token = re.sub(r"[^a-z]", "", match.group(1).lower())
        if token in VALID_TIERS:
            return token

    # Secondary recovery: first standalone tier word anywhere in the response.
    found = re.search(r"(?i)\b(safe|caution|refuse)\b", raw)
    if found:
        return found.group(1).lower()

    return ""


def _parse_reason(raw: str, tier: str) -> str:
    """Extract the one-sentence reason, falling back gracefully if it's missing."""
    match = re.search(r"(?im)^\s*reason\s*:\s*(.+)$", raw)
    if match and match.group(1).strip():
        return match.group(1).strip()

    # No explicit Reason line: use the first non-empty line that isn't the tier line.
    for line in raw.splitlines():
        line = line.strip()
        if line and not re.match(r"(?i)^tier\s*:", line):
            return line

    return f"Classified as {tier}."


def classify_safety_tier(question: str) -> dict:
    """
    Classify a home repair question into one of three safety tiers.

    See specs/classifier-spec.md for the full design rationale: a single
    chat-completion LLM-as-judge call using tier definitions + decision rules,
    a two-line "Reason:/Tier:" output format, tolerant parsing, and a
    fail-closed ("caution") fallback on any parse or API failure.

    Returns:
      - "tier"   : str — one of "safe", "caution", "refuse"
      - "reason" : str — a brief explanation of why this tier was assigned
    """
    try:
        completion = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Classify this home repair question:\n\n{question}",
                },
            ],
            # Deterministic classification: same question -> same tier.
            temperature=0,
        )
        raw = (completion.choices[0].message.content or "").strip()
    except Exception as exc:  # API / network failure — fail closed, stay running.
        return {
            "tier": _FALLBACK_TIER,
            "reason": f"Classifier unavailable ({exc.__class__.__name__}); defaulting to caution.",
        }

    tier = _parse_tier(raw)
    if tier not in VALID_TIERS:
        return {"tier": _FALLBACK_TIER, "reason": _FALLBACK_REASON}

    return {"tier": tier, "reason": _parse_reason(raw, tier)}
