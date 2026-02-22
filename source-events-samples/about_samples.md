## about samples and mappings
supply nodes can be of types MU WH, HF, TEAM (mobile teams during temporary periodic campaigns), MOBILE WH (temporary WHs during campaigns) as a supply node.

* **[hf_receipt_902](./hf_receipt_902_example.json):**
from is mapped by crosswalking that mapps `team` which is the team uid to the MU supply node uid, or fall back to incoming `team` it's a campaign team, it might be rejected by ledger if not presents there, adapter have no business in this except it logs what the ledger will say. 
* **[wh_stocktake_901](./wh_stocktake_901_example%20(for%20MU%20stocktakes).json):**
the `orgunit` is the stocktake subject.
* **[wh_stocktake_hf_901](./wh_stocktake_hf_901_example.json):**
the `orgunit` is the stocktake subject.
* **[wh_team_receipt_902](./wh_team_receipt_902_example.json):**
`from` is the `orgUnit`, `to` is crosswalked from `team` which is the team uid, or fall back to same incoming value `team`.
* **[wh_team_returns_904](./wh_team_returns_904_example.json):**
`to` is the `orgUnit`, `from` is crosswalked from `team` which is the team uid, or fall back to same incoming value `team`.