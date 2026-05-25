# Runtime Directory

This directory is committed only as an empty folder skeleton for new machines.

Do not commit generated files here:

- videos
- audio files
- subtitles
- logs
- active lock/state files
- model/cache output
- YouTube or Google credentials

The active-channel state files are created locally when needed:

```text
runtime/state/active_channel.json
runtime/state/active_channel.lock
```

Legacy/GAS processing may still use existing external folders. This runtime
skeleton is only a safe local workspace for components that need it.
