"""
Vision module registry.

Every analytics module is described here ONCE. The sidebar, the overview
cards, the events filters and the settings page are all built from this
list, so adding a module never requires editing a template.

Each module also declares the event types it can produce. The engine must
send one of these keys in "event_type"; anything else is rejected.

To add a module:
  1. Add a VisionModule entry to ALL_MODULES below (with its event types).
  2. Add its key to "enabled_modules" in the customer's profile.yaml.
  3. Add the translations to locale/fa/LC_MESSAGES/django.po.
"""

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

from apps.core.profile_loader import get_profile


@dataclass(frozen=True)
class EventType:
    key: str  # stable id sent by the engine, e.g. "no_helmet"
    name: str  # display name (translatable)
    severity: str = "warning"  # default severity: "info" | "warning" | "critical"


@dataclass(frozen=True)
class VisionModule:
    key: str  # stable id used in URLs, config and events, e.g. "ppe"
    name: str  # display name (translatable)
    description: str  # one short line (translatable)
    icon: str  # icon id from static/icons/icons.svg
    event_types: tuple[EventType, ...] = field(default_factory=tuple)

    def get_event_type(self, key: str) -> EventType | None:
        return next((t for t in self.event_types if t.key == key), None)


# All modules this product knows about. Order here does not matter;
# the sidebar order comes from the profile.
ALL_MODULES: dict[str, VisionModule] = {
    module.key: module
    for module in (
        VisionModule(
            key="ppe",
            name=_("PPE detection"),
            description=_("Helmet, safety vest and safety shoes"),
            icon="helmet",
            event_types=(
                EventType("no_helmet", _("No helmet"), "critical"),
                EventType("no_vest", _("No safety vest"), "warning"),
                EventType("no_safety_shoes", _("No safety shoes"), "warning"),
            ),
        ),
    )
}


def get_enabled_modules() -> list[VisionModule]:
    """Modules enabled in the active profile, in profile order."""
    return [ALL_MODULES[key] for key in get_profile().enabled_modules if key in ALL_MODULES]


def get_module(key: str) -> VisionModule | None:
    """Return an enabled module by key, or None."""
    return next((m for m in get_enabled_modules() if m.key == key), None)


def get_any_module(key: str) -> VisionModule | None:
    """Return a module by key even if it is not enabled (for old events)."""
    return ALL_MODULES.get(key)
