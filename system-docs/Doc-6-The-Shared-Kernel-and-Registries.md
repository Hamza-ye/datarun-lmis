# Area F: The Shared Kernel (Registries & Truth)

The "Shared Kernel" is the central nervous system of the Modular Monolith. It provides the immutable definitions and registries used by the Ledger's sub-modules (Areas B, C, D, E). Because the Ledger relies on strict mathematical rules, the definitions it uses must be unambiguous and historically accurate.

---

## 1. The Supply Node Registry (Topology)

Nodes represent any physical or logical location capable of holding stock (National Warehouses, Clinics, Mobile Teams).

### The "Gotcha": Slowly Changing Dimensions (SCD Type 2)
In the real world, a "Clinic" might move from "District A" to "District B." If we simply `UPDATE` the clinic's `parent_id` in the database, **we corrupt history**. A report run for last year will suddenly show all the clinic's consumption happening in District B, which is mathematically false.

To prevent this, the Ledger models Nodes using **Slowly Changing Dimensions (Type 2)** by tracking the **validity period** of a relationship.

```markdown
**Table Schema Concept:** `nodes`
| `id` (ULID) | `uid` (11 char) | `code` | `name` | `node_type` | `parent_id` | `valid_from` | `valid_to` | `meta` (jsonb) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `01H...V3` | `CLX12345678` | `CX-01` | `Clinic X` | `HF` | `01H...A1` | `2020-01-01` | `2026-03-01` | `{}` |
| `01J...M4` | `CLX12345678` | `CX-01` | `Clinic X` | `HF` | `01H...B2` | `2026-03-01` | `NULL` | `{}` |
```

**Rule:** When Area E evaluates the Approval Policy for a transaction that occurred on `2025-06-15`, it joins against `node_hierarchy` where `'2025-06-15' BETWEEN valid_from AND valid_to`. This guarantees temporal accuracy.

---

## 2. The Commodity Registry (Immutability Invariant)

The Ledger must never be confused about what a "Unit" is.

### The "Gotcha": Changing Packaging
If the Ministry decides a "Box of Paracetamol" is now 50 tablets instead of 100, updating the multiplier on the existing Item ID is **catastrophic**. It will instantly recalculate every past `STOCK_COUNT` variance based on the new multiplier, ruining years of financial data.

**The Golden Rule of the Kernel:** Base Units and Multipliers are **Strictly Immutable**.

1. **Base Units Only:** The Ledger (Area C) ONLY computes using the `base_unit`. It knows nothing about "Boxes."
2. **New Pack, New ID:** If the packaging changes, you must create a *new* Commodity ID or a new Package ID in the registry. 

**Table Schema Concept:** `commodity_registry`
| `item_id` | `name` | `base_unit` | `status` |
| --- | --- | --- | --- |
| `PARAM-01` | Paracetamol 500mg | `TABLET` | `ACTIVE` |

**Table Schema Concept:** `commodity_packages` (Only used by Clients/Adapters, never by Area C)
| `package_id` | `item_id` | `uom_name` | `base_unit_multiplier` | `is_active` |
| --- | --- | --- | --- | --- |
| `PKG-100` | `PARAM-01` | `BOX_100` | `100` | `DEPRECATED` |
| `PKG-050` | `PARAM-01` | `BOX_50` | `50` | `ACTIVE` |

---

## 3. The Policy Engine (Configuration as Data)

Area B, D, and E rely on business rules that change over time. These rules shouldn't be hardcoded into the Python logic.

**Table Schema Concept:** `system_policies`
| `policy_key` | `applies_to_node` | `applies_to_item` | `config_json` |
| --- | --- | --- | --- |
| `approval_required` | `GLOBAL` | `ALL` | `{"transaction_types": ["ADJUSTMENT"], "threshold_usd": 500}` |
| `auto_receive_days` | `WH_KAMPALA` | `ALL` | `{"days": 14}` |
| `negative_stock` | `GLOBAL` | `ALL` | `{"behavior": "BLOCK"}` |

### Resolution Hierarchy
When a module queries a policy, the Kernel executes a Fallback chain:
1. Is there a specific policy for this `item_id` at this `node_id`?
2. If no, is there a policy for *any* item at this `node_id`?
3. If no, is there a policy for this `item_id` at the `parent_node_id`?
4. If no, use the `GLOBAL` default.
