from django.db import migrations


CONSUMABLE_NAMES = (
    "Cable",
    "Adapter",
    "Toner",
    "Battery",
    "Keyboard",
    "Mouse",
    "Storage media",
    "Stationery",
)


def add_consumable_categories(apps, schema_editor):
    Category = apps.get_model("stockroom", "AssetCategory")
    Consumable = apps.get_model("stockroom", "Consumable")
    names = set(CONSUMABLE_NAMES)
    names.update(name for name in Consumable.objects.values_list("category", flat=True) if name)
    for name in sorted(names, key=str.casefold):
        Category.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("stockroom", "0002_asset_categories"),
    ]

    operations = [
        migrations.RunPython(add_consumable_categories, migrations.RunPython.noop),
    ]
