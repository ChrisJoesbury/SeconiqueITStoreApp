from .models import get_settings
from .roles import ADMIN, OPERATIONAL, REPORTING_ACCESS, has_role, primary_role


def stockroom_context(request):
    user = request.user
    if not user.is_authenticated:
        return {"scanner_auto_submit": True, "store_role": None}
    prefs = get_settings(user)
    return {
        "store_role": primary_role(user),
        "is_store_admin": has_role(user, (ADMIN,)),
        "is_operational": has_role(user, OPERATIONAL),
        "can_report": has_role(user, REPORTING_ACCESS),
        "scanner_auto_submit": prefs.scanner_auto_submit,
        "store_settings": prefs,
    }
