"""
Small template helpers for the UI.

    {% load ui_tags %}
    {% icon "helmet" %}                 -> inline SVG icon from the sprite
    {% icon "chevron-left" "flip-rtl" %} -> extra CSS class(es)
    {% nav_active "dashboard:live" %}   -> "is-active" when on that page
    {{ event.duration|hms }}            -> "1:05:03" or "4:12"
"""

from django import template
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name, extra_class=""):
    sprite = static("icons/icons.svg")
    return format_html(
        '<svg class="icon {}" aria-hidden="true" focusable="false"><use href="{}#{}"></use></svg>',
        extra_class,
        sprite,
        name,
    )


@register.filter
def hms(value):
    """timedelta -> "H:MM:SS" (or "M:SS" under an hour)."""
    if value is None:
        return ""
    seconds = max(0, int(value.total_seconds()))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


@register.simple_tag(takes_context=True)
def nav_active(context, url_name):
    request = context.get("request")
    if request is None:
        return ""
    try:
        target = reverse(url_name)
    except NoReverseMatch:
        return ""
    return "is-active" if request.path.startswith(target) else ""
