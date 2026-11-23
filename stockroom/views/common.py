from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect

from ..models import get_settings
from ..roles import has_role, home_url_name


def role_required(*roles):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not has_role(request.user, roles):
                messages.error(
                    request, "Your account does not have access to that page."
                )
                return redirect(home_url_name(request.user))
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def paginate(request, queryset):
    prefs = get_settings(request.user)
    paginator = Paginator(queryset, prefs.records_per_page or 25)
    return paginator.get_page(request.GET.get("page"))
