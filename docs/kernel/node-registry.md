# Node Registry (Supply Node Topology)

## Purpose

Nodes represent any physical or logical location capable of holding stock: National Warehouses, Clinics, Mobile Teams.

## Node Types

| Type Code | Description |
| --- | --- |
| `WH` | Warehouse |
| `HF` | Health Facility |
| `MU` | Mobile Unit |
| `TEAM` | Mobile teams during periodic campaigns |
| `MOBILE_WH` | Temporary warehouses during campaigns |

## The SCD Type 2 Problem

In the real world, a Clinic might move from District A to District B. If we simply `UPDATE` the clinic's `parent_id`, **we corrupt history** — a report for last year would show all consumption in District B, which is false.

### Solution: Slowly Changing Dimensions (Type 2)

Track the **validity period** of each relationship:

**Table:** `kernel_node_registry`

| Column | Type | Description |
| --- | --- | --- |
| `id` | UUID (PK) | Internal row ID |
| `uid` | String | Stable external identifier (e.g., `CLX1234`) |
| `code` | String | Short code |
| `name` | String | Human-readable name |
| `node_type` | String | `WH`, `HF`, `MU`, `TEAM`, `MOBILE_WH` |
| `parent_id` | UUID (FK) | Parent node |
| `valid_from` | Date | Start of this relationship |
| `valid_to` | Date (nullable) | End of this relationship (NULL = current) |
| `meta_data` | JSONB | Arbitrary metadata |
| `created_at` | Timestamp | Row creation |
| `updated_at` | Timestamp | Last update |

### Example

| uid | node_type | parent_id | valid_from | valid_to |
| --- | --- | --- | --- | --- |
| `CLX1234` | `HF` | `DIST-A` | 2020-01-01 | 2026-03-01 |
| `CLX1234` | `HF` | `DIST-B` | 2026-03-01 | NULL |

### Temporal Query Rule

When evaluating policies for a transaction that occurred on `2025-06-15`, join against the node registry where `'2025-06-15' BETWEEN valid_from AND valid_to`. This guarantees temporal accuracy.

## Related Docs

- **Policy resolution using nodes:** See [Policy Engine](policy-engine.md)
- **Edge case — topology drift:** See [Kernel Edge Cases](edge-cases.md)
