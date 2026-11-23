from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.forms.utils import ErrorDict
from django.utils.safestring import mark_safe
from django.utils import timezone

from .barcodes import barcode_svg
from .forms import BARCODE_RE, _clean_new_barcode
from .models import Asset, Consumable, Usage


class StockError(Exception):
    """A stock movement the store rules do not allow."""


def next_barcode(model, prefix, width=6):
    latest = 0
    codes = model.objects.filter(barcode__startswith=prefix).values_list(
        "barcode", flat=True
    )
    for code in codes:
        suffix = code[len(prefix) :]
        if suffix.isdigit():
            latest = max(latest, int(suffix))
    return f"{prefix}{latest + 1:0{width}d}"


def build_receipt_label(posted, model, prefix):
    """Prepare a printable label before the receipt is saved.

    A blank barcode is allocated from the store sequence. A barcode the user
    typed is kept when it is free. Nothing is written to the database.
    """

    data = posted.copy()
    name = (data.get("name") or "").strip()
    barcode = (data.get("barcode") or "").strip()
    errors = {}
    if not name:
        errors["name"] = "Enter the name before generating a label."
    elif len(name) > 200:
        errors["name"] = "Use at most 200 characters."
    if barcode and "name" not in errors:
        try:
            barcode = _clean_new_barcode(barcode, model)
        except ValidationError as exc:
            errors["barcode"] = " ".join(exc.messages)
    if errors:
        return data, errors, None
    if not barcode:
        barcode = next_barcode(model, prefix)
    data["barcode"] = barcode
    data["name"] = name
    label = {
        "barcode": barcode,
        "description": name,
        "barcode_svg": mark_safe(barcode_svg(barcode)),
    }
    return data, {}, label


def label_from_posted(posted):
    """Rebuild the on-screen label from a receipt that was not saved."""

    barcode = (posted.get("barcode") or "").strip()
    name = (posted.get("name") or "").strip()
    if not barcode or not name or not BARCODE_RE.match(barcode):
        return None
    return {
        "barcode": barcode,
        "description": name,
        "barcode_svg": mark_safe(barcode_svg(barcode)),
    }


def receipt_form_values(posted):
    """Single values from a receipt post, safe to pass as form initial data."""

    return {key: posted.get(key) for key in posted}


def apply_form_errors(form, errors):
    """Attach field errors without validating the rest of a receipt form."""

    form._errors = ErrorDict()
    form.cleaned_data = {}
    for field, message in errors.items():
        form.add_error(field, message)
    return form


def create_asset(form, user):
    supplied = (form.cleaned_data.get("barcode") or "").strip()
    for _attempt in range(3):
        try:
            with transaction.atomic():
                asset = form.save(commit=False)
                asset.barcode = supplied or next_barcode(Asset, "SEC-A-")
                asset.received_by = user
                asset.status = Asset.Status.IN_STOCK
                asset.stocktake_result = Asset.StocktakeResult.NOT_CHECKED
                asset.issued_to = ""
                asset.issued_at = None
                asset.issued_by = None
                asset.save()
                return asset
        except IntegrityError:
            if supplied:
                raise
    raise StockError("A barcode could not be allocated. Submit the form again.")


def issue_asset(asset, issued_to, user):
    issued_to = issued_to.strip()
    if not issued_to:
        raise StockError("Enter the name of the person receiving this asset.")
    with transaction.atomic():
        locked = Asset.objects.select_for_update().get(pk=asset.pk)
        if locked.status != Asset.Status.IN_STOCK:
            raise StockError("Only assets that are in stock can be issued.")
        locked.status = Asset.Status.ISSUED
        locked.issued_to = issued_to
        locked.issued_at = timezone.now()
        locked.issued_by = user
        locked.save()
        return locked


def return_asset(asset):
    with transaction.atomic():
        locked = Asset.objects.select_for_update().get(pk=asset.pk)
        if locked.status != Asset.Status.ISSUED:
            raise StockError("Only issued assets can be returned to the store.")
        locked.status = Asset.Status.IN_STOCK
        locked.issued_to = ""
        locked.issued_at = None
        locked.issued_by = None
        locked.save()
        return locked


def create_consumable(form, user):
    supplied = (form.cleaned_data.get("barcode") or "").strip()
    for _attempt in range(3):
        try:
            with transaction.atomic():
                item = form.save(commit=False)
                item.barcode = supplied or next_barcode(Consumable, "SEC-C-")
                quantity = item.quantity_on_hand
                item.save()
                Usage.objects.create(
                    consumable=item,
                    movement=Usage.Movement.RECEIPT,
                    quantity=quantity,
                    quantity_before=0,
                    quantity_after=quantity,
                    notes="Received as a new consumable.",
                    recorded_by=user,
                )
                return item
        except IntegrityError:
            if supplied:
                raise
    raise StockError("A barcode could not be allocated. Submit the form again.")


def _lock_consumable(consumable):
    return Consumable.objects.select_for_update().get(pk=consumable.pk)


def receive_consumable(consumable, quantity, user, notes=""):
    if quantity < 1:
        raise StockError("Enter a quantity of at least 1.")
    with transaction.atomic():
        locked = _lock_consumable(consumable)
        before = locked.quantity_on_hand
        locked.quantity_on_hand = before + quantity
        locked.save()
        Usage.objects.create(
            consumable=locked,
            movement=Usage.Movement.RECEIPT,
            quantity=quantity,
            quantity_before=before,
            quantity_after=locked.quantity_on_hand,
            notes=notes,
            recorded_by=user,
        )
        return locked


def issue_consumable(consumable, quantity, user, issued_to, notes=""):
    issued_to = issued_to.strip()
    if quantity < 1:
        raise StockError("Enter a quantity of at least 1.")
    if not issued_to:
        raise StockError("Enter who the items were issued to.")
    with transaction.atomic():
        locked = _lock_consumable(consumable)
        if quantity > locked.quantity_on_hand:
            unit = locked.unit or "each"
            raise StockError(
                f"Only {locked.quantity_on_hand} {unit} are in stock."
            )
        before = locked.quantity_on_hand
        locked.quantity_on_hand = before - quantity
        locked.save()
        Usage.objects.create(
            consumable=locked,
            movement=Usage.Movement.ISSUE,
            quantity=quantity,
            quantity_before=before,
            quantity_after=locked.quantity_on_hand,
            issued_to=issued_to,
            notes=notes,
            recorded_by=user,
        )
        return locked


def stocktake_consumable(consumable, counted, user, notes=""):
    if counted < 0:
        raise StockError("Counted quantity cannot be negative.")
    with transaction.atomic():
        locked = _lock_consumable(consumable)
        before = locked.quantity_on_hand
        locked.quantity_on_hand = counted
        locked.save()
        Usage.objects.create(
            consumable=locked,
            movement=Usage.Movement.STOCKTAKE,
            quantity=counted,
            quantity_before=before,
            quantity_after=counted,
            notes=notes,
            recorded_by=user,
        )
        return locked


def complete_asset_stocktake(user, scanned_barcodes):
    now = timezone.now()
    scanned = set(scanned_barcodes)
    found = 0
    missing = 0
    with transaction.atomic():
        in_stock = Asset.objects.select_for_update().filter(status=Asset.Status.IN_STOCK)
        for asset in in_stock:
            asset.last_stocktake_at = now
            asset.last_stocktake_by = user
            if asset.barcode in scanned:
                asset.stocktake_result = Asset.StocktakeResult.FOUND
                found += 1
            else:
                asset.stocktake_result = Asset.StocktakeResult.MISSING
                missing += 1
            asset.save(
                update_fields=[
                    "last_stocktake_at",
                    "last_stocktake_by",
                    "stocktake_result",
                ]
            )
    return found, missing
