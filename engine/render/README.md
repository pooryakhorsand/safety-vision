# render/

Everything drawn for people to look at. Display only: nothing here makes a decision.

| File | Job |
|------|-----|
| `overlay.py` | Person corners, tags and equipment boxes on the picture |
| `video_writer.py` | H.264 writer for the offline result |
| `stream.py` | MJPEG live view served on its own port (`render.stream_host` / `render.stream_port`) |

The stream has no login. It listens on 127.0.0.1 by default; sharing it with the network is a decision
for the operator and needs a firewall rule.
