# Adapter Edge Cases & Failure Survivability

## Invariant
No valid payload from an external system can be silently dropped, and no dirty/invalid payload can crash the main event loop.

## Scenario: Silent Null Evaluation

**What could violate the invariant?**
A payload arrives with an unanticipated schema change, but the JSON DSL triggers a silent `null` evaluation instead of throwing an error, forwarding an empty command to the Ledger.

**What mechanism protects it?**
Strict Pydantic Validation bounds the output of the Adapter (`LedgerCommand` schema validation). If parsing yields partial outputs that don't satisfy the `LedgerCommand` schema, Python throws a `ValidationError` which the `AdapterWorker` traps and routes to the DLQ.

**Recovery:**
Because the original dirty payload is stored in `adapter_inbox` with `status=DLQ` alongside the error trace, an administrator can fix the `MappingContract` DSL, test it, and use the Replay API to push the identical payload through the fixed mapper. No data is lost.
