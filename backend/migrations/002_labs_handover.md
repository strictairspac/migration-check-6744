# Schema v2 — lab isolation and batch handover

SQLAlchemy metadata creates labs/users/batches/mappings/runs/handovers/target_rows.
`users.lab_id` and `batches.lab_id` scope every list, read, write, download and audit
path: lab accounts use their own lab, administrators use all labs. `batches.lab_id`
NULL marks an old, unclaimed batch that only administrators can see until a handover.

Mappings, runs and target rows derive ownership from their batch, so handing over a
batch moves its whole history with it. `handovers.request_id` is unique; a replay
returns the original receipt without moving the batch again, even after later
handovers. Handover takes a row lock on the single batch only, so restores,
migrations and writes to other batches stay concurrent.

Startup runs `ensure_schema()`: `create_all` plus idempotent `ALTER TABLE ... ADD
COLUMN IF NOT EXISTS` for a pre-labs database. Existing rows keep their data;
historical batches remain unclaimed for the administrator to hand over.
