from django.apps import AppConfig
from django.urls import register_converter


class StockroomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "stockroom"
    verbose_name = "IT stockroom"

    def ready(self):
        from .converters import BarcodeConverter

        register_converter(BarcodeConverter, "barcode")
        from . import signals

        signals.connect_user_settings()
