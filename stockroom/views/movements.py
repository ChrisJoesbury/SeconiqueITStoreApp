from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..forms import AssetIssueForm, ConsumableIssueForm, ConsumableReceiptForm, ScanForm
from ..models import Asset, Consumable
from ..roles import ADMIN, STANDARD
from ..services import StockError, issue_asset, issue_consumable, receive_consumable
from .common import paginate, role_required


@role_required(STANDARD, ADMIN)
def goods_in(request):
    return render(request, "stockroom/goods/in.html")


@role_required(STANDARD, ADMIN)
def goods_out(request):
    return render(request, "stockroom/goods/out.html")


@role_required(STANDARD, ADMIN)
def goods_out_asset(request):
    form = ScanForm()
    asset = None
    issue_form = AssetIssueForm()
    lookup_error = ""
    query = ""
    if request.method == "POST":
        step = request.POST.get("step")
        if step == "confirm":
            barcode = request.POST.get("barcode", "").strip()
            asset = get_object_or_404(Asset, pk=barcode)
            issue_form = AssetIssueForm(request.POST)
            if issue_form.is_valid():
                try:
                    issue_asset(asset, issue_form.cleaned_data["issued_to"], request.user)
                except StockError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(
                        request,
                        f"{asset.name} issued to {issue_form.cleaned_data['issued_to']}.",
                    )
                    return redirect("asset_detail", barcode=asset.pk)
        else:
            form = ScanForm(request.POST)
            if form.is_valid():
                asset, lookup_error = _asset_ready_to_issue(form.cleaned_data["barcode"])
                if lookup_error:
                    form.add_error("barcode", lookup_error)
                    asset = None
                    lookup_error = ""
    else:
        query = request.GET.get("q", "").strip()
        selected = request.GET.get("barcode", "").strip()
        if not selected and query and Asset.objects.filter(pk=query).exists():
            selected = query
            query = ""
        if selected:
            asset, lookup_error = _asset_ready_to_issue(selected)
    page_obj = None
    if asset is None:
        matches = _asset_matches(query, Asset.objects.filter(status=Asset.Status.IN_STOCK))
        page_obj = paginate(request, matches)
    return render(
        request,
        "stockroom/goods/asset_out.html",
        {
            "form": form,
            "asset": asset,
            "issue_form": issue_form,
            "query": query,
            "page_obj": page_obj,
            "lookup_error": lookup_error,
        },
    )


@role_required(STANDARD, ADMIN)
def goods_out_consumable(request):
    form = ScanForm()
    item = None
    issue_form = None
    lookup_error = ""
    query = ""
    if request.method == "POST":
        step = request.POST.get("step")
        if step == "confirm":
            barcode = request.POST.get("barcode", "").strip()
            item = get_object_or_404(Consumable, pk=barcode)
            issue_form = ConsumableIssueForm(
                request.POST, stock=item.quantity_on_hand, unit=item.unit
            )
            if issue_form.is_valid():
                try:
                    updated = issue_consumable(
                        item,
                        issue_form.cleaned_data["quantity"],
                        request.user,
                        issue_form.cleaned_data["issued_to"],
                        issue_form.cleaned_data["notes"],
                    )
                except StockError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(
                        request,
                        f"Issued {issue_form.cleaned_data['quantity']} {updated.unit} of {updated.name}.",
                    )
                    return redirect("consumable_detail", barcode=updated.pk)
        else:
            form = ScanForm(request.POST)
            if form.is_valid():
                item, lookup_error = _consumable_ready_to_issue(form.cleaned_data["barcode"])
                if lookup_error:
                    form.add_error("barcode", lookup_error)
                    item = None
                    lookup_error = ""
                else:
                    issue_form = ConsumableIssueForm(stock=item.quantity_on_hand, unit=item.unit)
    else:
        query = request.GET.get("q", "").strip()
        selected = request.GET.get("barcode", "").strip()
        if not selected and query and Consumable.objects.filter(pk=query).exists():
            selected = query
            query = ""
        if selected:
            item, lookup_error = _consumable_ready_to_issue(selected)
            if item is not None:
                issue_form = ConsumableIssueForm(stock=item.quantity_on_hand, unit=item.unit)
    page_obj = None
    if item is None:
        matches = _consumable_matches(
            query, Consumable.objects.filter(quantity_on_hand__gt=0)
        )
        page_obj = paginate(request, matches)
    return render(
        request,
        "stockroom/goods/consumable_out.html",
        {
            "form": form,
            "item": item,
            "issue_form": issue_form,
            "query": query,
            "page_obj": page_obj,
            "lookup_error": lookup_error,
        },
    )


@role_required(STANDARD, ADMIN)
def goods_in_consumable(request):
    form = ScanForm()
    item = None
    receipt_form = ConsumableReceiptForm()
    query = ""
    if request.method == "POST":
        step = request.POST.get("step")
        if step == "confirm":
            barcode = request.POST.get("barcode", "").strip()
            item = get_object_or_404(Consumable, pk=barcode)
            receipt_form = ConsumableReceiptForm(request.POST)
            if receipt_form.is_valid():
                try:
                    updated = receive_consumable(
                        item,
                        receipt_form.cleaned_data["quantity"],
                        request.user,
                        receipt_form.cleaned_data["notes"],
                    )
                except StockError as exc:
                    messages.error(request, str(exc))
                else:
                    messages.success(
                        request,
                        f"Received {receipt_form.cleaned_data['quantity']} {updated.unit} of {updated.name}.",
                    )
                    return redirect("consumable_detail", barcode=updated.pk)
        else:
            form = ScanForm(request.POST)
            if form.is_valid():
                barcode = form.cleaned_data["barcode"]
                item = Consumable.objects.filter(pk=barcode).first()
                if item is None:
                    messages.info(
                        request,
                        "That barcode is not in the store yet. Add it as a new consumable.",
                    )
                    return redirect(f"{reverse('consumable_create')}?{urlencode({'barcode': barcode})}")
    else:
        query = request.GET.get("q", "").strip()
        selected = request.GET.get("barcode", "").strip()
        if not selected and query and Consumable.objects.filter(pk=query).exists():
            selected = query
            query = ""
        if selected:
            item = Consumable.objects.filter(pk=selected).first()
    page_obj = None
    if item is None:
        page_obj = paginate(request, _consumable_matches(query, Consumable.objects.all()))
    return render(
        request,
        "stockroom/goods/consumable_in.html",
        {
            "form": form,
            "item": item,
            "receipt_form": receipt_form,
            "query": query,
            "page_obj": page_obj,
        },
    )


def _asset_matches(query, queryset):
    if not query:
        return queryset
    return queryset.filter(
        Q(barcode__icontains=query)
        | Q(name__icontains=query)
        | Q(category__icontains=query)
        | Q(serial_number__icontains=query)
        | Q(model_name__icontains=query)
        | Q(manufacturer__icontains=query)
    )


def _consumable_matches(query, queryset):
    if not query:
        return queryset
    return queryset.filter(
        Q(barcode__icontains=query)
        | Q(name__icontains=query)
        | Q(category__icontains=query)
        | Q(supplier__icontains=query)
    )


def _asset_ready_to_issue(barcode):
    asset = Asset.objects.filter(pk=barcode).first()
    if asset is None:
        return None, "No asset has that barcode."
    if asset.status != Asset.Status.IN_STOCK:
        return None, f"That asset is {asset.get_status_display().lower()} and cannot be issued."
    return asset, ""


def _consumable_ready_to_issue(barcode):
    item = Consumable.objects.filter(pk=barcode).first()
    if item is None:
        return None, "No consumable has that barcode."
    if item.quantity_on_hand < 1:
        return None, "That consumable is out of stock."
    return item, ""
