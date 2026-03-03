# Adapter Edge Cases & Failure Survivability

## Invariant
No valid payload from an external system can be silently dropped, and no dirty/invalid payload can crash the main event loop.

## Scenario 1: Silent Null Evaluation (Upstream Schema Change)

**What could violate the invariant?**
A source system changes their payload schema (e.g., renames `quantity` to `amount`). The JSON DSL path `$.items[*].quantity` silently evaluates to `null` instead of throwing an error.

**What mechanism protects it?**
Two layers of defense:

1. **Output Validation (Current):** Strict Pydantic Validation bounds the output (`LedgerCommand` schema). If parsing yields partial outputs, Python throws a `ValidationError` which the `AdapterWorker` traps and routes to the DLQ.
2. **Null-Path Detection (Recommended Enhancement):** Before output validation, the DSL engine should check if any `required` output_template path resolved to `null`. If so, the error should explicitly name the broken path (e.g., `"Path $.items[*].quantity resolved to null"`) rather than failing at Pydantic validation with a generic `"quantity is required"` message.

**Recovery:**
Because the original dirty payload is stored in `adapter_inbox` with `status=DLQ` alongside the error trace, an administrator can inspect the source payload, identify the schema change, update the DSL contract, test it, and replay. No data is lost.

## Scenario 2: Multi-Command Partial Failure

**What could violate the invariant?**
A single incoming payload produces multiple Ledger commands (e.g., a form with both receipts and issues). The mapping phase succeeds for all commands, but during forwarding, command 2 of 5 is rejected by the Ledger (HTTP 400) while 1, 3, 4, 5 succeed.

**What mechanism protects it?**
The multi-command atomicity model (see [Mapping DSL → Multi-Command Output](mapping-dsl-reference.md#multi-command-output-one-payload--multiple-commands)):

1. Each command carries a **deterministic `source_event_id`** derived from `{payload_id}:{template_index}:{iterator_index}`.
2. The `adapter_egress_logs` records the outcome of **each** forwarding attempt individually.
3. The `adapter_inbox` status reflects the worst outcome (e.g., `DESTINATION_REJECTED` if any command was rejected).
4. On replay, **all** commands are regenerated with the same `source_event_id` values. The Ledger's idempotency guard deduplicates the 4 already-committed commands. Only the previously-rejected command is re-attempted.

**Recovery:**
Admin fixes the issue (e.g., the rejected command had invalid data), replays the entire payload. The 4 successful commands are harmlessly deduplicated. The fixed command processes normally. No double-counting.

## Scenario 3: Crosswalk Staleness

**What could violate the invariant?**
A clinic closes in the Shared Kernel, but the crosswalk still maps submissions to its `node_id`. New submissions arrive and get forwarded with a deactivated node.

**What mechanism protects it?**
Crosswalk entries support `is_active = FALSE` (see [Database Schema → adapter_crosswalks](database-schema.md)). Deactivated entries are treated as unmapped — the dictionary's `on_unmapped` strategy applies. The Ledger also validates `node_id` against the Shared Kernel at commit time as a second line of defense.

**Recovery:**
Admin deactivates the crosswalk entry. Payloads that were already forwarded with the stale mapping need a Ledger-side REVERSAL if the node is truly invalid.

## Related Docs

- **DLQ & Replay:** [DLQ and Replay](dlq-and-replay.md)
- **Multi-command output:** [Mapping DSL Reference](mapping-dsl-reference.md#multi-command-output-one-payload--multiple-commands)
- **Crosswalk schema:** [Database Schema](database-schema.md)
