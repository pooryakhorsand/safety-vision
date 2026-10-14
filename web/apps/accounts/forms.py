"""Forms for signing in and for creating users (admin only)."""

from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


class LoginForm(AuthenticationForm):
    """Standard Django login form with UI attributes on the inputs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"autocomplete": "username", "autofocus": True})
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})


class UserCreateForm(UserCreationForm):
    """Used by admins to add a new admin or operator account."""

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "role")
        labels = {
            "first_name": _("First name"),
            "last_name": _("Last name"),
            "role": _("Role"),
        }
