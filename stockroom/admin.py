from django.contrib import admin

from .models import Asset, AssetCategory, BinLocation, Consumable, Usage, UserSetting


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(BinLocation)
class BinLocationAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "barcode",
        "name",
        "category",
        "status",
        "location",
        "max_qty_to_hold",
        "order_date",
        "eol_date",
    )
    list_filter = ("status", "category", "stocktake_result")
    search_fields = ("barcode", "name", "serial_number", "model_name", "manufacturer", "attributes")


@admin.register(Consumable)
class ConsumableAdmin(admin.ModelAdmin):
    list_display = (
        "barcode",
        "name",
        "category",
        "quantity_on_hand",
        "reorder_level",
        "max_qty_to_hold",
        "unit",
        "location",
    )
    list_filter = ("category",)
    search_fields = ("barcode", "name", "supplier", "attributes")


@admin.register(Usage)
class UsageAdmin(admin.ModelAdmin):
    list_display = (
        "recorded_at",
        "movement",
        "consumable",
        "quantity",
        "quantity_before",
        "quantity_after",
        "issued_to",
        "recorded_by",
    )
    list_filter = ("movement",)
    search_fields = ("consumable__barcode", "consumable__name", "issued_to")


@admin.register(UserSetting)
class UserSettingAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "records_per_page",
        "default_location",
        "eol_warning_days",
        "scanner_auto_submit",
    )
