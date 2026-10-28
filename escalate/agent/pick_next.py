"""Choose the next ladder step from the playbook: on_no_reply / on_refused / on_partial."""

from escalate.agent.judge_reply import Verdict
from escalate.playbooks.models import Playbook


def pick_next(pb: Playbook, step_id: str, verdict: Verdict, facts: dict[str, str]) -> str | None:
    """Next step id, or None when the case is resolved or the ladder has ended."""
    if verdict == "resolved":
        return None
    step = pb.step(step_id)
    if verdict == "no_reply":
        target = step.on_no_reply
    elif verdict == "partial":
        target = step.on_partial or step.on_refused
    else:
        target = step.on_refused
    seen: set[str] = set()
    # Skip steps whose `when` does not hold (e.g. no marketplace): follow their no-reply edge.
    while target and target not in seen:
        seen.add(target)
        nxt = pb.step(target)
        if nxt.applies(facts):
            return target
        target = nxt.on_no_reply
    return None
