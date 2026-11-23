from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from ..forms import UserSettingForm
from ..models import get_settings


@login_required
def user_settings(request):
    prefs = get_settings(request.user)
    if request.method == "POST":
        form = UserSettingForm(request.POST, instance=prefs)
        if form.is_valid():
            form.save()
            messages.success(request, "Your settings have been saved.")
            return redirect("user_settings")
    else:
        form = UserSettingForm(instance=prefs)
    return render(request, "stockroom/settings.html", {"form": form})
