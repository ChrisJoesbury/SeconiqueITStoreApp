import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UsernameField
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import transaction
from django.utils import timezone

from .models import Asset, AssetCategory, BinLocation, Consumable, UserSetting, join_attributes
from .roles import ADMIN, ALL, ASSIGNEE, primary_role, set_store_role

BARCODE_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
BARCODE_RE = re.compile(rf"^{BARCODE_PATTERN}$")
BARCODE_HELP = "Letters, numbers, dots, underscores or hyphens. Maximum 64 characters."
ASSET_MAX_HOLD_HELP = (
    "The most of this asset the store should keep. Use 0 for no maximum. "
    "Analytics groups assets with the same name and category."
)
CONSUMABLE_MAX_HOLD_HELP = (
    "The most of this item the store should keep. Use 0 for no maximum. "
    "Reorder suggestions stop at this quantity."
)
ATTRIBUTES_HELP = "Separate each attribute with a comma, for example: wireless, 16GB, black."


def _configure_attributes(form):
    field = form.fields["attributes"]
    field.required = False
    field.help_text = ATTRIBUTES_HELP
    field.widget.attrs["placeholder"] = "wireless, 16GB, black"


def _clean_attributes(value):
    return join_attributes(value)


def _configure_max_hold(form, help_text):
    field = form.fields["max_qty_to_hold"]
    field.required = False
    field.label = "Max qty to hold"
    field.help_text = help_text
    field.widget.attrs["min"] = 0


def _store_max_hold(cleaned):
    if cleaned.get("max_qty_to_hold") in (None, ""):
        cleaned["max_qty_to_hold"] = 0
    return cleaned


def _validate_consumable_max_hold(form, cleaned):
    _store_max_hold(cleaned)
    maximum = cleaned.get("max_qty_to_hold") or 0
    reorder = cleaned.get("reorder_level")
    if maximum and reorder is not None and maximum <= reorder:
        form.add_error(
            "max_qty_to_hold",
            "Max qty to hold must be higher than the reorder level, or 0 for no maximum.",
        )
    return cleaned


def _style(form):
    for field in form.fields.values():
        css = field.widget.attrs.get("class", "")
        if "input" not in css.split():
            field.widget.attrs["class"] = f"{css} input".strip()
    return form


def _barcode_widget(scan_mode):
    return forms.TextInput(
        attrs={
            "autocomplete": "off",
            "autocapitalize": "off",
            "spellcheck": "false",
            "class": "input barcode-input",
            "data-scan-mode": scan_mode,
            "placeholder": "Scan or type",
            "autofocus": True,
            "pattern": BARCODE_PATTERN,
            "data-pattern-message": BARCODE_HELP,
            "maxlength": "64",
        }
    )


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)


class StyledForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)


class StoreLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)
        self.fields["username"].widget.attrs["autofocus"] = True

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if primary_role(user) == ASSIGNEE:
            raise ValidationError(
                "This account cannot sign in. It is only used when equipment is issued.",
                code="no_access",
            )


class AssetCreateForm(StyledModelForm):
    category = forms.ChoiceField(label="Category")
    location = forms.ChoiceField(label="Bin location")
    barcode = forms.CharField(
        required=False,
        max_length=64,
        label="Barcode",
        widget=_barcode_widget("next"),
        help_text="Leave blank to allocate a store barcode when the label is generated.",
    )

    class Meta:
        model = Asset
        fields = [
            "barcode",
            "name",
            "category",
            "attributes",
            "manufacturer",
            "model_name",
            "serial_number",
            "order_date",
            "eol_date",
            "location",
            "max_qty_to_hold",
            "supplier",
            "purchase_order",
            "notes",
        ]
        widgets = {
            "order_date": forms.DateInput(attrs={"type": "date"}),
            "eol_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "data-not-before": "id_order_date",
                    "data-not-before-message": "End of life must be on or after the order date.",
                }
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "attributes": forms.TextInput(),
        }
        help_texts = {
            "eol_date": "Used when planning replacement purchases.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = category_choices()
        _configure_max_hold(self, ASSET_MAX_HOLD_HELP)
        _configure_attributes(self)
        self.fields["location"].choices = location_choices(self.initial.get("location") or "")

    def clean_barcode(self):
        return _clean_new_barcode(self.cleaned_data.get("barcode"), Asset)

    def clean_attributes(self):
        return _clean_attributes(self.cleaned_data.get("attributes"))

    def clean(self):
        cleaned = super().clean()
        _validate_dates(self, cleaned.get("order_date"), cleaned.get("eol_date"))
        return _store_max_hold(cleaned)


class AssetEditForm(StyledModelForm):
    category = forms.ChoiceField(label="Category")
    location = forms.ChoiceField(label="Bin location")
    issued_to = forms.ChoiceField(required=False, label="Issued to")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_category = self.instance.category if getattr(self.instance, "pk", None) else ""
        self.fields["category"].choices = category_choices(current_category)
        current = self.instance.issued_to if getattr(self.instance, "pk", None) else ""
        self.fields["issued_to"].choices = assignee_choices(current)
        self.fields["issued_to"].help_text = ASSIGNEE_HELP
        self.fields["issued_to"].widget.attrs["data-required-when-field"] = "id_status"
        self.fields["issued_to"].widget.attrs["data-required-when-value"] = Asset.Status.ISSUED
        _configure_max_hold(self, ASSET_MAX_HOLD_HELP)
        _configure_attributes(self)
        current_location = self.instance.location if getattr(self.instance, "pk", None) else ""
        self.fields["location"].choices = location_choices(current_location)

    class Meta:
        model = Asset
        fields = [
            "name",
            "category",
            "attributes",
            "manufacturer",
            "model_name",
            "serial_number",
            "order_date",
            "eol_date",
            "status",
            "location",
            "max_qty_to_hold",
            "supplier",
            "purchase_order",
            "issued_to",
            "notes",
        ]
        widgets = {
            "order_date": forms.DateInput(attrs={"type": "date"}),
            "eol_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "data-not-before": "id_order_date",
                    "data-not-before-message": "End of life must be on or after the order date.",
                }
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "attributes": forms.TextInput(),
        }

    def clean(self):
        cleaned = super().clean()
        _validate_dates(self, cleaned.get("order_date"), cleaned.get("eol_date"))
        status = cleaned.get("status")
        issued_to = (cleaned.get("issued_to") or "").strip()
        if status == Asset.Status.ISSUED and not issued_to:
            self.add_error("issued_to", "Select the assignee who has this asset.")
        cleaned["issued_to"] = issued_to
        return _store_max_hold(cleaned)

    def clean_attributes(self):
        return _clean_attributes(self.cleaned_data.get("attributes"))

    def save(self, commit=True):
        asset = super().save(commit=False)
        if asset.status == Asset.Status.IN_STOCK:
            asset.issued_to = ""
            asset.issued_at = None
            asset.issued_by = None
        elif asset.status == Asset.Status.ISSUED and asset.issued_at is None:
            asset.issued_at = timezone.now()
        if commit:
            asset.save()
        return asset


class ConsumableCreateForm(StyledModelForm):
    category = forms.ChoiceField(label="Category")
    location = forms.ChoiceField(label="Bin location")
    barcode = forms.CharField(
        required=False,
        max_length=64,
        label="Barcode",
        widget=_barcode_widget("next"),
        help_text="Leave blank to allocate a store barcode when the label is generated.",
    )
    quantity_on_hand = forms.IntegerField(
        min_value=1,
        label="Quantity received",
        widget=forms.NumberInput(attrs={"min": 1}),
    )

    class Meta:
        model = Consumable
        fields = [
            "barcode",
            "name",
            "category",
            "attributes",
            "unit",
            "quantity_on_hand",
            "reorder_level",
            "reorder_quantity",
            "max_qty_to_hold",
            "location",
            "supplier",
            "notes",
        ]
        widgets = {
            "unit": forms.TextInput(attrs={"list": "consumable-units"}),
            "reorder_level": forms.NumberInput(attrs={"min": 0}),
            "reorder_quantity": forms.NumberInput(attrs={"min": 1}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "attributes": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = category_choices()
        _configure_max_hold(self, CONSUMABLE_MAX_HOLD_HELP)
        _configure_attributes(self)
        self.fields["location"].choices = location_choices(self.initial.get("location") or "")

    def clean_barcode(self):
        return _clean_new_barcode(self.cleaned_data.get("barcode"), Consumable)

    def clean_attributes(self):
        return _clean_attributes(self.cleaned_data.get("attributes"))

    def clean_reorder_quantity(self):
        value = self.cleaned_data["reorder_quantity"]
        if value < 1:
            raise forms.ValidationError("Reorder quantity must be at least 1.")
        return value

    def clean(self):
        cleaned = super().clean()
        return _validate_consumable_max_hold(self, cleaned)


class ConsumableEditForm(StyledModelForm):
    category = forms.ChoiceField(label="Category")
    location = forms.ChoiceField(label="Bin location")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance.category if getattr(self.instance, "pk", None) else ""
        self.fields["category"].choices = category_choices(current)
        _configure_max_hold(self, CONSUMABLE_MAX_HOLD_HELP)
        _configure_attributes(self)
        current_location = self.instance.location if getattr(self.instance, "pk", None) else ""
        self.fields["location"].choices = location_choices(current_location)

    class Meta:
        model = Consumable
        fields = [
            "name",
            "category",
            "attributes",
            "unit",
            "reorder_level",
            "reorder_quantity",
            "max_qty_to_hold",
            "location",
            "supplier",
            "notes",
        ]
        widgets = {
            "unit": forms.TextInput(attrs={"list": "consumable-units"}),
            "reorder_level": forms.NumberInput(attrs={"min": 0}),
            "reorder_quantity": forms.NumberInput(attrs={"min": 1}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "attributes": forms.TextInput(),
        }

    def clean_reorder_quantity(self):
        value = self.cleaned_data["reorder_quantity"]
        if value < 1:
            raise forms.ValidationError("Reorder quantity must be at least 1.")
        return value

    def clean_attributes(self):
        return _clean_attributes(self.cleaned_data.get("attributes"))

    def clean(self):
        cleaned = super().clean()
        return _validate_consumable_max_hold(self, cleaned)


class ScanForm(StyledForm):
    barcode = forms.CharField(
        max_length=64,
        label="Barcode",
        widget=_barcode_widget("submit"),
        help_text="Scan with a Honeywell terminal, or type the barcode.",
    )

    def clean_barcode(self):
        return _require_barcode(self.cleaned_data.get("barcode"))


class AssetIssueForm(StyledForm):
    issued_to = forms.ChoiceField(label="Issued to")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["issued_to"].choices = assignee_choices()
        self.fields["issued_to"].help_text = ASSIGNEE_HELP


class ConsumableReceiptForm(StyledForm):
    quantity = forms.IntegerField(
        min_value=1, label="Quantity received", widget=forms.NumberInput(attrs={"min": 1})
    )
    notes = forms.CharField(
        required=False, label="Notes", widget=forms.Textarea(attrs={"rows": 3})
    )


class ConsumableIssueForm(StyledForm):
    quantity = forms.IntegerField(
        min_value=1, label="Quantity issued", widget=forms.NumberInput(attrs={"min": 1})
    )
    issued_to = forms.ChoiceField(label="Issued to")
    notes = forms.CharField(
        required=False, label="Notes", widget=forms.Textarea(attrs={"rows": 3})
    )

    def __init__(self, *args, stock=None, unit="each", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["issued_to"].choices = assignee_choices()
        self.fields["issued_to"].help_text = ASSIGNEE_HELP
        if stock is not None:
            self.fields["quantity"].widget.attrs["max"] = stock
            self.fields["quantity"].widget.attrs["data-overflow-message"] = (
                f"Only {stock} {unit} are in stock."
            )
            self.fields["quantity"].help_text = f"{stock} {unit} currently in stock."

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        stock = self.fields["quantity"].widget.attrs.get("max")
        if stock is not None and quantity > int(stock):
            unit = self.fields["quantity"].help_text
            raise forms.ValidationError(f"That is more than the quantity in stock. {unit}")
        return quantity


class ConsumableCountForm(StyledForm):
    counted = forms.IntegerField(
        min_value=0,
        label="Counted quantity",
        widget=forms.NumberInput(attrs={"min": 0}),
    )
    notes = forms.CharField(
        required=False, label="Notes", widget=forms.Textarea(attrs={"rows": 2})
    )


class StoreUserForm(StyledForm):
    username = UsernameField(
        max_length=150,
        label="Username",
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "off"}),
    )
    first_name = forms.CharField(max_length=150, required=False, label="First name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")
    email = forms.EmailField(required=False, label="Email")
    role = forms.ChoiceField(choices=[(name, name) for name in ALL], label="Role")
    is_active = forms.BooleanField(
        required=False,
        initial=True,
        label="Active",
        help_text="Inactive accounts cannot sign in. Their stock history is kept.",
    )
    password = forms.CharField(
        required=False,
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "minlength": "8",
                "data-required-unless-field": "id_role",
                "data-required-unless-value": ASSIGNEE,
            }
        ),
    )
    password_confirm = forms.CharField(
        required=False,
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "data-must-match": "id_password",
                "data-must-match-message": "Enter the same password in both fields.",
                "data-required-unless-field": "id_role",
                "data-required-unless-value": ASSIGNEE,
            }
        ),
    )

    def __init__(self, *args, user=None, actor=None, **kwargs):
        self.user = user
        self.actor = actor
        super().__init__(*args, **kwargs)
        self.fields["role"].help_text = (
            "Assignees are people equipment is issued to. They cannot sign in."
        )
        if user is None:
            self.fields["password"].help_text = (
                "At least 8 characters. Leave blank for an Assignee, because they cannot sign in."
            )
        else:
            self.fields["password"].help_text = "Leave blank to keep the current password."
        if user is not None and user.is_superuser:
            self.fields["role"].help_text = (
                "This account is a superuser, so it keeps Admin access whatever role is selected."
            )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        taken = get_user_model().objects.filter(username__iexact=username)
        if self.user is not None:
            taken = taken.exclude(pk=self.user.pk)
        if taken.exists():
            raise forms.ValidationError("That username is already in use.")
        return username

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password") or ""
        confirm = cleaned.get("password_confirm") or ""
        if password or confirm:
            if password != confirm:
                self.add_error("password_confirm", "Enter the same password in both fields.")
            elif password:
                candidate = self.user or get_user_model()()
                candidate.username = cleaned.get("username") or candidate.username
                candidate.first_name = cleaned.get("first_name") or ""
                candidate.last_name = cleaned.get("last_name") or ""
                candidate.email = cleaned.get("email") or ""
                try:
                    validate_password(password, candidate)
                except ValidationError as exc:
                    self.add_error("password", exc)
        elif self.user is None and cleaned.get("role") not in (None, ASSIGNEE):
            self.add_error("password", "Enter a password.")

        role = cleaned.get("role")
        active = bool(cleaned.get("is_active"))
        if self.user is not None and self._removes_last_admin(role, active):
            self.add_error(
                None,
                "Keep at least one active Admin. This is the only one.",
            )
        if self.user is not None and self.actor is not None and self.user.pk == self.actor.pk:
            if not active:
                self.add_error("is_active", "You cannot deactivate your own account.")
            if role and role != ADMIN:
                self.add_error("role", "You cannot remove your own Admin role.")
        return cleaned

    def _removes_last_admin(self, role, active):
        user = self.user
        still_admin = active and (user.is_superuser or role == ADMIN)
        if still_admin or not _is_active_admin(user):
            return False
        others = get_user_model().objects.filter(is_active=True).filter(
            Q(is_superuser=True) | Q(groups__name=ADMIN)
        ).exclude(pk=user.pk)
        return not others.exists()

    def save(self):
        data = self.cleaned_data
        user = self.user or get_user_model()()
        user.username = data["username"]
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]
        user.email = data["email"]
        user.is_active = bool(data["is_active"])
        if data.get("password"):
            user.set_password(data["password"])
        elif self.user is None:
            user.set_unusable_password()
        user.save()
        set_store_role(user, data["role"])
        return user


class AssetCategoryForm(StyledModelForm):
    class Meta:
        model = AssetCategory
        fields = ["name"]

    def clean_name(self):
        name = " ".join((self.cleaned_data.get("name") or "").split())
        if not name:
            raise forms.ValidationError("Enter a category name.")
        taken = AssetCategory.objects.filter(name__iexact=name)
        if self.instance.pk:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("That category already exists.")
        return name

    @transaction.atomic
    def save(self, commit=True):
        previous = ""
        if self.instance.pk:
            previous = AssetCategory.objects.get(pk=self.instance.pk).name
        category = super().save(commit=commit)
        if commit and previous and previous != category.name:
            Asset.objects.filter(category=previous).update(category=category.name)
            Consumable.objects.filter(category=previous).update(category=category.name)
        return category


class BinLocationForm(StyledModelForm):
    class Meta:
        model = BinLocation
        fields = ["name"]

    def clean_name(self):
        name = " ".join((self.cleaned_data.get("name") or "").split())
        if not name:
            raise forms.ValidationError("Enter a bin location name.")
        taken = BinLocation.objects.filter(name__iexact=name)
        if self.instance.pk:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("That bin location already exists.")
        return name

    @transaction.atomic
    def save(self, commit=True):
        previous = ""
        if self.instance.pk:
            previous = BinLocation.objects.get(pk=self.instance.pk).name
        location = super().save(commit=commit)
        if commit and previous and previous != location.name:
            Asset.objects.filter(location=previous).update(location=location.name)
            Consumable.objects.filter(location=previous).update(location=location.name)
            UserSetting.objects.filter(default_location=previous).update(
                default_location=location.name
            )
        return location


ASSIGNEE_HELP = "Only Assignee accounts can be issued stock. They cannot sign in."


def category_choices(current=""):
    names = list(AssetCategory.objects.order_by("name").values_list("name", flat=True))
    if current and current not in names:
        names.append(current)
        names.sort(key=str.casefold)
    if not names:
        return [("", "Add a category first")]
    return [("", "Select a category")] + [(name, name) for name in names]


def location_choices(current=""):
    names = list(BinLocation.objects.order_by("name").values_list("name", flat=True))
    if current and current not in names:
        names.append(current)
        names.sort(key=str.casefold)
    if not names:
        return [("", "Add a bin location first")]
    return [("", "Select a bin location")] + [(name, name) for name in names]


def assignee_choices(current=""):
    people = list(
        get_user_model()
        .objects.filter(is_active=True, groups__name=ASSIGNEE)
        .order_by("first_name", "last_name", "username")
    )
    counts = {}
    for person in people:
        label = person.get_full_name().strip() or person.get_username()
        counts[label.casefold()] = counts.get(label.casefold(), 0) + 1
    choices = []
    for person in people:
        label = person.get_full_name().strip() or person.get_username()
        if counts[label.casefold()] > 1:
            label = f"{label} ({person.get_username()})"
        choices.append((label, label))
    if current and current not in {value for value, _label in choices}:
        choices.insert(0, (current, current))
    if not choices and not current:
        return [("", "Add an Assignee user first")]
    return [("", "Select an assignee")] + choices


def _is_active_admin(user):
    if not user.is_active:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=ADMIN).exists()


class UserSettingForm(StyledModelForm):
    records_per_page = forms.IntegerField(
        min_value=5,
        max_value=100,
        label="Records per page",
        widget=forms.NumberInput(attrs={"min": 5, "max": 100}),
    )
    default_location = forms.ChoiceField(
        label="Default bin location",
        help_text="Used when receiving an asset or a consumable.",
    )
    eol_warning_days = forms.IntegerField(
        min_value=0,
        max_value=3650,
        label="End-of-life warning (days)",
        widget=forms.NumberInput(attrs={"min": 0, "max": 3650}),
        help_text="Analytics highlights assets that reach end of life inside this window.",
    )

    class Meta:
        model = UserSetting
        fields = [
            "records_per_page",
            "default_location",
            "eol_warning_days",
            "scanner_auto_submit",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = ""
        if getattr(self.instance, "pk", None):
            current = self.instance.default_location or ""
        self.fields["default_location"].choices = location_choices(current)


def _require_barcode(value):
    value = (value or "").strip()
    if not value:
        raise forms.ValidationError("Scan or enter a barcode.")
    if not BARCODE_RE.match(value):
        raise forms.ValidationError(BARCODE_HELP)
    return value


def _clean_new_barcode(value, model):
    value = (value or "").strip()
    if not value:
        return ""
    if not BARCODE_RE.match(value):
        raise forms.ValidationError(BARCODE_HELP)
    if model.objects.filter(pk=value).exists():
        raise forms.ValidationError("That barcode is already in the store.")
    return value


def _validate_dates(form, order_date, eol_date):
    if order_date and eol_date and eol_date < order_date:
        form.add_error("eol_date", "End of life must be on or after the order date.")
