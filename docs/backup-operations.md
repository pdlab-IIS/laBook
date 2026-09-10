# Scheduled backup operations

## Status

The systemd service, timer, and retention logic were installed in production on
2026-09-01. The first manual run completed successfully and created
`backups/daily/library.db_20260901-234805-004353.db` with mode 0600. The timer is
active and waiting for its first scheduled run.

## Policy

- `labook-backup.timer` schedules the job daily at 03:15 in the host timezone.
- systemd may delay the start by up to 10 minutes to avoid a fixed load spike.
- `scripts.run_backup` uses the SQLite Backup API and checks
  `PRAGMA integrity_check` before reporting success.
- New scheduled backups are written to
  `/home/pdlab/labook/backups/daily` with mode 0600.
- The job keeps at most 90 matching backups and removes matching backups older
  than 120 days.
- The newest matching backup is always preserved, even if the host clock or
  schedule has been incorrect.
- Retention only considers regular, non-symlink files created with the current
  `library.db_<timestamp>.db` naming scheme in `backups/daily`.
- Existing historical backup directories and unrelated files are not included
  in automatic retention.

Automated off-host backup with encryption at rest is a separate requirement and
remains pending until an approved encryption recipient is available. The manual
development-machine copy below uses encrypted transport and restricted local
permissions; it does not establish an encrypted-at-rest backup system.

## Approved development-machine copies

On 2026-09-08, the user explicitly authorized copying production DB backups to
the current development machine, including future copies in this workflow.
The approved destination is `C:\workspace\laBook\backups\` on the current
development machine (Tailscale address at authorization: `100.74.34.64`).
This records standing permission, not a new recurring transfer schedule.

- Copy a verified SQLite Backup API snapshot, not the live database file.
- Use SSH/SCP to the verified production host; the current address is
  `100.110.113.62`, with existing SSH host identity `100.65.97.87`.
- Create a separate destination folder per deployment and restrict its Windows
  ACL to the current development user and SYSTEM before transfer.
- Compare the source and destination SHA-256 hashes, then verify a restore into
  a disposable database and check integrity and foreign keys.
- Keep DB files excluded from Git. Do not publish DB contents or copy secret
  configuration files as part of this authorization.
- Do not overwrite the development application's active `library.db`, remove
  historical backups, or transfer to another machine or third-party service
  without separate authorization.

The first copy under this authorization was completed and verified on
2026-09-08; see [the deployment record](deployment-20260908.md).

## Production installation

Run these steps only after the reviewed branch has been deployed to
`/home/pdlab/labook`.

1. Create the new destination without moving or deleting historical backups.

   ```sh
   sudo install -d -m 0700 -o pdlab -g pdlab /home/pdlab/labook/backups/daily
   ```

2. Install the reviewed unit files.

   ```sh
   sudo install -m 0644 deploy/systemd/labook-subapp.service /etc/systemd/system/labook-subapp.service
   sudo install -m 0644 deploy/systemd/labook-backup.service /etc/systemd/system/labook-backup.service
   sudo install -m 0644 deploy/systemd/labook-backup.timer /etc/systemd/system/labook-backup.timer
   sudo systemctl daemon-reload
   ```

3. Restart the updated Slack-only subapp, then run one backup manually before
   enabling the schedule.

   ```sh
   sudo systemctl restart labook-subapp
   sudo systemctl start labook-backup.service
   sudo systemctl is-active labook-subapp
   sudo systemctl --no-pager --full status labook-backup.service
   sudo journalctl -u labook-backup.service -n 20 --no-pager
   ```

4. Confirm that the JSON summary reports `status=ok`, inspect the new file mode,
   and open the new backup read-only to confirm `integrity_check=ok`.

5. Enable the timer only after the manual run has passed.

   ```sh
   sudo systemctl enable --now labook-backup.timer
   systemctl list-timers labook-backup.timer --no-pager
   ```

## Failure and rollback

- A failed backup is removed by the backup helper and returns a non-zero service
  result.
- Retention is not run unless the new backup has passed its integrity check.
- Disable future runs with
  `sudo systemctl disable --now labook-backup.timer` while investigating.
- Do not delete or overwrite `library.db` as part of timer rollback.
- Keep a failed backup directory for inspection; do not merge it into the
  historical backup set.
