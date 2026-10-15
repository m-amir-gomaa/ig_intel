# Sonaweft architecture

```text
Browser --> secure cookie + CSRF --> FastAPI / Modal
                                       |--> serialized SQLite ledger writer
                                       |--> private media volume (48-hour TTL)
                                       |--> confirmed CPU coordinator
                                              |--> FFmpeg normalization
                                              |--> L4 / faster-whisper large-v3
                                              |--> optional DeepSeek text review
                                              |--> committed result --> settle hold
Review player / separate corrections / portable exports <--|
Explicit selected claim --> Crossref metadata candidates

Isolated checkout --> Paddle --> signed durable inbox
                                 |--> fresh transaction + all adjustment pages
                                 |--> intent/owner/product-bound credit or revocation
```

`instascript/contract.py` validates original ASR and exact source-quoted review and creates versioned exports. `pipeline.py` provides local private checkpoints, exclusive locks, completion hashes and atomic publication. `review.py` bounds text/output, validates JSON and has no autonomous tools. Local `source.py` downloads are never invoked for public uploads.

`sonaweft_web/app.py` handles ownership, CSRF, request limits, consent, quotes, revisions, exports and isolated checkout. `media.py` restricts FFmpeg to file/pipe protocols and rejects network-capable playlist formats. `storage.py` validates UUID paths and audio byte ranges. Aggregate activity logs exclude transcripts and filenames.

Ledger confirmation atomically reserves fixed credit and estimated admission allowance before dispatch. Repeated request IDs reserve once. Success consumes the complete quote; failure/cancellation/stale timeout releases it. Cleanup releases work exceeding the 20-minute deadline; a late worker cannot settle a released hold. No automatic paid retry is made.

Signed notification payloads cannot fund accounts alone. Fresh Paddle transaction/adjustment verification checks server-owned intents, owner, product/prices, quantity, currency and environment. Refund revocation is monotonic; queued work is cancelled if necessary and debt blocks new work. Running work may finish with negative available credit while the invariant remains checked. Unknown transactions/products are ignored. Mocks do not establish real delivery or approval.

Separate media/model/ledger volumes isolate state. Hourly cleanup deletes expired files and retains seven daily encrypted financial snapshots with media metadata removed. Session-key rotation invalidates sessions/IP hashes; old keys are needed for old cloud snapshots. Owner-downloaded backups use a separate generated key.

One speech container/coordinator and bounded uploads, rate limits, trial/admission/storage caps limit initial exposure. Estimated admission caps are not provider-wide hard spending limits. Storage, requests, failed work and schedules can still cost money.

Sonaweft and Pageweft share reviewed owned payment logic and currently an account-scoped Paddle runtime key, with distinct product/prices, notification secret, sessions, ledgers and volumes. They have no sibling runtime imports or shared customer wallet. Key rotation affects both until separate keys are configured.

Future Noteweld imports must validate schema, size, paths, hashes and duplicate identity before one atomic import. Stable segment IDs/provenance preserve the original/corrections/notes distinction. Exporting a manifest does not implement that importer.

Legacy summarize/LLM adapters, Claude/UTCP examples and vault scaffolding are compatibility/history paths, not the hosted pipeline. Jev is retired. Research metadata matches never certify truth.
