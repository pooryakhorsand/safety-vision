"""
PPE module: helmet, safety vest, safety shoes.

Which items exist and which event each missing item raises is set in the settings
(modules.ppe.items), because every customer's model has its own class names.
"""

from __future__ import annotations

from engine.core.config import EngineConfig
from engine.core.frame import FrameContext, Label, Observation
from engine.modules.base import VisionModule, register_module
from engine.modules.ppe.association import assign_equipment
from engine.modules.ppe.voting import BAD, PpeVoter


@register_module
class PpeModule(VisionModule):
    key = "ppe"
    required_detectors = ("equipment",)

    def __init__(self, config: EngineConfig, camera_id: int):
        super().__init__(config, camera_id)
        self.settings = config.modules.ppe
        self.voter = PpeVoter(self.settings)

    def event_type_for(self, item: str) -> str | None:
        for key, event_type in self.settings.items.items():
            if key in item:
                return event_type
        return None

    def process(self, ctx: FrameContext) -> list[Observation]:
        persons = [(t.track_id, t.box) for t in ctx.persons]
        equipment = [(d.class_name, d.confidence, d.box) for d in ctx.detections.get("equipment", [])]
        assigned = assign_equipment(persons, equipment, self.settings)

        observations: list[Observation] = []
        for track in ctx.persons:
            states = self.voter.update(track.track_id, assigned.get(track.track_id, []), ctx.frame_index)

            labels = [
                Label(("no_" + item) if state == BAD else item, state == BAD) for item, state in sorted(states.items())
            ]

            # Several items can raise the same event (shoe + boot -> no_safety_shoes): combine them.
            by_event: dict[str, tuple[bool, float]] = {}
            for item, state in states.items():
                event_type = self.event_type_for(item)
                if event_type is None:
                    continue
                active, conf = by_event.get(event_type, (False, 0.0))
                by_event[event_type] = (active or state == BAD, max(conf, self.voter.confidence(track.track_id, item)))

            for event_type, (active, conf) in sorted(by_event.items()):
                observations.append(
                    Observation(
                        track_id=track.track_id,
                        event_type=event_type,
                        active=active,
                        confidence=conf,
                        box=track.box,
                        labels=labels,
                        module=self.key,
                    )
                )
        self.voter.forget_stale(ctx.frame_index)
        return observations
