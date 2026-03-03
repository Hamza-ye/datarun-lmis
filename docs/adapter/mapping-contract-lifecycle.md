# Mapping Contract Lifecycle

## Statuses

| Status | Description |
| --- | --- |
| `DRAFT` | Editable. No live traffic. Test-only. |
| `REVIEW` | Submitted for review. `sample_in.json` and `expected_out.json` required. |
| `APPROVED` | Review passed. Mapping test succeeded. Ready for activation. |
| `ACTIVE` | Processing live traffic. **Locked — no edits.** |
| `DEPRECATED` | Retired from new processing. Still valid for replay. Set `visible_in_ui = FALSE` to hide from active UI while preserving audit history. |
| `REJECTED` | Review failed. Rejection reason recorded. |

## Transitions & Guards

### DRAFT → REVIEW
- `sample_in.json` and `expected_out.json` must exist.

### REVIEW → APPROVED
- Mapping test (sample → expected) must pass.
- Test result metadata stored for this version.

### REVIEW → REJECTED
- Rejection reason must be recorded.

### APPROVED → ACTIVE (The "Atomic Flip")
- Only **one** `ACTIVE` version per contract `id`.
- Activation is atomic:
  1. Check if any previous version is `ACTIVE`.
  2. Set previous version to `DEPRECATED`.
  3. Set new version to `ACTIVE`.
  4. Log the transition.

### ACTIVE → DEPRECATED
- Deprecated versions are not used for new processing.
- Deprecated versions remain valid for replay.
- Set `visible_in_ui = FALSE` to remove from active UI while preserving audit history.

> **Design Note:** The former `ARCHIVED` status has been collapsed into `DEPRECATED` with a `visible_in_ui` flag. Status enums are domain vocabulary; UI visibility is a presentation concern. Keeping them separate avoids coupling the domain model to the UI layer.

## Rollback

Rollback is performed by activating a previous `APPROVED` or `DEPRECATED` version.

**Rules:**
- Rollback is an atomic `ACTIVE` switch.
- No data mutation occurs.
- Previously processed events are NOT reprocessed automatically.

## Editing Rule

> **Never allow editing of an `ACTIVE` version.** If you need a change, **Clone to DRAFT**, edit, and re-activate. This ensures that if you look at a log from 3 months ago, you can see exactly which mapping rules were in place at that moment.

## Versioning Rule

Every mapping contract must be versioned and include `sample_in.json` and `expected_out.json` tests.

## Related Docs

- **DSL schema:** See [Mapping DSL Reference](mapping-dsl-reference.md)
- **DB table:** See [Database Schema](database-schema.md) for `mapping_contracts`
- **Replay:** See [DLQ and Replay](dlq-and-replay.md) for replay-specific lifecycle rules
