# Release evidence — 15 October 2026

Sonaweft is deployed at https://m-amir-gomaa--sonaweft-web-app.us-east.modal.run. `/health` reports hosted processing enabled and billing disabled. Existing Pageweft cloud identities, balances and files were not migrated.

| Check | Actual evidence | Scope |
|---|---|---|
| Automated suite | 52 tests passed, Python safety lint and both JS syntax checks passed | Real temporary SQLite/files/FFprobe; model dispatch and Paddle HTTP are mocked |
| Local speech | Existing cached small model transcribed the original generated recording in about 5.4 seconds | CPU/int8 on this laptop; not an accuracy benchmark |
| Cloud speech | Pinned large-v3 revision on Modal L4 returned the expected two English sentences | Real inference, cloud-cached weights; not local MX350 inference |
| Optional review | Real configured DeepSeek Flash returned schema-valid notes; combined cloud processing reached ready | Actual text provider, original preserved; advanced model listed by API but not inference-benchmarked |
| Public workflow | Chromium uploaded/inspected the generated recording, confirmed a trial, waited for actual cloud ASR, opened source audio, saved a separate correction and downloaded a ZIP | Public HTTPS and real workers/storage; no customer media or purchase |
| Responsive browser | 320/390/768/1440 workspace/review widths and 20 policy/checkout cases passed with zero page errors/overflow | System Chromium; desktop/phone screenshots visually reviewed, not physical iPhone/Safari certification |
| Source lookup | Real Crossref request returned DOI candidates; tests exercise malformed results/outage and route consent/ownership/rate limits | Bibliographic matches only; no truth verdict or general search |
| Recovery/accounting | Once-only reservation/settlement, partial/full refund, chargeback, outage, replay, ownership and revision cases passed | Provider responses mocked; SQLite durable and concurrent checks real |
| Owner backup | Actual remote financial snapshot encrypted/downloaded/decrypted into a disposable SQLite clone; integrity `ok`, zero balance violations, zero media rows | Financial recovery snapshot, not media restore or production rollback |
| Nix | `nix build .#default --no-link` succeeded; built CLI actually transcribed the generated audio and published a complete hashed export | Nixpkgs Python 3.14.6 / faster-whisper 1.2.1 / PyAV 17.0.1; no system rebuild |
| Portfolio | Seven DOM tests and four Chromium viewport checks passed for the updated card/link/details | Sonaweft linked explicitly; Noteweld remains a proposal |
| Paddle setup | Separate real product, fixed $5/$10 prices, client token and paused notification created; Sonaweft hostname submitted and observed **In review** | Seller identity approval, real checkout/webhook/refund/payout remain unverified |

The initial cloud probe exposed cross-environment exception/NumPy serialization failures; native JSON values and a plain error envelope fixed them before public enablement. Local testing found PyAV 19 incompatible with the pip speech dependency combination, so pip/cloud use the tested 15.1.0 pin. Nix supplies a separately tested compatible pair. The launcher also handled a Nix library-discovery SIGPIPE before release.

Private reproducible probe data/logs/screenshots are ignored under `.local/fixtures/`, `.local/browser/` and `.local/backups/`. Original sample text was generated locally with eSpeak: “A careful reader can follow the original recording. This example contains two short sentences.” No customer or copyrighted book media was used. The internal seeded $5 validation credit is explicitly unverified fixture funding; reports show zero commercial purchases. One failed diagnostic job is retained in aggregate metrics; it was not hidden as success.

## Remaining commercial and quality gates

- Actual Paddle seller/website approval, isolated sandbox delivery and controlled live purchase/refund/payout acceptance; keep production notification paused and billing closed meanwhile.
- Representative long/noisy/accented audio accuracy, 60-minute runtime/failure-cost benchmarks, load/admission and operational margin measurement before increasing the small preview caps. A working short sample is not capacity evidence for 1,000 users.
- Provider-wide budget/alerts and automatic external monitoring are not configured. Admission estimates are not a total bill cap; owner checks and pause controls are available.
- Hosted URL import, diarization, immediate self-service deletion, email accounts/team access, Noteweld importer and shared login are not implemented. No enterprise/privacy certification is claimed.
- No trademark clearance, user-demand/revenue guarantee or perfect-transcription claim. See OPERATIONS.md for concrete payment opening steps.
