from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stockroom", "0004_max_qty_to_hold"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="attributes",
            field=models.TextField(
                blank=True,
                help_text="Separate each attribute with a comma, for example: wireless, 16GB, black.",
            ),
        ),
        migrations.AddField(
            model_name="consumable",
            name="attributes",
            field=models.TextField(
                blank=True,
                help_text="Separate each attribute with a comma, for example: HDMI, 2m, black.",
            ),
        ),
    ]
