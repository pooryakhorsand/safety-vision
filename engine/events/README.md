# events/

Shared by every module.

- `state_machine.py`: turns a stream of per-frame observations into events: a violation must last
  `confirm_seconds` to open an event, and be gone for `clear_seconds` to end it. A repeat by the same
  person inside the merge window reopens the same event.
- `snapshot.py`: builds the evidence picture (JPEG) for an event.
