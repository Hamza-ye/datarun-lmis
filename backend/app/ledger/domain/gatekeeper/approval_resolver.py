from app.ledger.schemas.command import LedgerCommand


class ApprovalResolver:
    @staticmethod
    def requires_approval(command: LedgerCommand, active_policies: dict) -> tuple[bool, str]:
        """
        Determines if a command needs to go to the Gatekeeper Staging Area.
        Returns (NeedsApproval, ReasonString)
        """
        # 1. Check if Transaction Type Requires Approval
        required_types = active_policies.get("policy.approval.required_on", [])
        if command.transaction_type.value not in required_types:
            return False, ""
            
        # 2. Check Auto-Approve Threshold
        threshold = active_policies.get("policy.approval.auto_approve_threshold")
        if threshold is not None:
            if abs(command.quantity) <= threshold:
                return False, f"Auto-approved. Variance {abs(command.quantity)} <= {threshold}"
                
        return True, f"Policy requires approval for {command.transaction_type.value} exceeding thresholds."
