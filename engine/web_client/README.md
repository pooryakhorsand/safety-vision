# web_client/

The only code that talks to the web app: reads the camera list, sends events (with a disk-backed retry
queue, so nothing is lost while the web app is down) and sends the heartbeat. The API is described in
`docs/engine_api.md`.
