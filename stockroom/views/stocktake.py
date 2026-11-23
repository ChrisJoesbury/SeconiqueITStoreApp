from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from ..forms import ScanForm
from ..models import Asset, Consumable
from ..roles import ADMIN, STANDARD
from ..services import complete_asset_stocktake
from .common import paginate, role_required

SESSION_KEY = "asset_stocktake"


def _scanned(request):
    values = request.session.get(SESSION_KEY, [])
    return list(dict.fromkeys(values))


def _save_scanned(request, barcodes):
    request.session[SESSION_KEY] = list(dict.fromkeys(barcodes))
    request.session.modified = True


@role_required(STANDARD, ADMIN)
def stocktake_home(request):
    return render(request, "stockroom/stocktake/home.html")


@role_required(STANDARD, ADMIN)
@require_http_methods(["GET", "POST"])
def stocktake_assets(request):
    scanned = _scanned(request)
    form = ScanForm()
    if request.method == "POST":
        step = request.POST.get("step")
        if step == "cancel":
            request.session.pop(SESSION_KEY, None)
            messages.success(request, "Asset stocktake cancelled. Nothing was changed.")
            return redirect("stocktake_assets")
        if step == "remove":
            barcode = request.POST.get("barcode", "")
            _save_scanned(request, [code for code in scanned if code != barcode])
            return redirect("stocktake_assets")
        if step == "complete":
            in_stock_codes = set(
                Asset.objects.filter(status=Asset.Status.IN_STOCK).values_list(
                    "barcode", flat=True
                )
            )
            if not in_stock_codes:
                messages.error(request, "There are no in-stock assets to count.")
                return redirect("stocktake_assets")
            ignored = [code for code in scanned if code not in in_stock_codes]
            found, missing = complete_asset_stocktake(request.user, scanned)
            request.session.pop(SESSION_KEY, None)
            messages.success(
                request,
                f"Stocktake complete. {found} found, {missing} marked missing.",
            )
            if ignored:
                messages.info(
                    request,
                    "Some scanned barcodes were not in stock, so they were left out of the count.",
                )
            return redirect("asset_list")
        form = ScanForm(request.POST)
        if form.is_valid():
            barcode = form.cleaned_data["barcode"]
            asset = Asset.objects.filter(pk=barcode).first()
            if asset is None:
                form.add_error("barcode", "No asset has that barcode.")
            elif asset.status != Asset.Status.IN_STOCK:
                form.add_error(
                    "barcode",
                    f"That asset is {asset.get_status_display().lower()}, so it is not part of this count.",
                )
            elif barcode in scanned:
                form.add_error("barcode", "That asset is already in this count.")
            else:
                scanned.append(barcode)
                _save_scanned(request, scanned)
                messages.success(request, f"Scanned {asset.name}.")
                return redirect("stocktake_assets")

    in_stock = Asset.objects.filter(status=Asset.Status.IN_STOCK).order_by("location", "name")
    scanned_set = set(scanned)
    return render(
        request,
        "stockroom/stocktake/assets.html",
        {
            "form": form,
            "page_obj": paginate(request, in_stock),
            "scanned": scanned_set,
            "scanned_count": len(scanned_set & set(in_stock.values_list("barcode", flat=True))),
            "expected_count": in_stock.count(),
        },
    )


@role_required(STANDARD, ADMIN)
def stocktake_consumables(request):
    query = request.GET.get("q", "").strip()
    items = Consumable.objects.all()
    if query:
        exact = Consumable.objects.filter(pk=query).first()
        if exact is not None:
            return redirect("consumable_detail", barcode=exact.pk)
        items = items.filter(Q(name__icontains=query) | Q(barcode__icontains=query))
    return render(
        request,
        "stockroom/stocktake/consumables.html",
        {"page_obj": paginate(request, items), "query": query},
    )
