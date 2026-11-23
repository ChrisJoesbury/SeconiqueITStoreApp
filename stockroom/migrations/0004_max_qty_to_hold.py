from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stockroom", "0003_shared_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="max_qty_to_hold",
            field=models.PositiveIntegerField(
                default=0,
                help_text="The most the store should keep of this asset. Zero means there is no maximum.",
                verbose_name="max qty to hold",
            ),
        ),
        migrations.AddField(
            model_name="consumable",
            name="max_qty_to_hold",
            field=models.PositiveIntegerField(
                default=0,
                help_text="The most of this item the store should keep. Zero means there is no maximum.",
                verbose_name="max qty to hold",
            ),
        ),
    ]
