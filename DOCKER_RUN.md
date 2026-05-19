# Docker Run Commands

Build the image:

```powershell
docker compose build
```

Run runtime validation:

```powershell
docker compose run --rm app python scripts/check_runtime.py
```

Run the Docker smoke test:

```powershell
docker compose run --rm app python scripts/docker_smoke_test.py
```

Run the normal pipeline entrypoint:

```powershell
docker compose run --rm app
```

Persistent host directories:

- `runtime/logs` -> container logs
- `runtime/state` -> queue state snapshots
- `runtime/temp` -> temporary render/TTS files

The container keeps the existing entrypoint and does not implement upload
workers, dashboard services, or YouTube upload scaling.
