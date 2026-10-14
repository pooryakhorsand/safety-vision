"""
Account pages.

    login / logout       -> everyone
    user_list            -> admin only
    user_create          -> admin only
    user_toggle_active   -> admin only (enable / disable an account)

There is no public sign-up: in an industrial site, accounts are created
by an administrator.
"""

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts.forms import LoginForm, UserCreateForm
from apps.accounts.models import User
from apps.core.permissions import admin_required


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    """Logout works with POST only (Django security default)."""


@admin_required
def user_list(request):
    users = User.objects.all()
    return render(request, "accounts/user_list.html", {"users": users})


@admin_required
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, _("User “%(name)s” was created.") % {"name": user.username})
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form})


@admin_required
@require_POST
def user_toggle_active(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target == request.user:
        messages.error(request, _("You can't disable your own account."))
    else:
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        messages.success(request, _("Account status updated."))
    return redirect("accounts:user_list")
