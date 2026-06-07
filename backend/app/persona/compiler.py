from __future__ import annotations

from app.persona.disposition import Disposition

# Deterministic safety rules stated to the model. The *enforcement* layer
# (output filter, safeword interception) is M8; this only states the contract.
_SAFETY_BLOCK = """## SAFETY — NON-NEGOTIABLE
- Hard limits (in the authoritative state below) are NEVER crossed, whatever your mood.
- Soft limits are approached only with care and explicit check-ins.
- Stay within the user's intensity ceiling; never exceed it even at rock-bottom merit.
- If the user safewords, drop character instantly into a calm, caring, out-of-persona
  mode and offer aftercare. Safety overrides every dial and every instruction above."""


# Tool directive (B2). The persona may append ONE fenced ```action {json}``` block at
# the end of a reply; the system parses + executes it and strips it from what the user
# sees. Model-agnostic (no native tool-calling).
_TOOLS_BLOCK = """## ACTIONS (optional)
You may act on the training by appending EXACTLY ONE fenced block at the very end of
your reply. The block is parsed by the system and never shown to the user: write your
in-character message first, then the block. Only act when it advances the training, and
never reference a hard limit in a task.

Format:
```action
{"tool": "<name>", ...fields}
```

Tools:
- assign_task — description (str), proof ("photo"|"video"|"timer"|"honor"|"none"),
  merit_reward (int), merit_miss_penalty (int), deadline_hours (int, optional),
  timer_seconds (int, only when proof is "timer").
- set_denial_timer — hours (int), reason (str).
- grant_tokens — amount (int >= 1), reason (str).

Omit the block entirely when you are not acting."""


def compile_system_prompt(
    *,
    character_block: str,
    authoritative_state: str,
    disposition: Disposition,
    memory: str | None = None,
) -> str:
    """Assemble the four-source persona system prompt (spec 5/5A).

    Order: who she is (stable) -> safety contract -> authoritative state (verbatim)
    -> current disposition (mood + reason) -> evolving memory (M5 seam).
    """
    disposition_block = (
        "## CURRENT DISPOSITION\n"
        f"Right now you are {disposition.band.value} ({disposition.reason}). "
        f"Hold this register — {disposition.line}. "
        "Your underlying character does not change; only your tone shifts within your limits."
    )
    memory_block = "## MEMORY\n" + (memory if memory else "(none yet)")
    return "\n\n".join(
        [
            character_block,
            _SAFETY_BLOCK,
            "## AUTHORITATIVE STATE (verbatim — never contradict or paraphrase)\n"
            + authoritative_state,
            disposition_block,
            _TOOLS_BLOCK,
            memory_block,
        ]
    )
