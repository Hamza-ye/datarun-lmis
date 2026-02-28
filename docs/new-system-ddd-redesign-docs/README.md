# SYSTEM OVERALL VISION
We are building a **domain-oriented ingestion platform** around a shared Data-Collection backbone. The system will translate field observations into canonical artifacts consumed by independent bounded contexts (Ledger, Inventory, CaseMgmt, etc.). The translation layer is purposely narrow and auditable; it may be realized as an Anti-Corruption Layer inside a downstream context, as a shared Event Gateway between contexts, or as a hybrid. We will evaluate those alternatives pragmatically as the platform and team evolve.

## Domain Ecosystem Overview

This project designs a **domain ecosystem around a shared Data-Collection backbone**, not merely “an adapter.” The system integrates generalized, evolving form-based collection with multiple independent domain services (Ledger, Case Management, Inventory, etc.), each owning UI, roles, storage, and domain logic, while exchanging information through shared events and a common operational context.

---

## 1 — What is being built (industry terms)

* Generalized Data Collection (forms; evolving)
* Multiple Domain Services (Ledger, CaseMgmt, Inventory, …)

  * Each domain has its own UI, roles, DB, and business logic
* Integration through shared data events and occasional UI composition across domains

Likely architectural fits:

* **Modular Monolith evolving to Microservices** — *probability: 70%*
* **Event-Driven Modular Architecture** — *probability: 80%*
* **Internal Platform / Domain Platform** (possible future state) — *probability: 50%*

Not intended:

* A generic integration SaaS, multi-tenant iPaaS, or public low-code transformation product.

This is internal domain infrastructure.

---

## 2 — Core architectural pattern

The architecture converges on:

> A Shared Event Backbone + Independent Domain Services

Key patterns in use or under consideration:

* Domain-Driven Design (DDD) and Bounded Contexts
* Event-Carried State Transfer
* Anti-Corruption Layers (ACLs)
* Backend-for-Frontend (BFF) for UI composition when needed

These are established, battle-tested patterns; the design follows them rather than inventing new paradigms.

---

## 3 — Adapter’s role in the architecture

The adapter functions as an **Anti-Corruption Layer (ACL)** between flexible Data-Collection inputs and strict domain services. Its responsibilities are translation, normalization, and reliable delivery. ACL implementations are typically custom to the domain and are rarely generic, off-the-shelf replacements.

---

## 4 — Two different ambitions (clarified)

Two distinct ambitions are possible and must be kept separate:

**Ambition A — Internal Platform for the Ecosystem**

* Shared ingestion, shared transformation DSL, shared delivery worker, reusable across internal domains.
* Reasonable and sustainable for internal use. *Probability: 65%*

**Ambition B — Generic Reusable Integration Framework**

* Arbitrary connectors, user-defined mapping rules, visual builders, extensible plugins, runtime scripting.
* This approach maps to products like NiFi, Camel, MuleSoft and often becomes overwhelming for small teams. *Probability of becoming burdensome: 85%*

---

## 5 — UI composition concerns

When the client both collects forms and needs domain data (e.g., stock on hand from Ledger), this pattern is called **Backend-for-Frontend (BFF)** or **API Composition Layer**. UI aggregation needs should be served by BFF or composition services—not by the integration engine.

Required capabilities for UI composition:

* Clean domain APIs
* Optional gateway or BFF for aggregation
* Shared authentication and context propagation

---

## 6 — Target architecture sketch

```
          General Data Collection
                    ↓
         Ingestion / ACL Layer (DSL + Mapper)
                    ↓
   -----------------------------------
   |        |            |           |
 Ledger   CaseMgmt      ...     Other Domains
```

Each domain:

* Owns its DB, UI, roles, invariants
* Consumes events produced by the ingestion/ACL layer
  This corresponds to an event-driven modular architecture rather than an iPaaS model.

---

## 7 — Core question to resolve

Which is the primary outcome:

* A domain ecosystem (internal infrastructure), or
* An integration product (generic external platform)

Current evidence and design indicate the work is a **domain ecosystem**; in that case the DSL functions as a domain Anti-Corruption Layer rather than a generic integration framework.

---

## 8 — Common concerns and reality check

Typical uncertainties include:

* Reinventing existing tools (ETL engines, iPaaS) — those tools solve generic problems but do not usually match domain-specific mapping logic.
* Missing a small tool vs. needing a custom ACL — domain-specific translations generally require custom development.

Domain-specific ACLs are normally custom and acceptable.
