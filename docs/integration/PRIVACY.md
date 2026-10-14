# Contribution reference implementation

Default is LOCAL_ONLY. The shipping native surfaces cannot enable contributions
until a trusted host approval bridge is verified. The fixture service does
implement forward-only automatic batching after a one-use authority grant.
It does not assume Nous consent or send to Nous. There is no production recipient.

The closed diagnostic_batch.v1 schema accepts only finite categories and bounded
counts. It rejects unknown/nested fields, duplicate keys, invalid encodings,
non-finite values and oversized input. A random package ID identifies a batch,
not an installation or user. No content hashes, messages, private model/tool
names, paths, credentials or raw errors are accepted. Unknown stack/model labels
are coarsened locally. Private deletion credentials are stored separately.

Consent binds destination, schema, purpose, retention and cadence. Observations
before consent are not collected for later upload. Pause/off purge unsent data;
restart is fail-closed LOCAL_ONLY. Destination change invalidates consent. A
send already in flight may complete before off returns (transport timeout two
seconds); revocation cannot retract bytes already sent. Receipt deletion is a
separate action. Local purge forgets receipts and therefore remote deletion
credentials; it does not delete receiver copies.

Queue bounds: 128 cells, 32 KiB per package, 1 MiB queue, five attempts, 72-hour
expiry. Receipt capacity is 128 and currently fails closed at capacity. A
production receipt-retention/rotation policy and host lifecycle worker are still
missing. The service tick implements daily batching with jitter; tests drive its
clock. It is not wired to native production hooks.

The loopback receiver stores accepted packages for at most 30 days while its
server loop runs; expiration also occurs on ingest and workbench reads. Stopped
services do not erase data until restarted. Deletion removes the active row and
recomputed aggregates. There is no backup manager or promise to erase filesystem
snapshots/SQLite free pages. Production backup/deletion policy remains required.
POSIX files are created mode 0600; Windows inherits directory ACLs.

The authenticated workbench exposes one fixed partition and suppresses cells
with fewer than three packages. It offers no totals, filters, raw drill-down or
download of individual packages. Package count is not unique users; suppression
is not anonymity, especially against colluding reporters or temporal differencing.
Reports are unverified, not proof of a mechanism or a safe global failure rate.

Threat boundary: malicious same-UID code/co-installed plugins are not isolated
by this plugin. The reference collector is not hardened for public deployment.
