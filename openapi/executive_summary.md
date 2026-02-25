# Executive Summary: API Freeze Discrepancies

The following 5 items require resolution to complete the API Freeze and unblock Angular UI development:

1. **Missing In-Transit API:** Need `GET /api/ledger/transfers` to list pending incoming/outgoing transfers for a node.
2. **Missing Receive Transfer API:** Need `POST /api/ledger/transfers/{id}/receive` for the UI to acknowledge and verify dispatched stock.
3. **Missing Gatekeeper Inbox API:** Need `GET /api/ledger/gatekeeper/staged` for Supervisors to view transactions awaiting approval.
4. **Missing DLQ Retry API:** Need `POST /api/adapter/admin/dlq/{id}/retry` so users can reprocess failed payloads after fixing mappings.
5. **Untyped Gatekeeper Action:** The `/api/ledger/gatekeeper/{id}/resolve` endpoint request body lacks a strict Pydantic schema in OpenAPI, appearing as a generic object.
