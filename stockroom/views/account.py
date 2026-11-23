from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse

from ..forms import StoreLoginForm
from ..roles import home_url_name, primary_role


class RoleLoginView(LoginView):
    template_name = "stockroom/login.html"
    authentication_form = StoreLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse(home_url_name(self.request.user))


@login_required
def home(request):
    return redirect(home_url_name(request.user))


def no_access(request):
    logout(request)
    messages.error(
        request,
        "This account cannot sign in. It is only used when equipment is issued.",
    )
    return redirect("login")


@login_required
def no_role(request):
    if primary_role(request.user):
        return redirect(home_url_name(request.user))
    return render(request, "stockroom/no_role.html")
