from django.contrib import messages
from django.db import IntegrityError
from django.db.models import F, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from ..barcodes import barcode_svg
from ..forms import (
    ConsumableCountForm,
    ConsumableCreateForm,
    ConsumableEditForm,
    ConsumableIssueForm,
    ConsumableReceiptForm,
)
from ..models import Consumable, get_settings
from ..roles import ADMIN, STANDARD
from ..services import (
    StockError,
    apply_form_errors,
    build_receipt_label,
    create_consumable,
    label_from_posted,
    receipt_form_values,
    issue_consumable,
    receive_consumable,
    stocktake_consumable,
)
from .common import paginate, role_required


@role_required(STANDARD, ADMIN)
def consumable_list(request):
    query = request.GET.get("q", "").strip()
    if query and Consumable.objects.filter(pk=query).exists():
        return redirect("consumable_detail", barcode=query)

    items = Consumable.objects.all()
    if query:
        items = items.filter(
            Q(barcode__icontains=query)
            | Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(supplier__icontains=query)
            | Q(attributes__icontains=query)
        )
    low_only = request.GET.get("low") == "1"
    over_only = request.GET.get("over") == "1"
    if low_only:
        items = items.filter(quantity_on_hand__lte=F("reorder_level"))
    elif over_only:
        items = items.filter(
            max_qty_to_hold__gt=0, quantity_on_hand__gt=F("max_qty_to_hold")
        )
    return render(
        request,
        "stockroom/consumables/list.html",
        {
            "page_obj": paginate(request, items),
            "query": query,
            "low_only": low_only,
            "over_only": over_only,
        },
    )


@role_required(STANDARD, ADMIN)
def consumable_detail(request, barcode):
    item = get_object_or_404(Consumable, pk=barcode)
    return render(
        request,
        "stockroom/consumables/detail.html",
        {
            "item": item,
            "receipt_form": ConsumableReceiptForm(),
            "issue_form": ConsumableIssueForm(stock=item.quantity_on_hand, unit=item.unit),
            "count_form": ConsumableCountForm(initial={"counted": item.quantity_on_hand}),
        },
    )


@role_required(STANDARD, ADMIN)
def consumable_create(request):
    prefs = get_settings(request.user)
    label = None
    if request.method == "POST" and request.POST.get("action") == "label":
        data, errors, label = build_receipt_label(request.POST, Consumable, "SEC-C-")
        if errors:
            form = apply_form_errors(ConsumableCreateForm(data), errors)
        else:
            form = ConsumableCreateForm(initial=receipt_form_values(data))
    elif request.method == "POST":
        form = ConsumableCreateForm(request.POST)
        if form.is_valid():
            try:
                item = create_consumable(form, request.user)
            except IntegrityError:
                form.add_error("barcode", "That barcode is already in the store.")
            except StockError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"{item.name} received. Print the label and fix it to the bin or pack.",
                )
                return redirect("consumable_label", barcode=item.pk)
        label = label_from_posted(request.POST)
    else:
        form = ConsumableCreateForm(
            initial={
                "location": prefs.default_location,
                "barcode": request.GET.get("barcode", ""),
                "unit": "each",
                "reorder_quantity": 1,
            }
        )
    return render(
        request,
        "stockroom/consumables/form.html",
        {"form": form, "mode": "create", "label": label},
    )


@role_required(ADMIN)
def consumable_edit(request, barcode):
    item = get_object_or_404(Consumable, pk=barcode)
    if request.method == "POST":
        form = ConsumableEditForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"{item.name} updated.")
            return redirect("consumable_detail", barcode=item.pk)
    else:
        form = ConsumableEditForm(instance=item)
    return render(
        request,
        "stockroom/consumables/form.html",
        {"form": form, "mode": "edit", "item": item},
    )


@role_required(ADMIN)
@require_POST
def consumable_delete(request, barcode):
    item = get_object_or_404(Consumable, pk=barcode)
    name = item.name
    try:
        item.delete()
    except ProtectedError:
        messages.error(
            request,
            f"{name} has usage history, so it cannot be deleted. Correct the record instead.",
        )
        return redirect("consumable_detail", barcode=barcode)
    messages.success(request, f"{name} deleted.")
    return redirect("consumable_list")


@role_required(STANDARD, ADMIN)
@require_POST
def consumable_receive(request, barcode):
    item = get_object_or_404(Consumable, pk=barcode)
    form = ConsumableReceiptForm(request.POST)
    if form.is_valid():
        try:
            updated = receive_consumable(
                item,
                form.cleaned_data["quantity"],
                request.user,
                form.cleaned_data["notes"],
            )
        except StockError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Received {form.cleaned_data['quantity']} {updated.unit}. On hand is now {updated.quantity_on_hand}.",
            )
    else:
        messages.error(request, "Enter a received quantity of at least 1.")
    return redirect("consumable_detail", barcode=item.pk)


@role_required(STANDARD, ADMIN)
@require_POST
def consumable_issue(request, barcode):
    item = get_object_or_404(Consumable, pk=barcode)
    form = ConsumableIssueForm(request.POST, stock=item.quantity_on_hand, unit=item.unit)
    if form.is_valid():
        try:
            updated = issue_consumable(
                item,
                form.cleaned_data["quantity"],
                request.user,
                form.cleaned_data["issued_to"],
                form.cleaned_data["notes"],
            )
        except StockError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Issued {form.cleaned_data['quantity']} {updated.unit} to {form.cleaned_data['issued_to']}.",
            )
    else:
        messages.error(request, "Check the quantity and who it was issued to.")
    return redirect("consumable_detail", barcode=item.pk)


@role_required(STANDARD, ADMIN)
@require_POST
def consumable_count(request, barcode):
    item = get_object_or_404(Consumable, pk=barcode)
    form = ConsumableCountForm(request.POST)
    if form.is_valid():
        try:
            updated = stocktake_consumable(
                item,
                form.cleaned_data["counted"],
                request.user,
                form.cleaned_data["notes"],
            )
        except StockError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Stocktake saved for {updated.name}. On hand is now {updated.quantity_on_hand}.",
            )
    else:
        messages.error(request, "Enter the counted quantity. Zero is allowed.")
    return redirect("consumable_detail", barcode=item.pk)


@role_required(STANDARD, ADMIN)
def consumable_label(request, barcode):
    item = get_object_or_404(Consumable, pk=barcode)
    return render(
        request,
        "stockroom/label.html",
        {
            "heading": "Consumable label",
            "description": item.name,
            "barcode": item.barcode,
            "barcode_svg": mark_safe(barcode_svg(item.barcode)),
            "back_url_name": "consumable_detail",
        },
    )
