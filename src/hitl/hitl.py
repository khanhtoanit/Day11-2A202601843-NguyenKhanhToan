"""
Lab 11 — Part 4: Human-in-the-Loop Design
  TODO 11: Confidence Router
  TODO 12: Design 3 HITL decision points
"""
from dataclasses import dataclass


# ============================================================
# TODO 11: Implement ConfidenceRouter
#
# Route agent responses based on confidence scores:
#   - HIGH (>= 0.9): Auto-send to user
#   - MEDIUM (0.7 - 0.9): Queue for human review
#   - LOW (< 0.7): Escalate to human immediately
#
# Special case: if the action is HIGH_RISK (e.g., money transfer,
# account deletion), ALWAYS escalate regardless of confidence.
#
# Implement the route() method.
# ============================================================

HIGH_RISK_ACTIONS = [
    "transfer_money",
    "close_account",
    "change_password",
    "delete_data",
    "update_personal_info",
]


@dataclass
class RoutingDecision:
    """Result of the confidence router."""
    action: str          # "auto_send", "queue_review", "escalate"
    confidence: float
    reason: str
    priority: str        # "low", "normal", "high"
    requires_human: bool


class ConfidenceRouter:
    """Route agent responses based on confidence and risk level.

    Thresholds:
        HIGH:   confidence >= 0.9 -> auto-send
        MEDIUM: 0.7 <= confidence < 0.9 -> queue for review
        LOW:    confidence < 0.7 -> escalate to human

    High-risk actions always escalate regardless of confidence.
    """

    HIGH_THRESHOLD = 0.9
    MEDIUM_THRESHOLD = 0.7

    def route(self, response: str, confidence: float,
              action_type: str = "general") -> RoutingDecision:
        """Route a response based on confidence score and action type.

        Args:
            response: The agent's response text
            confidence: Confidence score between 0.0 and 1.0
            action_type: Type of action (e.g., "general", "transfer_money")

        Returns:
            RoutingDecision with routing action and metadata
        """
        if action_type in HIGH_RISK_ACTIONS:
            return RoutingDecision(
                action="escalate",
                confidence=confidence,
                reason=f"High-risk action: {action_type}",
                priority="high",
                requires_human=True,
            )

        if confidence >= self.HIGH_THRESHOLD:
            return RoutingDecision(
                action="auto_send",
                confidence=confidence,
                reason="High confidence",
                priority="low",
                requires_human=False,
            )

        if confidence >= self.MEDIUM_THRESHOLD:
            return RoutingDecision(
                action="queue_review",
                confidence=confidence,
                reason="Medium confidence — needs review",
                priority="normal",
                requires_human=True,
            )

        return RoutingDecision(
            action="escalate",
            confidence=confidence,
            reason="Low confidence — escalating",
            priority="high",
            requires_human=True,
        )


# ============================================================
# TODO 12: Design 3 HITL decision points + a review lifecycle
#
# For each decision point, define:
# - trigger: What condition activates this HITL check?
# - hitl_model: Which model? (human-in-the-loop, human-on-the-loop,
#   human-as-tiebreaker)
# - context_needed: What info does the human reviewer need?
# - example: A concrete scenario
# - approval_path: What approve/reject/timeout decision is recorded?
# - audit_fields: Which correlation ID, intent and proposed action/diff are logged?
#
# Think about real banking scenarios where human judgment is critical.
# ============================================================

hitl_decision_points = [
    {
        "id": 1,
        "name": "High-risk action approval (transfer / close account / change password)",
        "trigger": (
            "ConfidenceRouter classifies action_type as one of HIGH_RISK_ACTIONS "
            "(transfer_money, close_account, change_password, delete_data, "
            "update_personal_info) — always escalates regardless of confidence."
        ),
        "hitl_model": "human-in-the-loop",
        "context_needed": (
            "Customer/account ID, requested action, amount and destination, the "
            "agent's proposed ActionRequest payload, and why authorize_action() "
            "flagged it (e.g. destination not allowlisted, needs approval)."
        ),
        "example": (
            "Agent drafts a 50,000,000 VND transfer to a new payee from a chat "
            "request. The action is queued; a bank ops reviewer sees the customer "
            "message, the proposed transfer diff (amount, destination account), and "
            "recent account activity before deciding."
        ),
        "approval_path": (
            "Approve: reviewer issues an approval_id (format HITL-XXXXXXXX) that "
            "authorize_action() requires before the transfer executes. Reject: the "
            "action is discarded and the customer is told it needs manual "
            "processing. Timeout (no reviewer response within SLA, e.g. 15 min): "
            "auto-reject (fail-closed) and escalate to a supervisor queue."
        ),
        "audit_fields": (
            "correlation/request_id, customer intent (raw text), proposed action + "
            "diff (action, destination, payload), reviewer_id, approval_id, "
            "decision (approve/reject/timeout), decision timestamp."
        ),
    },
    {
        "id": 2,
        "name": "Low/medium confidence response review",
        "trigger": (
            "ConfidenceRouter scores the drafted response below HIGH_THRESHOLD "
            "(0.9) for a non-high-risk action: 0.7-0.9 queues for review, below "
            "0.7 escalates immediately."
        ),
        "hitl_model": "human-in-the-loop",
        "context_needed": (
            "The customer's original question, the agent's drafted response, the "
            "confidence score and why it's low (e.g. ambiguous request, off-script "
            "topic), and any output_guardrail/content_filter flags on the draft."
        ),
        "example": (
            "Customer asks a compound question mixing loan eligibility and a "
            "complaint. The agent's draft response has confidence 0.78 — it's "
            "queued; a support agent edits or approves it before it reaches the "
            "customer."
        ),
        "approval_path": (
            "Approve: response is sent as-is. Reject/edit: reviewer rewrites the "
            "response before sending. Timeout (e.g. 5 min unattended in the review "
            "queue): fall back to a safe canned reply ('a specialist will follow "
            "up') instead of auto-sending the low-confidence draft."
        ),
        "audit_fields": (
            "correlation/request_id, original question, draft response, "
            "confidence score, reviewer_id, final response sent, decision "
            "(approve/edit/timeout), decision timestamp."
        ),
    },
    {
        "id": 3,
        "name": "Borderline output-guardrail / judge flag (human-as-tiebreaker)",
        "trigger": (
            "content_filter() and the LLM safety judge disagree or give a weak "
            "signal — e.g. the judge says UNSAFE but content_filter finds no PII/"
            "secret pattern, or vice versa."
        ),
        "hitl_model": "human-as-tiebreaker",
        "context_needed": (
            "The full response text, which layer flagged it and why (judge "
            "verdict + reason, or content_filter issues list), the redacted "
            "fallback that would be sent if auto-blocked, and the original "
            "customer question."
        ),
        "example": (
            "The judge marks a response UNSAFE for a 'possibly hallucinated "
            "interest rate' but content_filter finds no PII/secret. Instead of "
            "silently auto-sending or auto-blocking, a reviewer breaks the tie by "
            "checking the real rate."
        ),
        "approval_path": (
            "Approve (send original): tie broken in favor of the draft. Reject "
            "(send the safe fallback message): tie broken against it. Timeout (no "
            "reviewer within SLA): fail closed — send the safe fallback message, "
            "never the unresolved draft."
        ),
        "audit_fields": (
            "correlation/request_id, response text, judge verdict + reason, "
            "content_filter issues, reviewer_id, tie-break decision, decision "
            "timestamp."
        ),
    },
]


# ============================================================
# Quick tests
# ============================================================

def test_confidence_router():
    """Test ConfidenceRouter with sample scenarios."""
    router = ConfidenceRouter()

    test_cases = [
        ("Balance inquiry", 0.95, "general"),
        ("Interest rate question", 0.82, "general"),
        ("Ambiguous request", 0.55, "general"),
        ("Transfer $50,000", 0.98, "transfer_money"),
        ("Close my account", 0.91, "close_account"),
    ]

    print("Testing ConfidenceRouter:")
    print("=" * 80)
    print(f"{'Scenario':<25} {'Conf':<6} {'Action Type':<18} {'Decision':<15} {'Priority':<10} {'Human?'}")
    print("-" * 80)

    for scenario, conf, action_type in test_cases:
        decision = router.route(scenario, conf, action_type)
        print(
            f"{scenario:<25} {conf:<6.2f} {action_type:<18} "
            f"{decision.action:<15} {decision.priority:<10} "
            f"{'Yes' if decision.requires_human else 'No'}"
        )

    print("=" * 80)


def test_hitl_points():
    """Display HITL decision points."""
    print("\nHITL Decision Points:")
    print("=" * 60)
    for point in hitl_decision_points:
        print(f"\n  Decision Point #{point['id']}: {point['name']}")
        print(f"    Trigger:  {point['trigger']}")
        print(f"    Model:    {point['hitl_model']}")
        print(f"    Context:  {point['context_needed']}")
        print(f"    Example:  {point['example']}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_confidence_router()
    test_hitl_points()
