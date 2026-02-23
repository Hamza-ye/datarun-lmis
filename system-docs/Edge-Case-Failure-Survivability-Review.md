# Edge Case & Failure Survivability Review

This document explores the domain survivability of the Modular Monolith under extreme duress, configuration drift, temporal edge cases, and concurrency faults. We are prioritizing "Model Survivability" over speed. 

The core premise: **Can every business error be corrected without deleting history?**

---

## 1. Adapter & Dead Letter Queue (DLQ)
**What invariant must never break?**
No valid payload from an external system can be silently dropped, and no dirty/invalid payload can crash the main event loop.
**What event could violate it?** 
A payload arrives with an unanticipated schema change, but the JSON DSL triggers a silent `null` evaluation instead of throwing an error, forwarding an empty command to the Ledger.
**What mechanism protects it?** 
Strict Pydantic Validation bounds the output of the Adapter (`LedgerCommand` schema validation). If parsing yields partial outputs that don't satisfy the LedgerCommand schema, Python throws a `ValidationError` which the `AdapterWorker` traps and routes to the DLQ.
**How would we recover if it broke?**
Because the original dirty payload is stored in `adapter_inbox` with `status=ERROR` alongside the DLQ trace, an administrator can fix the `MappingContract` DSL, test it, and use the Replay API to push the identical payload through the fixed mapper. No data is lost.

---

## 2. Idempotency Guard (Area B)
**What invariant must never break?**
A business event must be applied to the ledger exactly once, regardless of network retries, duplicated queues, or concurrent identical submissions.
**What event could violate it?**
A field worker submits a "Deduct 50 Paracetamol" form. Their connection drops before getting the 201 response, so their app retries it three times in rapid succession.
**What mechanism protects it?**
The `source_event_id` is a strictly enforced `UNIQUE` constraint in `ledger_idempotency_registry`. Concurrent bursts will hit SQLite/Postgres lock contention; the first thread writes the key, subsequent threads bounce off an `IntegrityError` and are returned the initial cached `COMMITTED` status without affecting balances.
**How would we recover if it broke?**
If a client *re-uses* an old ID for a brand new transaction (a client-side bug), the system rejects it as a duplicate. To recover, the client system must be instructed to generate a new UUID for the new transaction. The Ledger's integrity is never compromised.

---

## 3. Approval Gatekeeper (Area E)
**What invariant must never break?**
Transactions flagged for approval must never alter the balance sheet until explicitly resolved by an authorized actor.
**What event could violate it?**
A transaction requiring approval is parked in `ledger_staged_commands`. While it sits there, the Global Policy is changed so that transaction type *no longer requires* approval. 
**What mechanism protects it?**
Policy definitions are evaluated at the moment of *ingestion*, not resolution. The transaction remains STAGED. When the supervisor clicks "Approve", the `GatekeeperService` validates the actor's RBAC against the *current* state of the Shared Kernel definitions, ensuring the actor still has jurisdiction over the target facility.
**How would we recover if it broke?**
If a transaction is accidentally approved (e.g. by a malicious actor), it flushes into the Immutable Event Store. To correct it, the system requires a symmetrical `REVERSAL` transaction linked to the offending `source_event_id`. History shows: Staged -> Approved -> Reversal applied. Perfect audit trail.

---

## 4. Immutable Event Store & Balances (Area C)
**What invariant must never break?**
The event log must be append-only and immutable. `SUM(events)` must always equal `stock_balance`.
**What event could violate it?**
Two concurrent workers try to process dispatches from the same warehouse at the exact same millisecond. The balance is 100. Worker A deducts 60. Worker B deducts 50. Both read the balance as 100, do the math in memory, and write back, leaving the final balance corrupted or negative without justification.
**What mechanism protects it?**
**Optimistic Concurrency Control (OCC)** using the `version` column. 
- Worker A reads `balance=100, version=5`. Writes `balance=40, version=6`.
- Worker B reads `balance=100, version=5`. Tries to write `balance=50, version=6`.
Worker B's transaction throws a `StaleDataError` (Integrity Exception). Worker B catches this, re-reads the balance (now 40), realizes it cannot deduct 50, and rejects the transaction for Insufficient Stock.
**How would we recover if it broke?**
If a bug allowed a negative balance, we cannot `UPDATE` the past event. We must append a new `ADJUSTMENT` event to force the balance back to a known good state, documenting the reason in the `metadata`.

---

## 5. Shared Kernel & Topology (Area F)
**What invariant must never break?**
Configuration changes must not alter historical facts.
**What event could violate it?**
On July 1st, Clinic A is moved from District 1 to District 2. An analyst runs a report for June consumption. The report attributes all of Clinic A's June consumption to District 2. This is mathematically and historically false.
**What mechanism protects it?**
**Slowly Changing Dimensions (SCD Type 2)**. When Clinic A's parent changes, the `NodeRegistry` row for District 1 is capped (`valid_to = '2026-06-30'`), and a *new* row is created for Clinic A linked to District 2 (`valid_from = '2026-07-01'`). Read models use temporal SQL joins: `occurred_at BETWEEN valid_from AND valid_to`.
**How would we recover if it broke?**
If an admin typos a hierarchy change that breaks future mapping, they can fix it with a new `PUT` that creates another split. If they need to edit the *past* date (e.g. "We moved it on June 1st but forgot to update the system until July 1st"), this is an **edge case risk**. The current system API only sets `valid_from = today()`. 
**Risk Flag:** We will need an Administrative "Historical Topology Correction" API or DBA script to safely alter `valid_from / valid_to` bounds for late-reported hierarchy changes.

---

## 6. In-Transit Registry (Area D)
**What invariant must never break?**
Goods dispatched must exactly equal goods received + goods lost. A shipment cannot be received twice.
**What event could violate it?**
The receiving facility clicks "Receive Delivery" twice due to lag.
**What mechanism protects it?**
The `transfer_id` acts as the idempotency guard for the Receipt flow. The `InTransitRegistry` state machine strictly enforces `DISPATCHED` -> `RECEIVED`. The second click will bounce because the status is no longer `DISPATCHED`.
**How would we recover if it broke?**
A truck crashes and the goods are destroyed. The ledger remains indefinitely in `DISPATCHED` limbo.
**Risk Flag:** We must explicitly model an `UPDATE_IN_TRANSIT_STATUS` command allowing supervisors to mark a transfer as `LOST_IN_TRANSIT`, which would trigger a write to the `InventoryEvent` store recording a write-off from the source facility.
