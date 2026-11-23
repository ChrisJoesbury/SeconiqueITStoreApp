from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from ..barcodes import barcode_svg
from ..forms import (
    AssetCategoryForm,
    AssetCreateForm,
    AssetEditForm,
    AssetIssueForm,
    BinLocationForm,
)
from ..models import Asset, AssetCategory, BinLocation, Consumable, UserSetting, get_settings
from ..roles import ADMIN, STANDARD
from ..services import (
    StockError,
    apply_form_errors,
    build_receipt_label,
    create_asset,
    label_from_posted,
    receipt_form_values,
    issue_asset,
    return_asset,
)
from .common import paginate, role_required


@role_required(STANDARD, ADMIN)
def asset_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query and Asset.objects.filter(pk=query).exists():
        return redirect("asset_detail", barcode=query)

    assets = Asset.objects.all()
    if query:
        assets = assets.filter(
            Q(barcode__icontains=query)
            | Q(name__icontains=query)
            | Q(serial_number__icontains=query)
            | Q(category__icontains=query)
            | Q(model_name__icontains=query)
            | Q(manufacturer__icontains=query)
            | Q(attributes__icontains=query)
        )
    if status in Asset.Status.values:
        assets = assets.filter(status=status)
    return render(
        request,
        "stockroom/assets/list.html",
        {
            "page_obj": paginate(request, assets),
            "query": query,
            "status": status,
            "statuses": Asset.Status.choices,
        },
    )


@role_required(STANDARD, ADMIN)
def asset_detail(request, barcode):
    asset = get_object_or_404(Asset, pk=barcode)
    return render(
        request,
        "stockroom/assets/detail.html",
        {"asset": asset, "issue_form": AssetIssueForm(), "holding": asset.type_holding()},
    )


@role_required(STANDARD, ADMIN)
def asset_create(request):
    prefs = get_settings(request.user)
    label = None
    if request.method == "POST" and request.POST.get("action") == "label":
        data, errors, label = build_receipt_label(request.POST, Asset, "SEC-A-")
        if errors:
            form = apply_form_errors(AssetCreateForm(data), errors)
        else:
            form = AssetCreateForm(initial=receipt_form_values(data))
    elif request.method == "POST":
        form = AssetCreateForm(request.POST)
        if form.is_valid():
            try:
                asset = create_asset(form, request.user)
            except IntegrityError:
                form.add_error("barcode", "That barcode is already in the store.")
            except StockError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"{asset.name} received. Print the label and fix it to the item.",
                )
                return redirect("asset_label", barcode=asset.pk)
        label = label_from_posted(request.POST)
    else:
        form = AssetCreateForm(initial={"location": prefs.default_location})
    return render(
        request,
        "stockroom/assets/form.html",
        {"form": form, "mode": "create", "label": label},
    )


@role_required(ADMIN)
def asset_edit(request, barcode):
    asset = get_object_or_404(Asset, pk=barcode)
    if request.method == "POST":
        form = AssetEditForm(request.POST, instance=asset)
        if form.is_valid():
            updated = form.save(commit=False)
            if updated.status == Asset.Status.ISSUED and updated.issued_by_id is None:
                updated.issued_by = request.user
            updated.save()
            messages.success(request, f"{updated.name} updated.")
            return redirect("asset_detail", barcode=updated.pk)
    else:
        form = AssetEditForm(instance=asset)
    return render(
        request,
        "stockroom/assets/form.html",
        {"form": form, "mode": "edit", "asset": asset},
    )


@role_required(ADMIN)
@require_POST
def asset_delete(request, barcode):
    asset = get_object_or_404(Asset, pk=barcode)
    name = asset.name
    asset.delete()
    messages.success(request, f"{name} deleted.")
    return redirect("asset_list")


@role_required(STANDARD, ADMIN)
@require_POST
def asset_issue(request, barcode):
    asset = get_object_or_404(Asset, pk=barcode)
    form = AssetIssueForm(request.POST)
    if form.is_valid():
        try:
            issue_asset(asset, form.cleaned_data["issued_to"], request.user)
        except StockError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"{asset.name} issued to {form.cleaned_data['issued_to']}.")
    else:
        messages.error(request, "Enter the name of the person receiving this asset.")
    return redirect("asset_detail", barcode=asset.pk)


@role_required(STANDARD, ADMIN)
@require_POST
def asset_return(request, barcode):
    asset = get_object_or_404(Asset, pk=barcode)
    try:
        return_asset(asset)
    except StockError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{asset.name} is back in stock.")
    return redirect("asset_detail", barcode=asset.pk)


@role_required(STANDARD, ADMIN)
def asset_label(request, barcode):
    asset = get_object_or_404(Asset, pk=barcode)
    return render(
        request,
        "stockroom/label.html",
        {
            "heading": "Asset label",
            "description": asset.name,
            "barcode": asset.barcode,
            "barcode_svg": mark_safe(barcode_svg(asset.barcode)),
            "back_url_name": "asset_detail",
        },
    )


@role_required(ADMIN)
def category_list(request):
    categories = []
    for category in AssetCategory.objects.all():
        category.asset_count = Asset.objects.filter(category=category.name).count()
        category.consumable_count = Consumable.objects.filter(category=category.name).count()
        categories.append(category)
    return render(request, "stockroom/assets/categories.html", {"categories": categories})


@role_required(ADMIN)
def category_create(request):
    if request.method == "POST":
        form = AssetCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f"{category.name} added.")
            return redirect("asset_category_list")
    else:
        form = AssetCategoryForm()
    return render(
        request,
        "stockroom/assets/category_form.html",
        {"form": form, "mode": "create"},
    )


@role_required(ADMIN)
def category_edit(request, category_id):
    category = get_object_or_404(AssetCategory, pk=category_id)
    asset_count = Asset.objects.filter(category=category.name).count()
    consumable_count = Consumable.objects.filter(category=category.name).count()
    if request.method == "POST":
        form = AssetCategoryForm(request.POST, instance=category)
        if form.is_valid():
            updated = form.save()
            messages.success(request, f"Category saved as {updated.name}.")
            return redirect("asset_category_list")
    else:
        form = AssetCategoryForm(instance=category)
    return render(
        request,
        "stockroom/assets/category_form.html",
        {
            "form": form,
            "mode": "edit",
            "category": category,
            "asset_count": asset_count,
            "consumable_count": consumable_count,
        },
    )


@role_required(ADMIN)
@require_POST
def category_delete(request, category_id):
    category = get_object_or_404(AssetCategory, pk=category_id)
    asset_count = Asset.objects.filter(category=category.name).count()
    consumable_count = Consumable.objects.filter(category=category.name).count()
    if asset_count or consumable_count:
        used = []
        if asset_count:
            used.append(f"{asset_count} asset" + ("" if asset_count == 1 else "s"))
        if consumable_count:
            used.append(
                f"{consumable_count} consumable" + ("" if consumable_count == 1 else "s")
            )
        messages.error(
            request,
            f"{category.name} is used by {' and '.join(used)}. Change those records before deleting it.",
        )
        return redirect("asset_category_edit", category_id=category.pk)
    name = category.name
    category.delete()
    messages.success(request, f"{name} deleted.")
    return redirect("asset_category_list")


@role_required(ADMIN)
def bin_location_list(request):
    locations = []
    for location in BinLocation.objects.all():
        location.asset_count = Asset.objects.filter(location=location.name).count()
        location.consumable_count = Consumable.objects.filter(location=location.name).count()
        locations.append(location)
    return render(request, "stockroom/locations/list.html", {"locations": locations})


@role_required(ADMIN)
def bin_location_create(request):
    if request.method == "POST":
        form = BinLocationForm(request.POST)
        if form.is_valid():
            location = form.save()
            messages.success(request, f"{location.name} added.")
            return redirect("bin_location_list")
    else:
        form = BinLocationForm()
    return render(
        request,
        "stockroom/locations/form.html",
        {"form": form, "mode": "create"},
    )


@role_required(ADMIN)
def bin_location_edit(request, location_id):
    location = get_object_or_404(BinLocation, pk=location_id)
    asset_count = Asset.objects.filter(location=location.name).count()
    consumable_count = Consumable.objects.filter(location=location.name).count()
    setting_count = UserSetting.objects.filter(default_location=location.name).count()
    if request.method == "POST":
        form = BinLocationForm(request.POST, instance=location)
        if form.is_valid():
            updated = form.save()
            messages.success(request, f"Bin location saved as {updated.name}.")
            return redirect("bin_location_list")
    else:
        form = BinLocationForm(instance=location)
    return render(
        request,
        "stockroom/locations/form.html",
        {
            "form": form,
            "mode": "edit",
            "location": location,
            "asset_count": asset_count,
            "consumable_count": consumable_count,
            "setting_count": setting_count,
        },
    )


@role_required(ADMIN)
@require_POST
def bin_location_delete(request, location_id):
    location = get_object_or_404(BinLocation, pk=location_id)
    asset_count = Asset.objects.filter(location=location.name).count()
    consumable_count = Consumable.objects.filter(location=location.name).count()
    setting_count = UserSetting.objects.filter(default_location=location.name).count()
    if asset_count or consumable_count or setting_count:
        used = []
        if asset_count:
            used.append(f"{asset_count} asset" + ("" if asset_count == 1 else "s"))
        if consumable_count:
            used.append(
                f"{consumable_count} consumable" + ("" if consumable_count == 1 else "s")
            )
        if setting_count:
            used.append(
                f"{setting_count} user setting" + ("" if setting_count == 1 else "s")
            )
        if len(used) == 1:
            detail = used[0]
        elif len(used) == 2:
            detail = f"{used[0]} and {used[1]}"
        else:
            detail = f"{used[0]}, {used[1]} and {used[2]}"
        messages.error(
            request,
            f"{location.name} is used by {detail}. Change those records before deleting it.",
        )
        return redirect("bin_location_edit", location_id=location.pk)
    name = location.name
    location.delete()
    messages.success(request, f"{name} deleted.")
    return redirect("bin_location_list")
