# Kernel Edge Cases & Failure Survivability

## Invariant
Configuration changes must not alter historical facts.

## Scenario: Topology Drift (Node Reassignment)

**What could violate the invariant?**
On July 1st, Clinic A is moved from District 1 to District 2. An analyst runs a report for June consumption. The report attributes all of Clinic A's June consumption to District 2 — this is mathematically and historically false.

**Protection:**
**Slowly Changing Dimensions (SCD Type 2)**. When Clinic A's parent changes, the `kernel_node_registry` row for District 1 is capped (`valid_to = '2026-06-30'`), and a *new* row is created for Clinic A linked to District 2 (`valid_from = '2026-07-01'`). Read models use temporal SQL joins: `occurred_at BETWEEN valid_from AND valid_to`.

**Recovery:**
If an admin typos a hierarchy change, they can fix it with a new `PUT` that creates another split. If they need to edit the *past* date (e.g., "We moved it June 1st but forgot until July 1st"), this is an edge case.

> **Risk Flag:** The current system API only sets `valid_from = today()`. We will need an Administrative "Historical Topology Correction" API or DBA script to safely alter `valid_from / valid_to` bounds for late-reported hierarchy changes.
