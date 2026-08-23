from __future__ import annotations

from fastapi import HTTPException
from .models import Principal


def require_internal(principal: Principal) -> None:
    if principal.role not in {"support_agent", "ops_manager"}:
        raise HTTPException(403, "This workflow is available only to authorised ParcelPilot staff.")


def check_account_scope(principal: Principal, account_id: str) -> None:
    """Enforcement is intentionally here, at the data-tool boundary.

    A customer session is allowed exactly one account. Internal support can read all
    accounts in this assessment; production would add per-region/team entitlements.
    """
    if principal.role == "customer" and principal.account_id != account_id:
        raise HTTPException(403, "Account scope violation: cross-account data is not available.")
