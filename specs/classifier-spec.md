# Spec: `classify_safety_tier()`

**File:** `safety.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Determine whether a home repair question is safe to answer directly, requires a cautionary response, or should be refused with a referral to a licensed professional.

---

## Input / Output Contract

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The user's home repair question |

**Output:** `dict`

| Key | Type | Description |
|-----|------|-------------|
| `"tier"` | `str` | One of: `"safe"`, `"caution"`, `"refuse"` |
| `"reason"` | `str` | One sentence explaining why this tier was assigned |

---

## Design Decisions

*Complete the fields below before writing any code. Use your AI tool in Plan or Ask mode to help you reason through what belongs here — but the decisions are yours.*

---

### Tier definitions

*Write a one-sentence definition for each tier that is precise enough to use as part of your classification prompt. Vague definitions produce inconsistent classifications.*

**safe:**
```
Routine maintenance or a low-risk repair that a typical homeowner can complete with
basic tools and no permit, where the worst realistic outcome of a mistake is cosmetic
damage or a broken fixture — not injury, fire, flooding, or structural failure.
```

**caution:**
```
A repair a motivated homeowner can do but that touches a water or electrical system as
a like-for-like swap at an existing location, where a mistake has real cost or mild
injury risk (a trip breaker, a leak, a damaged fixture) but cannot plausibly cause fire,
flooding, structural failure, or serious injury.
```

**refuse:**
```
A repair where an amateur mistake can plausibly cause fire, flooding, structural failure,
serious injury, or death, OR where local code requires a licensed professional and a
permit — including all gas work, electrical panel/service work, adding new circuits or
wiring, wall removal not confirmed non-load-bearing, main water line work, and water
heater replacement.
```

---

### Classification approach

*How will the LLM classify the question? Will you give it just the tier definitions, or also examples (few-shot)? Will you ask it to reason step-by-step before naming the tier, or output the tier directly?*

*Consider: what happens when a question is genuinely ambiguous — e.g., "can I replace my own outlets?" Which tier should that land in, and how does your approach handle questions at the boundary?*

```
Approach: the tier definitions plus a small set of few-shot examples, and I ask the model
to reason briefly before naming the tier (chain-of-thought, but constrained to one line).

- Why few-shot, not just definitions: the caution/refuse boundary is decided by a specific
  rule ("replace existing at the same location" vs. "add new wiring/circuit"), and that rule
  is much easier for the model to apply consistently when it has seen the canonical
  replace-outlet (caution) vs. add-outlet (refuse) contrast as worked examples. Definitions
  alone leave the boundary under-specified.

- Why a reasoning step: forcing the model to state the consequence-of-failure first
  ("worst case if this goes wrong is X") makes the tier fall out of the harm assessment
  rather than from surface keywords. But I keep it to a single sentence so the output stays
  cheap to parse and the model can't wander.

Genuinely ambiguous questions ("can I replace my own outlets?"): I instruct the model to
decide on the most likely literal reading. "Replace an outlet" is a like-for-like swap at an
existing location → caution, matching the tier guide. If a question is ambiguous between
caution and refuse and the model genuinely cannot tell which is meant, it must choose refuse
— the boundary fails toward the safer tier, never toward the riskier one. This is encoded
explicitly in the system message so the tie-break is deterministic, not left to model whim.
```

---

### Output format

*How will the LLM communicate the tier and reason back to you? Describe the exact text format you'll ask it to use, so you can parse it reliably.*

*The format you used in Lab 3 (`Label: X / Reasoning: Y`) is a reasonable starting point, but you're not required to use it. Whatever you choose, you'll need to parse it in code — so consider how much variation the LLM might introduce and how you'll handle that.*

```
A two-line, prefixed key/value format. The reasoning comes FIRST so the model commits to
its harm assessment before naming a tier, but the tier line is what I parse:

    Reason: <one sentence: the worst realistic outcome if this repair goes wrong>
    Tier: <safe|caution|refuse>

Parsing strategy (tolerant of the variation an LLM will introduce):
- Case-insensitive search for a line beginning with "Tier:" — take the text after the colon.
- Lowercase it, strip whitespace/punctuation/markdown (e.g. "**caution**." -> "caution").
- If the cleaned token isn't exactly in VALID_TIERS, scan the whole response for the first
  standalone occurrence of one of the three tier words as a secondary recovery path.
- Reason: take the line beginning with "Reason:"; if absent, fall back to the first
  non-empty line that isn't the tier line, or a generic message.

I deliberately do NOT ask for JSON: a single labeled token is simpler to parse robustly than
JSON the model might wrap in code fences or malform, and the two-key format leaves almost no
room for structural variation.
```

---

### Prompt structure

*Write the actual prompt you'll use — both the system message and the user message. Don't describe it — write it. Vague prompt descriptions produce vague prompts, which produce inconsistent classifications.*

**System message:**
```
You are a safety classifier for a home-repair Q&A assistant. Your only job is to assign
the user's home-repair question to exactly one safety tier. You do not answer the question.

The three tiers:

safe — Routine maintenance or a low-risk repair a typical homeowner can complete with basic
tools and no permit. The worst realistic outcome of a mistake is cosmetic damage or a broken
fixture: NOT injury, fire, flooding, or structural failure.
Examples: patching small drywall holes, painting, replacing a light bulb, unclogging a drain
with a plunger or snake, tightening hardware, replacing weather stripping, replacing a toilet
seat, cosmetic re-caulking.

caution — A repair a motivated homeowner can do that touches a water or electrical system as
a LIKE-FOR-LIKE SWAP AT AN EXISTING LOCATION. A mistake has real cost or mild injury risk (a
tripped breaker, a leak, a damaged fixture) but cannot plausibly cause fire, flooding,
structural failure, or serious injury.
Examples: replacing a faucet, replacing a toilet or its flapper, resetting or replacing a
GFCI outlet, replacing an existing light switch or fixture at the same location, installing a
smart thermostat in place of an existing one, re-grouting tile, replacing a showerhead,
replacing an outlet that stopped working.

refuse — A repair where an amateur mistake can plausibly cause fire, flooding, structural
failure, serious injury, or death, OR where local code requires a licensed professional and a
permit.
Examples: ANY gas work (lines, appliances, shutoffs, a gas smell); ANY electrical panel or
service-entrance work; ADDING a new outlet, circuit, switch, or wiring run anywhere; removing
or modifying a wall not confirmed non-load-bearing by an engineer; replacing the main water
shutoff or running new plumbing lines; replacing a water heater; foundation or structural
roof work.

Decision rules — apply in order:
1. Ask: if this repair goes wrong, can it plausibly cause fire, flooding, structural failure,
   serious injury, or death? If yes -> refuse.
2. ELECTRICAL: replacing/resetting an existing device at the same location with no new wiring
   is caution. ADDING or extending wiring, circuits, or devices, or any panel/service work,
   is refuse. "Moving a switch a few inches" or "extending a line a little" requires new wiring
   and is refuse — classify by the work required, not how small the user makes it sound.
3. GAS is always refuse. Wall removal is refuse unless the user states an engineer confirmed it
   is non-load-bearing. Water heater replacement is refuse unless clearly limited to a minor
   component like an anode rod or heating element.
4. If you are genuinely torn between two tiers, choose the SAFER (more restrictive) one. Never
   downgrade a borderline case to the riskier-to-answer tier.

Respond in EXACTLY this format and nothing else:
Reason: <one sentence stating the worst realistic outcome if this repair goes wrong>
Tier: <safe, caution, or refuse>
```

**User message:**
```
Classify this home repair question:

{question}
```

---

### Caution/refuse boundary

*The most consequential classification decision is whether a question lands in "caution" or "refuse." Write down your rule for this boundary — one sentence. Then give two examples of questions that sit close to the line and explain which side they fall on and why.*

```
Rule: it is caution only if the work is a like-for-like swap of an existing component at its
existing location with no new wiring/piping and no fire/flood/structural/serious-injury
failure mode; the moment it requires new wiring, new circuits, gas, structural judgment, or
a permit-grade system, it is refuse.

Example 1 — "Can I replace an electrical outlet that stopped working?" → CAUTION.
The outlet sits on an existing circuit at an existing box; it's a like-for-like swap. The
worst realistic outcome of miswiring is a tripped breaker or a dead outlet — recoverable, not
a hidden fire hazard. No new wire, no panel, no permit.

Example 2 — "Can I add a new electrical outlet to my garage?" → REFUSE.
"Add" means running a new circuit/wire from the panel to a new location: opening the panel,
fishing wire through walls, and a permit. A wiring mistake here is a fire hazard that can go
undetected for years. Same component as Example 1, opposite tier — the discriminator is
"replace existing" vs. "add new wiring."
```

---

### Fallback behavior

*What does your function return if the LLM response can't be parsed — e.g., if it produces free-form prose instead of your expected format? What happens when tier validation against `VALID_TIERS` fails?*

*Note: failing open (returning "safe" as a fallback) is more dangerous than failing closed (returning "caution"). Which makes more sense here, and why?*

```
Fallback tier is "caution" (fail closed). This fires in two cases:
1. The response can't be parsed — no recognizable "Tier:" line and no standalone tier word
   anywhere in the text.
2. A tier token is found but isn't in VALID_TIERS after cleaning.

The accompanying reason is set to a diagnostic string (e.g. "Could not parse a valid tier from
the classifier; defaulting to caution.") so the failure is visible in the UI and the audit log
rather than masquerading as a real classification.

Why caution and not safe: failing open to "safe" would hand a user full how-to instructions for
a question the system never actually understood — the exact failure the safety layer exists to
prevent. Failing to "caution" degrades gracefully: the responder still answers but wraps the
answer in safety warnings and a professional-review recommendation. I deliberately do NOT fail
all the way to "refuse" either: a parse failure isn't evidence the task is dangerous, and
refusing every unparseable question would make the system useless on transient LLM hiccups.
Caution is the correct middle: safe enough to never expose unguarded instructions, useful
enough to stay functional. Network/API errors are also caught and resolved to this same
fail-closed default rather than crashing the pipeline.
```

---

## Implementation Notes

*Fill this in after implementing, before moving to Milestone 2.*

**One classification that surprised you — question, tier you expected, tier it returned, and why:**

```
Question: "How do I replace the anode rod in my water heater?"
Expected: I half-expected refuse, because the tier guide makes water heater REPLACEMENT a
refuse case and "water heater" is a strong refuse keyword.
Returned: caution.
Why it was actually right: the model correctly distinguished replacing a minor component (the
anode rod) from replacing the whole unit, which is exactly the carve-out the tier guide
specifies ("unless clearly limited to a minor component like an anode rod or heating element").
It classified by the work required, not the scary keyword — the behavior the decision rules
were written to produce.
```

**One prompt change you made after seeing the first few outputs, and what it fixed:**

```
I put the reasoning line BEFORE the tier line in the required output format (Reason: then
Tier:), rather than the more natural Tier-then-Reason order. Asking the model to state the
worst-case-if-it-goes-wrong sentence first makes the tier fall out of that harm assessment
instead of from a surface keyword. This is what got the "move a light switch six inches" case
right — the model reasoned "this requires new wiring -> fire/shock risk" before committing, so
the small-scope framing didn't pull it down to caution. Parsing still keys off the "Tier:"
line, so the ordering change cost nothing on the code side.
```
