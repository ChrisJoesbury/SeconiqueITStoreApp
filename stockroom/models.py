from django.conf import settings
from django.db import models
from django.db.models import Count, F, Max, Q


def split_attributes(value):
    """Split a comma-separated attribute list, dropping blanks and duplicates."""

    seen = set()
    labels = []
    for part in str(value or "").split(","):
        label = " ".join(part.split())
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return labels


def join_attributes(value):
    return ", ".join(split_attributes(value))


class AssetCategory(models.Model):
    """A name that can be chosen for an asset or a consumable."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "asset_categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class BinLocation(models.Model):
    """A bin that can be chosen for an asset or a consumable."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "bin_locations"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Asset(models.Model):
    """One physical IT asset. The barcode is the primary key."""

    class Status(models.TextChoices):
        IN_STOCK = "in_stock", "In stock"
        ISSUED = "issued", "Issued"
        IN_REPAIR = "in_repair", "In repair"
        RETIRED = "retired", "Retired"

    class StocktakeResult(models.TextChoices):
        NOT_CHECKED = "not_checked", "Not checked"
        FOUND = "found", "Found"
        MISSING = "missing", "Missing"

    barcode = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    attributes = models.TextField(
        blank=True,
        help_text="Separate each attribute with a comma, for example: wireless, 16GB, black.",
    )
    manufacturer = models.CharField(max_length=100, blank=True)
    model_name = models.CharField("model", max_length=100, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    order_date = models.DateField()
    eol_date = models.DateField("end of life")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IN_STOCK
    )
    location = models.CharField("bin location", max_length=100, blank=True)
    max_qty_to_hold = models.PositiveIntegerField(
        "max qty to hold",
        default=0,
        help_text="The most the store should keep of this asset. Zero means there is no maximum.",
    )
    supplier = models.CharField(max_length=200, blank=True)
    purchase_order = models.CharField(max_length=50, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assets_received",
    )
    issued_to = models.CharField(max_length=200, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assets_issued",
    )
    last_stocktake_at = models.DateTimeField(null=True, blank=True)
    last_stocktake_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assets_stocktaken",
    )
    stocktake_result = models.CharField(
        max_length=20,
        choices=StocktakeResult.choices,
        default=StocktakeResult.NOT_CHECKED,
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "assets"
        ordering = ["name", "barcode"]
        constraints = [
            models.CheckConstraint(
                condition=Q(eol_date__gte=F("order_date")),
                name="asset_eol_on_or_after_order_date",
            )
        ]
        indexes = [
            models.Index(fields=["status"], name="asset_status_idx"),
            models.Index(fields=["eol_date"], name="asset_eol_idx"),
            models.Index(fields=["category"], name="asset_category_idx"),
        ]

    def __str__(self):
        return f"{self.barcode} {self.name}"

    @property
    def attribute_list(self):
        return split_attributes(self.attributes)

    @property
    def needs_reorder_attention(self):
        return self.status in {self.Status.IN_STOCK, self.Status.ISSUED}

    @classmethod
    def holding_rows(cls):
        """How many of each asset type are held, compared with max qty to hold.

        Assets that share a name and category are one type. The limit is the
        highest max qty to hold set on assets that are not retired. Retired
        assets are left out of the count. Issued assets are counted separately
        and are not treated as held.
        """

        rows = (
            cls.objects.values("name", "category")
            .annotate(
                held=Count(
                    "pk",
                    filter=Q(status__in=(cls.Status.IN_STOCK, cls.Status.IN_REPAIR)),
                ),
                issued=Count("pk", filter=Q(status=cls.Status.ISSUED)),
                max_qty=Max(
                    "max_qty_to_hold",
                    filter=~Q(status=cls.Status.RETIRED),
                ),
            )
            .filter(max_qty__gt=0)
            .exclude(held=0, issued=0)
            .order_by("category", "name")
        )
        return [cls._prepare_holding(row) for row in rows]

    @staticmethod
    def _prepare_holding(row):
        prepared = dict(row)
        prepared["over_by"] = max(prepared["held"] - prepared["max_qty"], 0)
        prepared["room"] = max(prepared["max_qty"] - prepared["held"], 0)
        prepared["over_max"] = prepared["held"] > prepared["max_qty"]
        return prepared

    def type_holding(self):
        row = next(
            (
                item
                for item in self.holding_rows()
                if item["name"] == self.name and item["category"] == self.category
            ),
            None,
        )
        return row


class Consumable(models.Model):
    """A consumable product identified by one barcode, held as a quantity."""

    barcode = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    attributes = models.TextField(
        blank=True,
        help_text="Separate each attribute with a comma, for example: HDMI, 2m, black.",
    )
    unit = models.CharField(max_length=30, default="each")
    quantity_on_hand = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=0)
    reorder_quantity = models.PositiveIntegerField(default=1)
    max_qty_to_hold = models.PositiveIntegerField(
        "max qty to hold",
        default=0,
        help_text="The most of this item the store should keep. Zero means there is no maximum.",
    )
    location = models.CharField("bin location", max_length=100, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "consumables"
        ordering = ["name", "barcode"]
        indexes = [
            models.Index(fields=["category"], name="consumable_category_idx"),
        ]

    def __str__(self):
        return f"{self.barcode} {self.name}"

    @property
    def attribute_list(self):
        return split_attributes(self.attributes)

    @property
    def needs_reorder(self):
        return self.quantity_on_hand <= self.reorder_level

    @property
    def over_max_hold(self):
        return self.max_qty_to_hold > 0 and self.quantity_on_hand > self.max_qty_to_hold

    @property
    def over_by(self):
        if not self.over_max_hold:
            return 0
        return self.quantity_on_hand - self.max_qty_to_hold

    @property
    def room_to_hold(self):
        if self.max_qty_to_hold < 1:
            return None
        return max(self.max_qty_to_hold - self.quantity_on_hand, 0)

    @property
    def suggested_order(self):
        """Buy quantity when stock is at the reorder level, capped by max hold."""

        if not self.needs_reorder:
            return 0
        order = self.reorder_quantity
        if self.max_qty_to_hold:
            order = min(order, max(self.max_qty_to_hold - self.quantity_on_hand, 0))
        return order

    @property
    def order_was_capped(self):
        return (
            self.max_qty_to_hold > 0
            and self.needs_reorder
            and self.suggested_order < self.reorder_quantity
        )


class Usage(models.Model):
    """A logged movement of a consumable: goods in, goods out, or stocktake."""

    class Movement(models.TextChoices):
        RECEIPT = "receipt", "Goods in"
        ISSUE = "issue", "Goods out"
        STOCKTAKE = "stocktake", "Stocktake"

    consumable = models.ForeignKey(
        Consumable, on_delete=models.PROTECT, related_name="usage_records"
    )
    movement = models.CharField(max_length=20, choices=Movement.choices)
    quantity = models.PositiveIntegerField()
    quantity_before = models.PositiveIntegerField()
    quantity_after = models.PositiveIntegerField()
    issued_to = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="usage_recorded",
    )

    class Meta:
        db_table = "usage"
        ordering = ["-recorded_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(movement="stocktake") | Q(quantity__gt=0),
                name="usage_quantity_positive_unless_stocktake",
            )
        ]
        indexes = [
            models.Index(fields=["movement", "recorded_at"], name="usage_movement_idx"),
            models.Index(fields=["recorded_at"], name="usage_recorded_idx"),
        ]

    def __str__(self):
        return f"{self.get_movement_display()} {self.quantity} {self.consumable_id}"


class UserSetting(models.Model):
    """Preferences stored per user. The database table is named settings."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="stock_settings",
    )
    records_per_page = models.PositiveSmallIntegerField(default=25)
    default_location = models.CharField(
        "default bin location",
        max_length=100,
        blank=True,
        default="Main Store",
    )
    eol_warning_days = models.PositiveSmallIntegerField(default=90)
    scanner_auto_submit = models.BooleanField(
        default=True,
        help_text="Honeywell terminals type a barcode and send Enter. When this is on, a scan form submits at that Enter.",
    )

    class Meta:
        db_table = "settings"

    def __str__(self):
        return f"Settings for {self.user}"


def get_settings(user):
    setting, _created = UserSetting.objects.get_or_create(user=user)
    return setting
