# Adapter Test Fixtures

Cleaned source-event payloads and their corresponding mapping contracts. Each fixture is trimmed to 2 line items — enough to test iteration and crosswalk logic without bloating context.

## Fixtures Index

| Fixture | Transaction Type | Node Resolution | Notes |
| --- | --- | --- | --- |
| `hf_receipt_902` | RECEIPT | `team` → MU node via crosswalk (PASS_THROUGH fallback) | Health facility receipt |
| `wh_stocktake_901` | STOCK_COUNT | `orgUnit` → node via crosswalk | Periodic warehouse stocktake |
| `wh_team_receipt_902` | RECEIPT | `invoice.team` → node via crosswalk | Warehouse team receipt (nested team field) |
| `wh_team_returns_904` | RETURN / ADJUSTMENT | `team` → node | Team returns to warehouse |

## Usage

These fixtures are designed for:
1. **Unit tests**: Validate the DSL engine processes each contract correctly
2. **Contract review tests**: `sample_in.json` + `expected_out.json` pattern per contract lifecycle
3. **AI context**: Minimal examples when working on adapter mapping logic
