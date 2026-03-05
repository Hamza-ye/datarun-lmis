# Headless Form Engine — Contract & Design

> **Status:** Source of Truth  
> **Last updated:** 2026-03-05  
> **Audience:** Frontend developer building the Data Capture module

---

## 1. What the Form Engine Is

The Form Engine is a **headless** (no-UI) TypeScript library that:

1. **Holds form state** — `values` (flat singletons) + `collections` (identity-keyed repeater rows)
2. **Evaluates behavior rules** — visibility, required, disabled per field, using namespace resolvers
3. **Manages collection rows** — add/remove with stable ULIDs, `_parent_id` for nested repeaters
4. **Assembles V2 submissions** — produces the normalized payload ready for POST

The engine has **no Angular imports, no HTTP calls, no DOM access**. Angular components interact with it through its public API and observe changes via Signals or RxJS.

### What It Does NOT Do

| Not Its Job | Why | Who Does It |
|---|---|---|
| Render UI | Rendering is the Presentation layer's job | Angular components in `features/data-capture/components/` |
| Make HTTP calls | Network is the Infrastructure layer's job | `SubmissionService` / `TemplateApiClient` |
| Store data to IndexedDB | Persistence is Infrastructure | Future `OfflinePersistenceAdapter` |
| Transform legacy templates | Backend concern | DatarunAPI's Template Transformer (HashMap Registry) |

---

## 2. V2 Data Shapes (What the Engine Manages)

### 2.1 Submission State

The engine's internal state mirrors the V2 submission contract:

```typescript
interface V2Submission {
  submission_uid: string;
  template_uid: string;
  version_number: number;
  values: Record<string, unknown>;          // flat singletons
  collections: Record<string, CollectionMap>; // identity-keyed repeater rows
}

type CollectionMap = Record<string, CollectionRow>;

interface CollectionRow {
  _parent_id?: string;   // set only for nested repeaters
  _index?: number;       // optional, UI sort hint only
  [fieldBinding: string]: unknown;
}
```

**Example:**

```json
{
  "submission_uid": "z3Ye07TDj7a",
  "template_uid": "ck2pHW93sk2",
  "version_number": 2,
  "values": {
    "visitdate": "2025-09-27",
    "gender": "MALE",
    "PatientName": "محمد فيصل كامل مشعل"
  },
  "collections": {
    "medicines": {
      "01K693VTPPWQR1M23AN06B6N0D": {
        "_index": 1,
        "amd": "act40_tape",
        "prescribed_quantity": 1
      }
    }
  }
}
```

### 2.2 Template Tree (What the Engine Receives)

The backend's V2 template endpoint returns a tree of nodes:

```typescript
interface TemplateTree {
  node_id: string;         // "root" for the top level
  children: TreeNode[];
}

interface TreeNode {
  node_id: string;         // unique within the tree
  type: NodeType;          // determines UI widget
  binding: string;         // key in `values` or `collections`
  label?: Record<string, string>;  // localized labels
  mandatory?: boolean;
  option_set?: string;     // UID of the option set
  rules?: Rule[];          // behavior rules
  validation?: ValidationRule;
  children?: TreeNode[];   // nested nodes (sections, repeaters)
}

type NodeType =
  | 'section'        // visual grouping (no data)
  | 'repeater'       // collection container
  | 'Text' | 'Number' | 'Date' | 'Age'
  | 'SelectOne' | 'SelectMulti'
  | 'YesNo' | 'FullName'
  | 'IntegerPositive'
  // ... extensible
```

**Key rule:** A node with `type: 'section'` has NO `binding` in the submission data. It's visual-only. A node with `type: 'repeater'` has a `binding` that maps to a key in `collections`.

---

## 3. Public API

```typescript
interface FormEngine {
  // ── Lifecycle ───────────────────────────────────────────────
  /** Initialize with a template tree. Optionally hydrate from an existing submission. */
  initialize(tree: TemplateTree, existing?: V2Submission): void;

  /** Tear down — release subscriptions, clear state. */
  destroy(): void;

  // ── Singleton value reads/writes ────────────────────────────
  getValue(binding: string): unknown;
  setValue(binding: string, value: unknown): void;

  // ── Collection reads/writes ─────────────────────────────────
  /** Get a single row by collection name and row ID. */
  getRow(collection: string, rowId: string): CollectionRow;

  /** Get all rows in a collection, optionally filtered by parent. */
  getRows(collection: string, parentId?: string): Record<string, CollectionRow>;

  /** Set a single field value within a collection row. */
  setRowValue(collection: string, rowId: string, binding: string, value: unknown): void;

  /** Add a new empty row. Returns the generated row ID (ULID). */
  addRow(collection: string, parentId?: string): string;

  /** Remove a row and all its children (cascading for nested repeaters). */
  removeRow(collection: string, rowId: string): void;

  // ── Node UI state (rule evaluation results) ─────────────────
  /** Get computed UI state for a specific node. */
  getNodeState(nodeId: string): NodeUIState;

  // ── Observables ─────────────────────────────────────────────
  /** Emits on any value/collection change. */
  stateChange$: Observable<StateChangeEvent>;

  /** Emits when rule evaluation changes a node's visibility/required/disabled. */
  nodeStateChange$: Observable<NodeUIStateChange>;

  // ── Submission assembly ─────────────────────────────────────
  /** Assemble the current state into a V2 submission payload. */
  getSubmission(): V2Submission;

  /** True if any value has been modified since initialize/last save. */
  isDirty(): boolean;

  /** True if all mandatory fields are filled and all validations pass. */
  isValid(): boolean;
}
```

### Node UI State

```typescript
interface NodeUIState {
  nodeId: string;
  visible: boolean;     // controlled by SHOW/HIDE rules
  required: boolean;    // controlled by SET_REQUIRED rules
  disabled: boolean;    // controlled by DISABLE rules
  errors: string[];     // validation error messages
}

interface StateChangeEvent {
  path: string;         // e.g., "values.visitdate" or "collections.medicines.01K693..."
  value: unknown;
  previousValue: unknown;
}

interface NodeUIStateChange {
  nodeId: string;
  state: NodeUIState;
  previousState: NodeUIState;
}
```

---

## 4. Rule Evaluation (Namespace Resolvers)

Rules are defined in the template tree on each node. The engine evaluates them using three **namespaces** that bridge the flat normalized state and the hierarchical UI context.

### 4.1 `_row` — Intra-Row (Current Row Context)

**When:** A rule is scoped to a repeater and references `_row.fieldName`.

**Resolution:** The engine passes the single row object for the row currently being evaluated.

```json
{
  "condition": { "==": [{ "var": "_row.amd" }, "other"] },
  "effects": [{ "target_node": "MYZOyP37ilc", "action": "SHOW" }]
}
```

**Engine behavior:** When evaluating this rule for row `uuid-123`, the engine sets `_row = collections.medicines["uuid-123"]`, then runs the JsonLogic condition. **O(1).**

### 4.2 `$rel` — Relational (Parent-Scoped Children)

**When:** A rule on a parent repeater needs to aggregate over child rows.

**Resolution:** The engine filters the child collection by `_parent_id === currentParentRowId`, then passes the resulting array.

```json
{
  "scope": "households",
  "condition": {
    "some": [
      { "var": "$rel.family_members" },
      { "<": [{ "var": "age" }, 5] }
    ]
  }
}
```

**Engine behavior:** For household `hh_001`, the engine computes `Object.values(collections.family_members).filter(m => m._parent_id === 'hh_001')` and feeds it to `some`. **O(K)** where K = child rows for this parent.

### 4.3 `$global` — Global (All Rows, Unfiltered)

**When:** A rule needs to check across ALL rows in a collection regardless of parent.

**Resolution:** The engine passes `Object.values(collections[collectionName])` as a flat array.

```json
{
  "scope": "global",
  "condition": {
    "some": [
      { "var": "$global.medicines" },
      { "==": [{ "var": "drug_type" }, "Narcotic"] }
    ]
  }
}
```

### 4.4 Memoization Strategy

Namespace resolvers are **memoized** (cached until invalidated):

| Namespace | Cache Key | Invalidated When |
|---|---|---|
| `_row` | `collection + rowId` | Any field in that row changes |
| `$rel` | `collection + parentId` | Any child row is added/removed/changed |
| `$global` | `collection` | Any row in the collection changes |

This ensures rule evaluation is fast even with large forms.

---

## 5. How Angular Components Use the Engine

### Container (Smart) Component — `FormFillPage`

```typescript
@Component({ ... })
export class FormFillPage {
  private engine = inject(FormEngineService);
  private api = inject(TemplateApiClient);

  tree = signal<TemplateTree | null>(null);

  async ngOnInit() {
    const templateUid = this.route.snapshot.params['uid'];
    const tree = await this.api.getTemplateTree(templateUid);
    this.engine.initialize(tree);
    this.tree.set(tree);
  }

  onSubmit() {
    if (this.engine.isValid()) {
      const submission = this.engine.getSubmission();
      this.submissionService.submit(submission);
    }
  }
}
```

### Presenter (Dumb) Component — `TextFieldComponent`

```typescript
@Component({
  selector: 'app-text-field',
  template: `
    @if (uiState().visible) {
      <label>{{ label() }}</label>
      <input [value]="value()" (input)="onChange($event)" [disabled]="uiState().disabled" />
      @if (uiState().errors.length) {
        <span class="error">{{ uiState().errors[0] }}</span>
      }
    }
  `
})
export class TextFieldComponent {
  node = input.required<TreeNode>();

  private engine = inject(FormEngineService);

  value = computed(() => this.engine.getValue(this.node().binding));
  uiState = computed(() => this.engine.getNodeState(this.node().node_id));
  label = computed(() => this.node().label?.['en'] ?? this.node().binding);

  onChange(event: Event) {
    const val = (event.target as HTMLInputElement).value;
    this.engine.setValue(this.node().binding, val);
  }
}
```

### Dynamic Component Resolution

The container iterates over `tree.children` and resolves each node to a component by `type`:

```typescript
const COMPONENT_MAP: Record<NodeType, Type<any>> = {
  'section':         SectionComponent,
  'repeater':        RepeaterComponent,
  'Text':            TextFieldComponent,
  'Number':          NumberFieldComponent,
  'Date':            DateFieldComponent,
  'SelectOne':       SelectOneComponent,
  'SelectMulti':     SelectMultiComponent,
  'YesNo':           YesNoComponent,
  // ...
};
```

Each node is rendered recursively: sections and repeaters render their `children`. Leaf fields render input controls.

---

## 6. Collection (Repeater) Management

### Adding a Row

```typescript
// In RepeaterComponent
onAddRow() {
  const newRowId = this.engine.addRow(this.node().binding);
  // Engine creates: collections.medicines[newRowId] = {}
  // Engine emits stateChange$ → Angular re-renders
}
```

### Nested Repeaters

For a `family_members` repeater nested inside `households`:

```typescript
// In the family_members RepeaterComponent, nested inside a households row
onAddFamilyMember() {
  const parentRowId = this.currentHouseholdRowId();
  const newId = this.engine.addRow('family_members', parentRowId);
  // Engine creates: collections.family_members[newId] = { _parent_id: parentRowId }
}
```

### Removing a Row

```typescript
onRemoveRow(rowId: string) {
  this.engine.removeRow(this.node().binding, rowId);
  // Engine removes the row AND cascades to child collections
  // (removes any family_members where _parent_id === rowId)
}
```

---

## 7. Validation

The engine performs validation at two levels:

| Level | Source | Examples |
|---|---|---|
| **Field-level** | `TreeNode.mandatory`, `TreeNode.validation` | Required field empty, number out of range |
| **Rule-level** | `Rule.effects` with `action: "SET_REQUIRED"` | Conditionally required based on other field values |

Validation runs automatically on every `setValue` / `setRowValue`. The `isValid()` method checks all visible, required fields.

> [!IMPORTANT]
> **Hidden fields are NOT validated.** If a rule hides a field, its value is preserved in state but excluded from validation. This prevents "phantom required field" errors when rules hide conditional sections.

---

## 8. Related Docs

| Topic | Document |
|---|---|
| **Frontend architecture** (layers, modules, folder layout) | [Overview](overview.md) |
| **Full V2 contract** (migration, ACL, history, all edge cases) | [V2 Contract](../../form_template_and_submission_v2_contract_discussion.md) |
| **Integration boundary** (how V2 relates to V1, downstream BCs) | [Integration Contract](../../architecture/integration-contract-datarunapi.md) |
