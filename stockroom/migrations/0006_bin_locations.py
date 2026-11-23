from django.db import migrations, models


DEFAULT_BINS = (
    "Disposal cage",
    "Goods In",
    "Goods Out",
    "Main Store",
    "Server Room",
)


def seed_bin_locations(apps, schema_editor):
    BinLocation = apps.get_model("stockroom", "BinLocation")
    Asset = apps.get_model("stockroom", "Asset")
    Consumable = apps.get_model("stockroom", "Consumable")
    UserSetting = apps.get_model("stockroom", "UserSetting")
    names = set(DEFAULT_BINS)
    names.update(name for name in Asset.objects.values_list("location", flat=True) if name)
    names.update(name for name in Consumable.objects.values_list("location", flat=True) if name)
    names.update(
        name for name in UserSetting.objects.values_list("default_location", flat=True) if name
    )
    for name in sorted(names, key=str.casefold):
        BinLocation.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("stockroom", "0005_attributes"),
    ]

    operations = [
        migrations.CreateModel(
            name="BinLocation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
            ],
            options={
                "db_table": "bin_locations",
                "ordering": ["name"],
            },
        ),
        migrations.AlterField(
            model_name="asset",
            name="location",
            field=models.CharField(blank=True, max_length=100, verbose_name="bin location"),
        ),
        migrations.AlterField(
            model_name="consumable",
            name="location",
            field=models.CharField(blank=True, max_length=100, verbose_name="bin location"),
        ),
        migrations.AlterField(
            model_name="usersetting",
            name="default_location",
            field=models.CharField(
                blank=True,
                default="Main Store",
                max_length=100,
                verbose_name="default bin location",
            ),
        ),
        migrations.RunPython(seed_bin_locations, migrations.RunPython.noop),
    ]
