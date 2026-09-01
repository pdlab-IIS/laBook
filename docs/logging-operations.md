# Logging operations

## Status

The application, Gunicorn, and subapp are configured to write to stdout or
stderr for collection by systemd-journald. The configuration is verified in an
isolated directory on the Raspberry Pi but is not installed in production.

Production currently uses `Storage=volatile`: the journal occupies about 30.9
MB in `/run` and is lost at reboot. The reviewed drop-in changes journald to
persistent storage with a 256 MB and 30-day ceiling while reserving at least 1
GB of filesystem free space. This retention setting is system-wide, not limited
to laBook services, and therefore must be reviewed as a host-level change before
installation.

## Recorded fields

The Gunicorn access log records the forwarded client address, timestamp, HTTP
method, URL path without its query string, protocol, status, response size, and
request duration. Query strings and request bodies are deliberately excluded.

Application messages should contain identifiers needed for diagnosis, result
status, duration, and exception type. They must not contain API tokens, webhook
URLs, review text, user details, complete external URLs containing keys, or
request bodies.

## Reading logs

```sh
journalctl -u labook.service --since today --no-pager
journalctl -u labook-subapp.service --since today --no-pager
journalctl -u labook-backup.service -n 50 --no-pager
```

Follow the web application during a maintenance check with:

```sh
journalctl -u labook.service -f
```

## Deployment and verification

1. Install the reviewed service files from `deploy/systemd/` and run
   `sudo systemctl daemon-reload`.
2. Install and activate the host-wide journal retention setting.

   ```sh
   sudo install -d -m 0755 /etc/systemd/journald.conf.d
   sudo install -m 0644 deploy/journald/60-labook-retention.conf /etc/systemd/journald.conf.d/60-labook-retention.conf
   sudo systemctl restart systemd-journald
   sudo journalctl --flush
   sudo journalctl --disk-usage
   ```

3. Deploy `logger_config.py` and `start_gunicorn.sh` together with the rest of
   the reviewed application revision.
4. Restart the services through `Prod.sh`.
5. Request `/healthz` and `/readyz`, then confirm that both access entries and
   application messages appear under `labook.service`.
6. Confirm that `logs/access.log`, `logs/error.log`, `labook.log`, and
   `labook-sub.log` no longer grow.
7. After a reboot test, confirm that entries from the previous boot remain
   available through `journalctl --list-boots`.

Existing legacy log files are evidence from earlier incidents. This migration
does not delete or truncate them. Archive or remove them only under a separate,
explicit retention decision after the journal transition has been observed.

To roll back only the host-wide persistence policy, remove the reviewed drop-in
and restart `systemd-journald`. Do not delete `/var/log/journal` until its
contents are no longer required for incident analysis.
