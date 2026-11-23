from datetime import timedelta

from django.db.models import F
from django.shortcuts import render
from django.utils import timezone

from ..models import Asset, Consumable, Usage, get_settings
from ..roles import ADMIN, STANDARD
from .common import role_required


@role_required(STANDARD, ADMIN)
def dashboard(request):
    prefs = get_settings(request.user)
    today = timezone.localdate()
    horizon = today + timedelta(days=prefs.eol_warning_days)
    active_statuses = [Asset.Status.IN_STOCK, Asset.Status.ISSUED]
    context = {
        "in_stock_count": Asset.objects.filter(status=Asset.Status.IN_STOCK).count(),
        "issued_count": Asset.objects.filter(status=Asset.Status.ISSUED).count(),
        "missing_count": Asset.objects.filter(
            status=Asset.Status.IN_STOCK,
            stocktake_result=Asset.StocktakeResult.MISSING,
        ).count(),
        "low_stock_count": Consumable.objects.filter(
            quantity_on_hand__lte=F("reorder_level")
        ).count(),
        "over_max_count": Consumable.objects.filter(
            max_qty_to_hold__gt=0, quantity_on_hand__gt=F("max_qty_to_hold")
        ).count(),
        "eol_count": Asset.objects.filter(
            status__in=active_statuses, eol_date__lte=horizon
        ).count(),
        "eol_days": prefs.eol_warning_days,
        "recent_usage": Usage.objects.select_related("consumable", "recorded_by")[:8],
        "has_records": Asset.objects.exists() or Consumable.objects.exists(),
    }
    return render(request, "stockroom/dashboard.html", context)
