# Ledger Edge Cases & Failure Survivability

## 1. Idempotency Guard — Duplicate Submission Storm

**Invariant:** A business event must be applied to the ledger exactly once, regardless of network retries or concurrent identical submissions.

**Scenario:** A field worker submits a "Deduct 50 Paracetamol" form. Connection drops before the 201 response, so the app retries three times in rapid succession.

**Protection:** The `source_event_id` is a strictly enforced `UNIQUE` constraint. Concurrent bursts hit lock contention; the first thread writes the key, subsequent threads bounce off an `IntegrityError` and are returned the cached `COMMITTED` status without affecting balances.

**Recovery:** If a client re-uses an old ID for a brand-new transaction (client-side bug), the system rejects it as a duplicate. The client must generate a new UUID. The Ledger's integrity is never compromised.

---

## 2. Approval Gatekeeper — Policy Drift

**Invariant:** Transactions flagged for approval must never alter the balance sheet until explicitly resolved by an authorized actor.

**Scenario:** A transaction is parked in `ledger_staged_commands`. While it sits there, the Global Policy is changed so that transaction type *no longer requires* approval.

**Protection:** Policy definitions are evaluated at the moment of *ingestion*, not resolution. The transaction remains `STAGED`. When the supervisor clicks "Approve," the `GatekeeperService` validates the actor's RBAC against the *current* state of the Shared Kernel, ensuring the actor still has jurisdiction.

**Recovery:** If a transaction is accidentally approved, it flushes into the Event Store. To correct it, the system requires a symmetrical `REVERSAL` linked to the offending `source_event_id`. History shows: Staged → Approved → Reversal applied.

---

## 3. Event Store — Concurrent Balance Corruption

**Invariant:** The event log must be append-only and immutable. `SUM(events)` must always equal `stock_balance`.

**Scenario:** Two concurrent workers process dispatches from the same warehouse simultaneously. Both read balance = 100, do math in memory, and write back — the final balance is corrupted.

**Protection:** **Optimistic Concurrency Control (OCC)** using the `version` column. Worker A reads `version=5`, writes `version=6`. Worker B reads `version=5`, tries to write `version=6` — fails with `StaleDataError`. Worker B re-reads (balance now 40), realizes it cannot deduct 50, rejects for Insufficient Stock.

**Recovery:** If a bug allowed a negative balance, we append a corrective `ADJUSTMENT` event to restore a known-good state, documenting the reason in metadata. Never `UPDATE` a past event.

---

## 4. In-Transit Registry — Double Receipt / Lost Shipment

**Invariant:** Goods dispatched must exactly equal goods received + goods lost. A shipment cannot be received twice.

**Scenario (Double Receipt):** The receiving facility clicks "Receive Delivery" twice due to lag.

**Protection:** The `transfer_id` acts as the idempotency guard. The state machine strictly enforces `OPEN` → `COMPLETED`. The second click bounces because the status is no longer `OPEN`.

**Scenario (Lost Shipment):** A truck crashes and goods are destroyed. The ledger remains indefinitely in `OPEN` limbo.

**Recovery:** A supervisor submits an `UPDATE_IN_TRANSIT_STATUS` command with `status: LOST_IN_TRANSIT`. The system generates an `ADJUSTMENT` event (negative) at the source node with `adjustment_reason: LOSS_IN_TRANSIT`. The write-off is gated by `policy.transfer.loss_writeoff_requires_approval`. See [In-Transit Registry → Loss Write-Off](in-transit-registry.md#loss-write-off-lost_in_transit).
