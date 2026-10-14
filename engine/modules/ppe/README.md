# PPE module: helmet, safety vest, safety shoes

Watches every person in the camera and raises an event when a required piece of
protective equipment is missing for long enough. Module key: `ppe`.

<!-- TODO: add the demo GIF here, e.g. ![PPE demo](../../../docs/media/ppe_demo.gif) -->

> Demo footage in this repository is **recorded video**, not a live camera.

## What it reports

| Event type | Meaning | Default severity |
|------------|---------|------------------|
| `no_helmet` | Person without a safety helmet | critical |
| `no_vest` | Person without a safety vest | warning |
| `no_safety_shoes` | Person without safety shoes or boots | warning |

An event is **one violation over a period of time** (start, end, snapshot), not one row per frame.
The web console shows it; an operator can acknowledge it and say who the person is.

## How it works

```
frame → person detector → tracker → equipment detector
      → association (which box belongs to which person)
      → voting (smooth the result over time)
      → event state machine (confirm / clear)
      → snapshot + event sent to the web app
```

1. **Person detection and tracking.** A large YOLO model finds people; BoT-SORT gives each person a track ID that stays stable between frames.
2. **Equipment detection.** A custom model finds the equipment, both present items (`helmet`) and explicit missing ones (`no_helmet`).
3. **Association** (`association.py`). Each equipment box is given to exactly one person, using overlap with that person's box and the body zone where the item should be (head for the helmet, torso for the vest, feet for the shoes).
4. **Voting** (`voting.py`). The last N frames vote for each person and item. The state changes only when enough frames agree, so a single bad frame does not flip it. A tie counts as a violation (safety first).
5. **Event lifecycle** (shared `events/state_machine.py`). A violation must last `confirm_seconds` before it becomes an event, and must be gone for `clear_seconds` before it ends. Short blinks do not restart the timer (`pending_grace_seconds`).
6. **Repeat violations.** If the same person violates again within `merge_window_minutes`, the engine reopens the same event and increases its `occurrences` count instead of creating many events. The match uses appearance (ReID) and is only meant for minutes, not for identifying someone across days.

The engine never sends a name. Only an operator assigns a person to an event in the web app.

## Files

| File | Job |
|------|-----|
| `module.py` | The module class: runs association and voting, returns observations |
| `association.py` | Gives each equipment box to one person |
| `voting.py` | Per-person temporal voting with hysteresis |
| `weights/` | The equipment model `ppe.pt` (not in git) |

## Settings (`modules.ppe` in `engine/config/engine.yaml`)

| Key | Meaning |
|-----|---------|
| `zone_margin` | Extra room around the body zones when matching boxes |
| `min_contain` | Minimum share of an equipment box that must lie inside the person |
| `vote_window` | How many recent frames vote |
| `min_votes` | How many frames must agree before the state changes |
| `zones`, `items`, `item_colors` | Body zones, item to event type mapping, overlay colours (defaults exist) |

Timing (`confirm_seconds`, `clear_seconds`, `merge_window_minutes`) is in the `events` section. All keys are documented in `engine/config/engine.example.yaml`.

## Model weights

`ppe.pt` is not provided and not committed: you train it on your own images. Put it in `weights/` (see `weights/.gitignore`) or change `detectors.equipment.weights`. Required class names and training tips: [docs/models.md](../../../docs/models.md).

## Evaluation

No numbers are published because the model is yours. Measure speed with `python -m engine.tools.benchmark` and accuracy on video that was not used for training.


## Limitations

- Small or distant people and very low light reduce accuracy.
- Heavy overlap between people can give an item to the wrong person.
- Safety shoes are the hardest item: they are small and often hidden.
- The model only knows the equipment it was trained on; different helmets or vests may need more training data.
- The repeat-violation merge works for minutes within a shift and is not an identity system.

## Run it

```
python -m engine.core.main offline --help    # analyse a video file and write results
python -m engine.core.main replay --help     # play those results as a live camera in the web console
```
