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
            memory_block,
        ]
    )
