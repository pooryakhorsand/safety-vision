"""Form for adding and editing a camera (admin only)."""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.cameras.models import Camera
from apps.cameras.sources import is_valid_source
from apps.vision_modules.registry import get_enabled_modules


class CameraForm(forms.ModelForm):
    modules = forms.MultipleChoiceField(
        label=_("Modules"),
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Which analyses run on this camera."),
    )

    class Meta:
        model = Camera
        fields = ("name", "group", "source_url", "modules", "is_enabled", "display_order")
        widgets = {"source_url": forms.TextInput(attrs={"dir": "ltr", "autocomplete": "off"})}
        help_texts = {
            "source_url": _("rtsp://user:password@address/stream, a video file path, or a webcam number such as 0."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        enabled = get_enabled_modules()
        self.fields["modules"].choices = [(module.key, module.name) for module in enabled]
        if not self.is_bound:
            # A camera saved with an empty list ran every module: show them all ticked.
            current = self.instance.modules if self.instance.pk and self.instance.modules else [m.key for m in enabled]
            self.initial["modules"] = current
        self.fields["source_url"].required = True

    def clean_source_url(self):
        value = self.cleaned_data["source_url"].strip()
        if not is_valid_source(value):
            raise forms.ValidationError(_("Enter an rtsp:// or http:// address, a full file path, or a webcam number."))
        return value

    def clean_modules(self):
        return list(self.cleaned_data["modules"])
