"""
Values available in every template:

    brand.product_name, brand.site_name, brand.logo_url, brand.accent_color
    app_version
    vision_modules   (enabled modules, for the sidebar and overview)
"""

from django.conf import settings
from django.templatetags.static import static
from django.utils.translation import get_language

from apps.core.models import SiteSettings
from apps.core.profile_loader import get_profile
from apps.vision_modules.registry import get_enabled_modules


def brand_context(request):
    profile = get_profile()
    language = (get_language() or profile.default_language)[:2]
    site = SiteSettings.current()  # chosen at first run; overrides the profile's site name
    return {
        "brand": {
            "product_name": profile.text(profile.product_name, language),
            "site_name": site.site_name if site and site.site_name else profile.text(profile.site_name, language),
            "logo_url": static(f"profile/{profile.logo}"),
            "accent_color": profile.accent_color,
        },
        "app_version": settings.APP_VERSION,
        "vision_modules": get_enabled_modules(),
    }
