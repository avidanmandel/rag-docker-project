# ScoutMatch AI — Demo Scenario (Lecturer Script)

Use disposable sessions on http://3.239.47.249/ after v12 cutover.

1. Show home page — ScoutMatch landing hero and club workspace.
2. Ask baseline: *What is the club's transfer budget?* → 100,000 EUR from `transfer_budget.txt`.
3. Upload demo CVs: Ron Ben Ari (PDF), Dor Levi (DOCX), Tal Raz (DOCX), Eyal Mor (CSV), Pedro Silva (TXT).
4. Ask: *Who is Ron Ben Ari?* → grounded profile from uploaded CV.
5. Ask: *Which candidates are willing to relocate?* → Ron, Tal, Pedro; exclude Dor and Eyal.
6. Ask: *Who is the cheapest right back?* → Ron Ben Ari, 43,000 EUR.
7. Ask: *Who is the best fit to play below the striker?* → Tal Raz with tactical rationale.
8. Ask: *Can the club afford both Ron Ben Ari and Tal Raz?* → yes, 93,000 EUR within 100,000 EUR budget.
9. Upload `ron_ben_ari_availability_update.txt` and wait for sync.
10. Ask: *Who is the best immediate option for right back?* → recommendation shifts away from Ron.
11. Delete the availability update and wait for sync.
12. Ask the same right-back question → Ron may be preferred again; deleted update absent from sources.
13. Open a new session — baseline budget still works; Ron Ben Ari question refuses (no leakage).
14. Ask out-of-domain: *Who is Donald Trump?* → refusal, no sources.
15. Explain architecture: Docker on EC2, boto3, S3 session + baseline prefixes, Bedrock KB, session isolation, cleanup dry-run only until demo complete.

See `docs/RAG_DATA_LIFECYCLE.md` and `docs/BASELINE_BUSINESS_ACCEPTANCE_MATRIX.md` for validation details.
