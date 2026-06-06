from dataclasses import dataclass


@dataclass(frozen=True)
class HonorCase:
    name: str
    report: str
    scripted_json: str
    expected_verdict: str


# Golden honor-verification cases: the model's scripted JSON is what a strict verifier
# *should* return; the harness asserts our parsing + routing produce that verdict.
HONOR_CASES: tuple[HonorCase, ...] = (
    HonorCase(
        name="detailed_pass",
        report="I made the bed: hospital corners, pillows squared, throw folded.",
        scripted_json='{"verdict": "pass", "confidence": 90, "reasoning": "specific", "issues": []}',
        expected_verdict="pass",
    ),
    HonorCase(
        name="vague_fail",
        report="yeah did it",
        scripted_json='{"verdict": "fail", "confidence": 25, "reasoning": "no specifics", "issues": ["vague"]}',  # noqa: E501
        expected_verdict="fail",
    ),
    HonorCase(
        name="evasive_reproof",
        report="mostly, will finish later",
        scripted_json='{"verdict": "re_proof", "confidence": 40, "reasoning": "incomplete", "issues": ["partial"]}',  # noqa: E501
        expected_verdict="re_proof",
    ),
    HonorCase(
        name="garbage_response_reproof",
        report="done",
        scripted_json="sure, looks fine to me",  # unparseable -> must become re_proof
        expected_verdict="re_proof",
    ),
)
