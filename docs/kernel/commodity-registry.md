# Commodity Registry

## Purpose

The Ledger must never be confused about what a "Unit" is. The Commodity Registry provides canonical item definitions.

## The Immutability Invariant

If the Ministry decides a "Box of Paracetamol" is now 50 tablets instead of 100, updating the multiplier on the existing Item ID is **catastrophic** — it would instantly recalculate every past STOCK_COUNT variance based on the new multiplier, ruining years of financial data.

### Golden Rule

**Base Units and Multipliers are Strictly Immutable.**

1. **Base Units Only:** The Event Store ONLY computes using the `base_unit`. It knows nothing about "Boxes."
2. **New Pack, New ID:** If packaging changes, create a *new* Package ID in the registry.

## Tables

### `kernel_commodity_registry` — Canonical Items

| Column | Type | Description |
| --- | --- | --- |
| `item_id` | String (PK) | Internal item identifier (e.g., `PARAM-01`) |
| `code` | String | Short code (e.g., `PRM-500`) |
| `name` | String | Human-readable name (e.g., Paracetamol 500mg) |
| `base_unit` | String | Smallest unit (e.g., `TABLET`) |
| `status` | String | `ACTIVE`, `DEPRECATED` |
| `created_at` | Timestamp | Record creation |
| `updated_at` | Timestamp | Last update |

### `commodity_packages` — UOM Conversions

**Used only by Clients/Adapters**, never by the Event Store.

| Column | Type | Description |
| --- | --- | --- |
| `package_id` | String (PK) | Package identifier (e.g., `PKG-100`) |
| `item_id` | String (FK) | Links to `kernel_commodity_registry` |
| `uom_name` | String | Package name (e.g., `BOX_100`) |
| `base_unit_multiplier` | Integer | Conversion factor (e.g., `100`) |
| `is_active` | Boolean | Whether this package is current |

### Example

| package_id | item_id | uom_name | multiplier | is_active |
| --- | --- | --- | --- | --- |
| `PKG-100` | `PARAM-01` | `BOX_100` | 100 | DEPRECATED |
| `PKG-050` | `PARAM-01` | `BOX_50` | 50 | ACTIVE |

## Related Docs

- **Adapter crosswalks:** The Adapter's `adapter_crosswalks` table maps external codes (e.g., `PARAM-BOX-200`) to these `item_id` values
- **Ledger math:** The Event Store only uses `item_id` + `base_unit`
