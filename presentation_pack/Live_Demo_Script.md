# ScoutMatch AI — Live Demo Script

Duration: **2–3 minutes**.

## Prompt 1
```
We finished fourth last season. Analyze our current squad before the transfer window closes. Which position should we prioritize?
```
**Expected:** RAG-grounded answer with source cards.
**Fallback:** Retrieval usually takes 10–20 seconds.
**Screenshot:** artifacts/evidence/business_workflow_v2_staging/03_grounded_squad_analysis.png

## Prompt 2
```
I choose Ron Ben Ari as our right-back candidate. Submit the recommendation for management review.
```
**Expected:** Confirm / Deny card.
**Screenshot:** artifacts/evidence/business_workflow_v2_staging/09_critical_decision_confirm_card.png

## Click Confirm
**Expected:** 43,000 EUR reserved, 57,000 EUR remaining, Pending management approval.
**Screenshot:** artifacts/evidence/business_workflow_v2_staging/10_critical_decision_result.png

## Prompt 3
```
Show me the updated proposed lineup and squad-risk board.
```
**Expected:** Inline 11-player lineup board.
**Screenshot:** artifacts/evidence/business_workflow_v2_staging/12_visual_squad_board.png

## Human approval (say aloud)
Ron is not signed; Daniel Cohen is not sold; lineup is not approved.

## If live demo fails
Show screenshots above and state http://3.239.47.249/
