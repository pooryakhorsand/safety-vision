"""
First-run setup: create the first administrator, pick the language and the site name.
The page exists only while there is no user; afterwards it answers 404.
"""

from django import forms
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.core.models import SiteSettings
from apps.core.profile_loader import get_profile


class SetupForm(UserCreationForm):
    site_name = forms.CharField(
        label=_("Site name"), max_length=80, help_text=_("Shown in the top bar, e.g. the name of your plant.")
    )
    language = forms.ChoiceField(label=_("Language"), choices=[("fa", "فارسی"), ("en", "English")])

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        if commit:
            user.save()
        return user


def setup(request):
    if User.objects.exists():
        raise Http404
    profile = get_profile()
    initial = {
        "language": profile.default_language,
        "site_name": profile.text(profile.site_name, profile.default_language),
    }
    form = SetupForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        SiteSettings.save_values(form.cleaned_data["site_name"], form.cleaned_data["language"])
        login(request, user)
        response = redirect("dashboard:overview")
        response.set_cookie("django_language", form.cleaned_data["language"], max_age=365 * 24 * 3600)
        return response
    return render(request, "setup.html", {"form": form})
