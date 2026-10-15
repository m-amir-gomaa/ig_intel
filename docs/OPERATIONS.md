# Sonaweft operations — 15 October 2026

Live: https://m-amir-gomaa--sonaweft-web-app.us-east.modal.run

## Observed account state

The existing owner Modal account hosts `sonaweft`. Volumes: `sonaweft-media-v1`, `sonaweft-ledger-v1`, `sonaweft-models-v1`. Secrets: `sonaweft-session`, `sonaweft-payments`, `sonaweft-llm`. Large model weights are cached only in the cloud.

The existing verified-email Paddle seller has a separate Sonaweft SaaS product, one-time USD $5/$10 prices, client token and **paused** notification destination at the live regional hostname's `/api/payment-event`. The account-scoped runtime key is currently reused from Pageweft; product/prices/intents are checked independently. Private setup values are ignored under `.local/integrations/`.

Paid access remains closed. The Sonaweft hostname was submitted through the existing signed-in Firefox account and observed **In review** on 15 October. Pageweft remains separately in review. Email verification does not establish identity, seller or website approval. The runtime key expires **13 January 2027**; rotate before **6 January**, updating both products if still shared.

## Owner controls

Run from this repository using the authenticated Modal SDK; no public admin endpoint exists.

```sh
.venv-web/bin/python scripts/operations.py report
.venv-web/bin/python scripts/operations.py pause
.venv-web/bin/python scripts/operations.py resume
.venv-web/bin/python scripts/operations.py caps --day-units 10000 --month-units 20000
.venv-web/bin/python scripts/operations.py backup --output .local/backups/financial-NEW.fernet
```

10,000 admission units represent $1 of **estimated processing allowance**. Initial caps are $1/day and $2/month, including admitted failed attempts; they are not provider-wide hard spending limits. Changing them changes exposure. Pause rejects new processing without deleting data or balances. Report checks balance invariants, commercial purchases, pending jobs/events and aggregate activity. If invariants fail, pause and investigate before resuming.

Monitoring is owner-pulled reports plus Modal logs/usage; automated external alerts are not configured. Review actual provider usage regularly and configure account-level alerts/limits where supported; no global provider hard cap has been verified.

Backups create exclusive mode-0600 encrypted files plus a separate `.key`. Move the key to separate secure storage. Encryption roundtrip is checked. A restore drill additionally needs a temporary private SQLite database, integrity/invariant comparison and reconciliation before touching production. Never overwrite a running ledger. Hourly cleanup retains seven daily cloud financial snapshots encrypted with the session key; keep that key securely. Financial backups intentionally exclude media.

## Required payment opening sequence

1. Finish the owner's personal/identity/business review in the **existing** Paddle seller. Amir must supply correct unknown legal details, including DOB; do not create another seller or guess them.
2. Settings → Website approval: submit the actual regional hostname and product/pricing/operator/policy pages. Record actual approval and whether prepaid processing packs are accepted; a submission is not approval.
3. Use isolated sandbox product/notification/ledger configuration to exercise purchase, abandonment, duplicate/reordered delivery, full/partial refund, chargeback, lost dispatch, recovery and provider outage. Existing HTTP mocks do not replace real delivery. Sandbox must never credit production.
4. After production approval, verify the paused production notification, three handled event types and matching signing secret. Runtime permissions are transaction read/write and adjustment read. Credentials stay server-side.
5. Compare actual long/noisy recording costs, retries, tax/payment fees and refunds to the tariff. Configure provider budgets/alerts and appropriate admission caps. The current tariff is provisional, not proven net profit.
6. A controlled production purchase/refund must establish checkout, authentic delivery, reconciliation and payout treatment. Only then open `BILLING_MODE=live` and `PADDLE_SELLER_APPROVED=true`. Temporary owner acceptance activation must be closed immediately if any check fails.

No $1 monthly subscription is added. Occasional-use $5/$10 packs amortize payment fees. These are separate processing entitlements, not a shared wallet, exact-cost pass-through or lifetime service guarantee.

## Deployment and incidents

Install Python 3.13, FFmpeg and `.[web,cloud]`; authenticate your own Modal account and configure all three secrets before `python -m modal deploy app.py`. New self-hosters require their own Paddle products/approvals. The development freeze is separate from pinned cloud image dependencies/model revision.

After ambiguous dispatch, refresh the existing job; do not automatically create a new billable job. Stale queued/running jobs release holds after 20 minutes through cleanup/status checks. Failed paid jobs offer explicit quoted retry; retained ASR may be reused. Free allowances are not automatically reset on provider failure. Pause admissions for persistent faults, inspect logs without printing transcripts/secrets, correct and redeploy, then resume.

Sources/results are deleted by the first hourly cleanup after 48-hour expiry. No immediate user-delete control is implemented; contact `mo.gomaa.formal@gmail.com` with ownership proof, never recovery keys or recordings. Recovery uses a private bearer key; email login, team sharing and enterprise compliance are not claimed.

## Primary references

- [Modal images](https://modal.com/docs/guide/images), [GPUs](https://modal.com/docs/guide/gpu), [volumes](https://modal.com/docs/guide/volumes), [pricing](https://modal.com/pricing).
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [model source/license](https://huggingface.co/Systran/faster-whisper-large-v3).
- [DeepSeek models/pricing](https://api-docs.deepseek.com/quick_start/pricing/); the actual account returned both configured model IDs on 15 October 2026.
- [Paddle domain verification](https://www.paddle.com/help/start/account-verification/what-is-domain-verification), [signatures](https://developer.paddle.com/webhooks/signature-verification), [transactions](https://developer.paddle.com/api-reference/transactions/overview), [adjustments](https://developer.paddle.com/api-reference/adjustments/overview).
- [Crossref REST](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) and [access](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/).
