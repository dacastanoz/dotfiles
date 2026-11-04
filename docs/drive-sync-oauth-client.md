# Drive sync: moving a remote to your own OAuth client

rclone's shared Google client is being retired. rclone prints a notice on every run of a remote that still uses it. `drive-sync` turns that notice into a bar tooltip warning and at most one notification a day. The warning names only the remotes whose latest run printed the notice, and it clears by itself after their next successful run without it.

You only need this guide when the warning appears. `drive-sync` never changes rclone's configuration itself.

## 1. Reuse an OAuth client if you have one

If another of your remotes already has a `client_id`, you can point this remote at the same client. You don't need a new client for each remote. All remotes on one client share its quota.

If you have none, create one by following [Making your own client ID](https://rclone.org/drive/#making-your-own-client-id) in the rclone docs. The type is **Desktop app**, and the Google Drive API must be enabled.

## 2. Check the consent screen

In the Google Cloud console, the client's consent screen must be:

- **User type:** External
- **Publishing status:** In production

While the status is **Testing**, Google expires refresh tokens after 7 days, and the sync fails with an auth error every week.

## 3. Point the remote at the client

Keep the remote name exactly as `rclone listremotes` shows it.

```sh
rclone config update <remote> client_id <id> client_secret <secret> --no-obscure
```

This puts the secret on your command line and in your shell history. To avoid that, use `rclone config` and edit the remote interactively.

Never commit `rclone.conf` or these values.

## 4. Reconnect

The old token belongs to the old client, so reconnect each remote you moved:

```sh
rclone config reconnect <remote>:
```

Until you do, the remote fails with `Error 401` or `invalid_client`. The bar shows this as an auth problem, along with this same command.

## 5. Check

Wait for the next scheduled run, or use **Sync now** in the Drive menu. The warning clears after that remote's next successful run. If it keeps failing with an auth error, check steps 2 to 4.
