from datetime import timedelta

from django.db.models import F, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from ..models import Asset, Consumable, Usage, get_settings
from ..roles import ADMIN, APP_ROLES, REPORTING
from .common import paginate, role_required


@role_required(ADMIN, REPORTING)
def analytics(request):
    prefs = get_settings(request.user)
    today = timezone.localdate()
    horizon = today + timedelta(days=prefs.eol_warning_days)
    active = [Asset.Status.IN_STOCK, Asset.Status.ISSUED]
    status_counts = []
    for value, label in Asset.Status.choices:
        status_counts.append(
            {
                "label": label,
                "total": Asset.objects.filter(status=value).count(),
            }
        )
    usage_rows = list(
        Usage.objects.filter(movement=Usage.Movement.ISSUE)
        .values("consumable__barcode", "consumable__name", "consumable__unit")
        .annotate(total=Sum("quantity"))
        .order_by("-total")
    )
    peak = usage_rows[0]["total"] if usage_rows else 0
    for row in usage_rows:
        row["width"] = round((row["total"] / peak) * 100) if peak else 0
    holding = Asset.holding_rows()
    over_max_consumables = Consumable.objects.filter(
        max_qty_to_hold__gt=0, quantity_on_hand__gt=F("max_qty_to_hold")
    ).order_by("-quantity_on_hand", "name")
    context = {
        "status_counts": status_counts,
        "asset_total": Asset.objects.count(),
        "eol_assets": Asset.objects.filter(
            status__in=active, eol_date__lte=horizon
        ).order_by("eol_date"),
        "eol_days": prefs.eol_warning_days,
        "missing_assets": Asset.objects.filter(
            status=Asset.Status.IN_STOCK,
            stocktake_result=Asset.StocktakeResult.MISSING,
        ).order_by("name"),
        "low_stock": Consumable.objects.filter(
            quantity_on_hand__lte=F("reorder_level")
        ).order_by("quantity_on_hand", "name"),
        "over_max_consumables": over_max_consumables,
        "over_consumable_count": over_max_consumables.count(),
        "asset_holding": holding,
        "over_asset_count": sum(1 for row in holding if row["over_max"]),
        "usage_rows": usage_rows[:12],
        "recent_issues": Usage.objects.filter(movement=Usage.Movement.ISSUE)
        .select_related("consumable", "recorded_by")
        .order_by("-recorded_at")[:10],
    }
    return render(request, "stockroom/analytics.html", context)


def attribute_catalogue(query=""):
    """Count each attribute and list the assets and consumables that use it.

    Matching ignores letter case. "Wireless" and "wireless" are one attribute,
    shown with the spelling that appears first.
    """

    needle = query.casefold()
    totals = {}
    items = []

    def add_item(kind, obj, holding):
        labels = obj.attribute_list
        if not labels:
            return
        if needle and not any(needle in label.casefold() for label in labels):
            return
        items.append(
            {
                "kind": kind,
                "kind_label": "Asset" if kind == "asset" else "Consumable",
                "barcode": obj.barcode,
                "name": obj.name,
                "category": obj.category,
                "attributes": labels,
                "holding": holding,
            }
        )
        for label in labels:
            if needle and needle not in label.casefold():
                continue
            key = label.casefold()
            row = totals.get(key)
            if row is None:
                row = {"name": label, "asset_count": 0, "consumable_count": 0}
                totals[key] = row
            row[f"{kind}_count"] += 1

    for asset in Asset.objects.order_by("name", "barcode"):
        add_item("asset", asset, asset.get_status_display())
    for item in Consumable.objects.order_by("name", "barcode"):
        add_item(
            "consumable",
            item,
            f"{item.quantity_on_hand} {item.unit}",
        )

    summary = sorted(totals.values(), key=lambda row: row["name"].casefold())
    for row in summary:
        row["total"] = row["asset_count"] + row["consumable_count"]
    items.sort(key=lambda row: (row["name"].casefold(), row["kind"], row["barcode"]))
    return summary, items


@role_required(*APP_ROLES)
def attribute_report(request):
    query = request.GET.get("q", "").strip()
    selected = request.GET.get("attribute", "").strip()
    summary, items = attribute_catalogue(query)
    selected_label = ""
    if selected:
        key = selected.casefold()
        match = next((row for row in summary if row["name"].casefold() == key), None)
        selected_label = match["name"] if match else selected
        items = [
            row
            for row in items
            if any(label.casefold() == key for label in row["attributes"])
        ]
    return render(
        request,
        "stockroom/reports/attributes.html",
        {
            "summary": summary,
            "page_obj": paginate(request, items),
            "query": query,
            "selected": selected_label,
            "attribute": selected_label,
            "item_count": len(items),
        },
    )


def store_contents_rows(query="", kind=""):
    """Items physically in the IT store, marked as an asset or a consumable.

    An asset counts when it is in stock. A consumable counts when a quantity
    is on hand. Issued, in-repair and retired assets are left out, as are
    consumables with nothing on the shelf.
    """

    rows = []
    if kind in ("", "asset"):
        assets = Asset.objects.filter(status=Asset.Status.IN_STOCK)
        if query:
            assets = assets.filter(
                Q(barcode__icontains=query)
                | Q(name__icontains=query)
                | Q(category__icontains=query)
                | Q(location__icontains=query)
                | Q(serial_number__icontains=query)
                | Q(attributes__icontains=query)
            )
        for asset in assets:
            rows.append(
                {
                    "kind": "asset",
                    "kind_label": "Asset",
                    "barcode": asset.barcode,
                    "name": asset.name,
                    "category": asset.category,
                    "quantity": "1",
                    "location": asset.location,
                    "attributes": asset.attribute_list,
                }
            )
    if kind in ("", "consumable"):
        items = Consumable.objects.filter(quantity_on_hand__gt=0)
        if query:
            items = items.filter(
                Q(barcode__icontains=query)
                | Q(name__icontains=query)
                | Q(category__icontains=query)
                | Q(location__icontains=query)
                | Q(attributes__icontains=query)
            )
        for item in items:
            rows.append(
                {
                    "kind": "consumable",
                    "kind_label": "Consumable",
                    "barcode": item.barcode,
                    "name": item.name,
                    "category": item.category,
                    "quantity": f"{item.quantity_on_hand} {item.unit}",
                    "location": item.location,
                    "attributes": item.attribute_list,
                }
            )
    rows.sort(key=lambda row: (row["name"].casefold(), row["kind"], row["barcode"]))
    return rows


@role_required(*APP_ROLES)
def store_contents(request):
    query = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "").strip()
    if kind not in ("asset", "consumable"):
        kind = ""
    rows = store_contents_rows(query, kind)
    return render(
        request,
        "stockroom/reports/contents.html",
        {
            "page_obj": paginate(request, rows),
            "query": query,
            "kind": kind,
            "asset_count": sum(1 for row in rows if row["kind"] == "asset"),
            "consumable_count": sum(1 for row in rows if row["kind"] == "consumable"),
        },
    )


@role_required(*APP_ROLES)
def usage_list(request):
    movement = request.GET.get("movement", "").strip()
    query = request.GET.get("q", "").strip()
    records = Usage.objects.select_related("consumable", "recorded_by")
    if movement in Usage.Movement.values:
        records = records.filter(movement=movement)
    if query:
        records = records.filter(
            Q(consumable__barcode__icontains=query)
            | Q(consumable__name__icontains=query)
            | Q(issued_to__icontains=query)
        )
    return render(
        request,
        "stockroom/usage/list.html",
        {
            "page_obj": paginate(request, records),
            "query": query,
            "movement": movement,
            "movements": Usage.Movement.choices,
        },
    )
