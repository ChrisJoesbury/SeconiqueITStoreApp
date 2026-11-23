from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .forms import AssetCreateForm, AssetIssueForm
from .models import Asset, AssetCategory, BinLocation, Consumable, Usage, UserSetting
from .roles import ADMIN, ASSIGNEE, REPORTING, STANDARD
from .services import (
    StockError,
    create_consumable,
    issue_asset,
    issue_consumable,
    receive_consumable,
    stocktake_consumable,
)


class StockMovementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="Ledger-day-1947")

    def test_receipt_issue_and_stocktake_are_logged(self):
        form = _consumable_form()
        self.assertTrue(form.is_valid(), form.errors)
        item = create_consumable(form, self.user)
        self.assertEqual(item.barcode, "SEC-C-000001")
        self.assertEqual(item.quantity_on_hand, 10)
        self.assertEqual(Usage.objects.filter(movement=Usage.Movement.RECEIPT).count(), 1)

        receive_consumable(item, 5, self.user, "Extra box")
        item.refresh_from_db()
        self.assertEqual(item.quantity_on_hand, 15)

        issue_consumable(item, 4, self.user, "Alex Morgan")
        item.refresh_from_db()
        self.assertEqual(item.quantity_on_hand, 11)

        with self.assertRaises(StockError):
            issue_consumable(item, 50, self.user, "Alex Morgan")

        stocktake_consumable(item, 0, self.user, "Shelf empty")
        item.refresh_from_db()
        self.assertEqual(item.quantity_on_hand, 0)
        self.assertEqual(Usage.objects.filter(movement=Usage.Movement.STOCKTAKE).count(), 1)

    def test_asset_end_of_life_cannot_precede_the_order_date(self):
        form = AssetCreateForm(
            data={
                "name": "Laptop",
                "category": "Laptop",
                "order_date": "2026-05-01",
                "eol_date": "2026-04-01",
                "location": "Main Store",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("eol_date", form.errors)

    def test_only_in_stock_assets_can_be_issued(self):
        asset = Asset.objects.create(
            barcode="SEC-A-000001",
            name="Monitor",
            category="Monitor",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
        )
        issue_asset(asset, "Priya Shah", self.user)
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.ISSUED)
        with self.assertRaises(StockError):
            issue_asset(asset, "Someone else", self.user)


class RoleAccessTests(TestCase):
    def setUp(self):
        self.standard = _user("store.standard", STANDARD)
        self.admin = _user("store.admin", ADMIN)
        self.reporting = _user("store.report", REPORTING)

    def test_reporting_is_limited_to_analytics(self):
        self.client.force_login(self.reporting)
        denied = self.client.get(reverse("goods_in"))
        self.assertRedirects(denied, reverse("analytics"))
        allowed = self.client.get(reverse("analytics"))
        self.assertEqual(allowed.status_code, 200)

    def test_standard_cannot_open_analytics_or_delete(self):
        asset = Asset.objects.create(
            barcode="SEC-A-000009",
            name="Phone",
            category="Phone",
            order_date=date(2026, 1, 1),
            eol_date=date(2029, 1, 1),
        )
        self.client.force_login(self.standard)
        self.assertRedirects(self.client.get(reverse("analytics")), reverse("dashboard"))
        self.client.post(reverse("asset_delete", args=[asset.pk]))
        self.assertTrue(Asset.objects.filter(pk=asset.pk).exists())

    def test_admin_can_manage_asset_categories(self):
        self.client.force_login(self.standard)
        self.assertRedirects(
            self.client.get(reverse("asset_category_list")), reverse("dashboard")
        )
        self.client.force_login(self.admin)
        duplicate = self.client.post(reverse("asset_category_create"), {"name": "laptop"})
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(duplicate, "already exists")

        created = self.client.post(reverse("asset_category_create"), {"name": "Printer"})
        self.assertRedirects(created, reverse("asset_category_list"))
        category = AssetCategory.objects.get(name="Printer")
        asset = Asset.objects.create(
            barcode="SEC-A-000010",
            name="Laser printer",
            category="Printer",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
        )
        renamed = self.client.post(
            reverse("asset_category_edit", args=[category.pk]), {"name": "Printers"}
        )
        self.assertRedirects(renamed, reverse("asset_category_list"))
        asset.refresh_from_db()
        self.assertEqual(asset.category, "Printers")
        category.refresh_from_db()

        blocked = self.client.post(reverse("asset_category_delete", args=[category.pk]))
        self.assertRedirects(blocked, reverse("asset_category_edit", args=[category.pk]))
        self.assertTrue(AssetCategory.objects.filter(pk=category.pk).exists())

        asset.category = "Laptop"
        asset.save()
        removed = self.client.post(reverse("asset_category_delete", args=[category.pk]))
        self.assertRedirects(removed, reverse("asset_category_list"))
        self.assertFalse(AssetCategory.objects.filter(name="Printers").exists())

        cable = AssetCategory.objects.get(name="Cable")
        item = Consumable.objects.create(
            barcode="SEC-C-000009",
            name="HDMI cable",
            category="Cable",
        )
        renamed_cable = self.client.post(
            reverse("asset_category_edit", args=[cable.pk]), {"name": "Cables"}
        )
        self.assertRedirects(renamed_cable, reverse("asset_category_list"))
        item.refresh_from_db()
        self.assertEqual(item.category, "Cables")
        blocked_cable = self.client.post(reverse("asset_category_delete", args=[cable.pk]))
        self.assertRedirects(blocked_cable, reverse("asset_category_edit", args=[cable.pk]))
        self.assertTrue(AssetCategory.objects.filter(name="Cables").exists())

    def test_admin_can_open_analytics(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("analytics"))
        self.assertEqual(response.status_code, 200)

    def test_only_admin_can_manage_users(self):
        self.client.force_login(self.standard)
        self.assertRedirects(self.client.get(reverse("user_list")), reverse("dashboard"))
        self.client.force_login(self.reporting)
        self.assertRedirects(self.client.get(reverse("user_list")), reverse("analytics"))
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("user_list")).status_code, 200)

    def test_admin_can_create_and_change_a_user(self):
        self.client.force_login(self.admin)
        created = self.client.post(
            reverse("user_create"),
            {
                "username": "new.keeper",
                "first_name": "New",
                "last_name": "Keeper",
                "email": "keeper@example.com",
                "role": STANDARD,
                "is_active": "on",
                "password": "Ledger-new-1947",
                "password_confirm": "Ledger-new-1947",
            },
        )
        self.assertRedirects(created, reverse("user_list"))
        account = User.objects.get(username="new.keeper")
        self.assertTrue(account.check_password("Ledger-new-1947"))
        self.assertTrue(account.groups.filter(name=STANDARD).exists())

        changed = self.client.post(
            reverse("user_edit", args=[account.pk]),
            {
                "username": "new.keeper",
                "first_name": "New",
                "last_name": "Keeper",
                "email": "keeper@example.com",
                "role": REPORTING,
                "is_active": "on",
                "password": "",
                "password_confirm": "",
            },
        )
        self.assertRedirects(changed, reverse("user_list"))
        account.refresh_from_db()
        self.assertTrue(account.check_password("Ledger-new-1947"))
        self.assertTrue(account.groups.filter(name=REPORTING).exists())
        self.assertFalse(account.groups.filter(name=STANDARD).exists())

    def test_assignee_cannot_sign_in_or_open_the_app(self):
        assignee = _user("joe.bloggs", ASSIGNEE)
        assignee.first_name = "Joe"
        assignee.last_name = "Bloggs"
        assignee.save()
        denied = self.client.post(
            reverse("login"),
            {"username": "joe.bloggs", "password": "Ledger-day-1947"},
        )
        self.assertEqual(denied.status_code, 200)
        self.assertContains(denied, "cannot sign in")
        self.assertNotIn("_auth_user_id", self.client.session)

        self.client.force_login(assignee)
        bounced = self.client.get(reverse("dashboard"), follow=True)
        self.assertEqual(bounced.request["PATH_INFO"], reverse("login"))
        self.assertContains(bounced, "cannot sign in")

        form = AssetIssueForm()
        self.assertIn(("Joe Bloggs", "Joe Bloggs"), form.fields["issued_to"].choices)
        rejected = AssetIssueForm(data={"issued_to": "Someone else"})
        self.assertFalse(rejected.is_valid())

    def test_admin_cannot_remove_their_own_access(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("user_edit", args=[self.admin.pk]),
            {
                "username": self.admin.username,
                "role": STANDARD,
                "password": "",
                "password_confirm": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertTrue(self.admin.groups.filter(name=ADMIN).exists())


class ReceiptLabelTests(TestCase):
    def setUp(self):
        self.user = _user("store.receipt", STANDARD)
        self.client.force_login(self.user)

    def test_asset_label_is_ready_before_the_asset_is_saved(self):
        response = self.client.post(
            reverse("asset_create"),
            {"action": "label", "name": "Dell Latitude"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SEC-A-000001")
        self.assertContains(response, 'value="SEC-A-000001"')
        self.assertContains(response, "Dell Latitude")
        self.assertContains(response, "label-sheet")
        self.assertNotContains(response, "This field is required.")
        self.assertFalse(Asset.objects.exists())

        received = self.client.post(
            reverse("asset_create"),
            {
                "barcode": "SEC-A-000001",
                "name": "Dell Latitude",
                "category": "Laptop",
                "order_date": "2026-01-01",
                "eol_date": "2030-01-01",
                "location": "Main Store",
            },
        )
        self.assertRedirects(received, reverse("asset_label", args=["SEC-A-000001"]))
        self.assertTrue(Asset.objects.filter(pk="SEC-A-000001", name="Dell Latitude").exists())

    def test_consumable_label_is_ready_before_the_item_is_saved(self):
        response = self.client.post(
            reverse("consumable_create"),
            {"action": "label", "name": "HDMI cable"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SEC-C-000001")
        self.assertContains(response, 'value="SEC-C-000001"')
        self.assertContains(response, "HDMI cable")
        self.assertContains(response, "label-sheet")
        self.assertNotContains(response, "This field is required.")
        self.assertFalse(Consumable.objects.exists())

    def test_label_keeps_a_typed_barcode_and_needs_a_description(self):
        missing = self.client.post(reverse("asset_create"), {"action": "label", "name": "  "})
        self.assertContains(missing, "Enter the name before generating a label.")
        self.assertNotContains(missing, "label-sheet")

        kept = self.client.post(
            reverse("consumable_create"),
            {"action": "label", "name": "Toner", "barcode": "TONER-1"},
        )
        self.assertContains(kept, "TONER-1")
        self.assertContains(kept, "Toner")
        self.assertFalse(Consumable.objects.filter(pk="TONER-1").exists())


def _user(username, role):
    user = User.objects.create_user(username=username, password="Ledger-day-1947")
    user.groups.add(Group.objects.get(name=role))
    return user


def _consumable_form(**overrides):
    from .forms import ConsumableCreateForm

    data = {
        "name": "HDMI cable",
        "category": "Cable",
        "unit": "each",
        "quantity_on_hand": 10,
        "reorder_level": 2,
        "reorder_quantity": 10,
        "location": "Main Store",
    }
    data.update(overrides)
    return ConsumableCreateForm(data=data)


class MaxHoldTests(TestCase):
    def setUp(self):
        self.admin = _user("store.admin.max", ADMIN)
        self.keeper = User.objects.create_user(username="keeper.max", password="Ledger-day-1947")

    def test_blank_max_is_stored_as_no_maximum(self):
        form = _consumable_form()
        self.assertTrue(form.is_valid(), form.errors)
        item = create_consumable(form, self.keeper)
        self.assertEqual(item.max_qty_to_hold, 0)
        self.assertFalse(item.over_max_hold)
        self.assertEqual(item.suggested_order, 0)

    def test_max_must_sit_above_the_reorder_level(self):
        form = _consumable_form(max_qty_to_hold=2)
        self.assertFalse(form.is_valid())
        self.assertIn("max_qty_to_hold", form.errors)

    def test_suggested_order_stops_at_the_max(self):
        item = Consumable(
            quantity_on_hand=1,
            reorder_level=2,
            reorder_quantity=20,
            max_qty_to_hold=6,
        )
        self.assertEqual(item.suggested_order, 5)
        self.assertTrue(item.order_was_capped)

    def test_reports_compare_stock_with_max_qty_to_hold(self):
        Consumable.objects.create(
            barcode="SEC-C-000021",
            name="HDMI cable",
            category="Cable",
            unit="each",
            quantity_on_hand=12,
            reorder_level=2,
            reorder_quantity=4,
            max_qty_to_hold=8,
        )
        toner = Consumable.objects.create(
            barcode="SEC-C-000022",
            name="Black toner",
            category="Toner",
            unit="each",
            quantity_on_hand=1,
            reorder_level=2,
            reorder_quantity=20,
            max_qty_to_hold=6,
        )
        for number in range(1, 4):
            Asset.objects.create(
                barcode=f"SEC-A-00010{number}",
                name="Laptop",
                category="Laptop",
                order_date=date(2026, 1, 1),
                eol_date=date(2030, 1, 1),
                max_qty_to_hold=2,
            )
        Asset.objects.create(
            barcode="SEC-A-000104",
            name="Laptop",
            category="Laptop",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
            status=Asset.Status.ISSUED,
            max_qty_to_hold=2,
        )
        Asset.objects.create(
            barcode="SEC-A-000105",
            name="Laptop",
            category="Laptop",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
            status=Asset.Status.RETIRED,
            max_qty_to_hold=9,
        )

        self.assertEqual(toner.suggested_order, 5)
        holding = Asset.holding_rows()
        self.assertEqual(len(holding), 1)
        self.assertEqual(holding[0]["held"], 3)
        self.assertEqual(holding[0]["issued"], 1)
        self.assertEqual(holding[0]["max_qty"], 2)
        self.assertEqual(holding[0]["over_by"], 1)
        self.assertTrue(holding[0]["over_max"])

        self.client.force_login(self.admin)
        analytics = self.client.get(reverse("analytics"))
        self.assertContains(analytics, "Consumables above max qty to hold")
        self.assertContains(analytics, "Assets against max qty to hold")
        self.assertContains(analytics, "HDMI cable")
        self.assertContains(analytics, "capped at the max qty to hold")
        self.assertContains(analytics, "1 over")
        self.assertEqual(analytics.context["over_consumable_count"], 1)
        self.assertEqual(analytics.context["over_asset_count"], 1)
        self.assertEqual(analytics.context["low_stock"].get().barcode, toner.barcode)

        consumables = self.client.get(reverse("consumable_list"), {"over": "1"})
        self.assertContains(consumables, "HDMI cable")
        self.assertNotContains(consumables, "Black toner")

        detail = self.client.get(reverse("asset_detail", args=["SEC-A-000101"]))
        self.assertContains(detail, "Max qty to hold")
        self.assertContains(detail, "1 over")

        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.context["over_max_count"], 1)
        self.assertContains(dashboard, "Consumables over max hold")


class MovementSearchTests(TestCase):
    def setUp(self):
        self.user = _user("store.movement", STANDARD)
        self.client.force_login(self.user)
        self.asset = Asset.objects.create(
            barcode="SEC-A-000201",
            name="Dell Latitude",
            category="Laptop",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
            location="IT store",
        )
        Asset.objects.create(
            barcode="SEC-A-000202",
            name="Desk phone",
            category="Phone",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
        )
        self.cable = Consumable.objects.create(
            barcode="SEC-C-000201",
            name="HDMI cable",
            category="Cable",
            quantity_on_hand=6,
            unit="each",
        )
        Consumable.objects.create(
            barcode="SEC-C-000202",
            name="Black toner",
            category="Toner",
            quantity_on_hand=2,
            unit="each",
        )

    def test_assets_can_be_issued_from_a_name_search(self):
        found = self.client.get(reverse("goods_out_asset"), {"q": "Latitude"})
        self.assertContains(found, "Dell Latitude")
        self.assertNotContains(found, "Desk phone")
        self.assertContains(found, "Issue")

        chosen = self.client.get(reverse("goods_out_asset"), {"barcode": self.asset.barcode})
        self.assertContains(chosen, "Confirm issue")
        self.assertContains(chosen, "Dell Latitude")
        self.assertNotContains(chosen, "Desk phone")

    def test_consumables_can_be_issued_and_received_from_a_name_search(self):
        issue = self.client.get(reverse("goods_out_consumable"), {"q": "HDMI"})
        self.assertContains(issue, "HDMI cable")
        self.assertNotContains(issue, "Black toner")

        receive = self.client.get(reverse("goods_in_consumable"), {"q": "toner"})
        self.assertContains(receive, "Black toner")
        self.assertNotContains(receive, "HDMI cable")
        self.assertContains(receive, "Receive")

        chosen = self.client.get(reverse("goods_in_consumable"), {"barcode": self.cable.barcode})
        self.assertContains(chosen, "Confirm receipt")
        self.assertContains(chosen, "HDMI cable")


class StoreContentsReportTests(TestCase):
    def setUp(self):
        self.admin = _user("store.admin.contents", ADMIN)
        self.reporting = _user("store.report.contents", REPORTING)
        self.standard = _user("store.standard.contents", STANDARD)
        Asset.objects.create(
            barcode="SEC-A-000201",
            name="Laptop",
            category="Laptop",
            location="IT store",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
        )
        Asset.objects.create(
            barcode="SEC-A-000202",
            name="Monitor",
            category="Monitor",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
            status=Asset.Status.ISSUED,
            issued_to="Alex Morgan",
        )
        Consumable.objects.create(
            barcode="SEC-C-000201",
            name="HDMI cable",
            category="Cable",
            unit="each",
            quantity_on_hand=4,
            location="IT store",
        )
        Consumable.objects.create(
            barcode="SEC-C-000202",
            name="Black toner",
            category="Toner",
            unit="each",
            quantity_on_hand=0,
        )

    def test_store_list_marks_assets_and_consumables(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("store_contents"))
        self.assertContains(response, "What is in the store")
        self.assertContains(response, "Laptop")
        self.assertContains(response, "pill-asset")
        self.assertContains(response, "HDMI cable")
        self.assertContains(response, "pill-consumable")
        self.assertContains(response, "4 each")
        self.assertNotContains(response, "Monitor")
        self.assertNotContains(response, "Black toner")
        self.assertEqual(response.context["asset_count"], 1)
        self.assertEqual(response.context["consumable_count"], 1)
        self.assertContains(response, reverse("asset_detail", args=["SEC-A-000201"]))

        assets_only = self.client.get(reverse("store_contents"), {"kind": "asset"})
        self.assertContains(assets_only, "Laptop")
        self.assertNotContains(assets_only, "HDMI cable")

        found = self.client.get(reverse("store_contents"), {"q": "hdmi"})
        self.assertContains(found, "HDMI cable")
        self.assertNotContains(found, "Laptop")

    def test_reporting_and_standard_can_open_the_store_list(self):
        self.client.force_login(self.reporting)
        reporting = self.client.get(reverse("store_contents"))
        self.assertEqual(reporting.status_code, 200)
        self.assertNotContains(reporting, reverse("asset_detail", args=["SEC-A-000201"]))

        self.client.force_login(self.standard)
        standard = self.client.get(reverse("store_contents"))
        self.assertEqual(standard.status_code, 200)
        self.assertContains(standard, "Store list")


class AttributeReportTests(TestCase):
    def test_attributes_are_cleaned_and_reported_across_stock(self):
        form = _consumable_form(attributes=" HDMI , 2m, hdmi , ")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["attributes"], "HDMI, 2m")
        keeper = User.objects.create_user(username="keeper.attr", password="Ledger-day-1947")
        cable = create_consumable(form, keeper)
        cable.attributes = "wireless, 2m"
        cable.save()

        Asset.objects.create(
            barcode="SEC-A-000301",
            name="Laptop",
            category="Laptop",
            attributes="Wireless, 16GB",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
        )
        Asset.objects.create(
            barcode="SEC-A-000302",
            name="Desk phone",
            category="Phone",
            attributes="handset",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
        )

        self.client.force_login(_user("store.admin.attr", ADMIN))
        report = self.client.get(reverse("attribute_report"))
        summary = {row["name"]: row for row in report.context["summary"]}
        self.assertEqual(summary["Wireless"]["asset_count"], 1)
        self.assertEqual(summary["Wireless"]["consumable_count"], 1)
        self.assertEqual(summary["16GB"]["total"], 1)
        self.assertEqual(summary["2m"]["consumable_count"], 1)
        self.assertNotIn("wireless", summary)
        self.assertContains(report, "Desk phone")

        chosen = self.client.get(reverse("attribute_report"), {"attribute": "wireless"})
        self.assertContains(chosen, "Laptop")
        self.assertContains(chosen, "HDMI cable")
        self.assertNotContains(chosen, "Desk phone")
        self.assertEqual(chosen.context["item_count"], 2)

        listing = self.client.get(reverse("store_contents"), {"q": "16GB"})
        self.assertContains(listing, "Laptop")
        self.assertNotContains(listing, "HDMI cable")

        self.client.force_login(_user("store.report.attr", REPORTING))
        visible = self.client.get(reverse("attribute_report"))
        self.assertEqual(visible.status_code, 200)
        self.assertContains(visible, "Attributes")


class BinLocationTests(TestCase):
    def setUp(self):
        self.standard = _user("store.standard.bins", STANDARD)
        self.admin = _user("store.admin.bins", ADMIN)

    def test_the_store_bins_are_available(self):
        names = set(BinLocation.objects.values_list("name", flat=True))
        self.assertTrue(
            {
                "Disposal cage",
                "Goods In",
                "Goods Out",
                "Main Store",
                "Server Room",
            }.issubset(names)
        )

    def test_admin_can_create_rename_and_delete_a_bin_location(self):
        self.client.force_login(self.standard)
        self.assertRedirects(self.client.get(reverse("bin_location_list")), reverse("dashboard"))
        self.assertNotContains(self.client.get(reverse("dashboard")), reverse("bin_location_list"))

        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("dashboard")), reverse("bin_location_list"))
        duplicate = self.client.post(reverse("bin_location_create"), {"name": "main store"})
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(duplicate, "already exists")

        created = self.client.post(reverse("bin_location_create"), {"name": "Returns cage"})
        self.assertRedirects(created, reverse("bin_location_list"))
        location = BinLocation.objects.get(name="Returns cage")
        asset = Asset.objects.create(
            barcode="SEC-A-000401",
            name="Spare switch",
            category="Network equipment",
            location="Returns cage",
            order_date=date(2026, 1, 1),
            eol_date=date(2030, 1, 1),
        )
        item = Consumable.objects.create(
            barcode="SEC-C-000401",
            name="Patch lead",
            category="Cable",
            location="Returns cage",
            quantity_on_hand=2,
        )
        prefs = UserSetting.objects.get(user=self.admin)
        prefs.default_location = "Returns cage"
        prefs.save()

        renamed = self.client.post(
            reverse("bin_location_edit", args=[location.pk]), {"name": "Returns"}
        )
        self.assertRedirects(renamed, reverse("bin_location_list"))
        asset.refresh_from_db()
        item.refresh_from_db()
        prefs.refresh_from_db()
        self.assertEqual(asset.location, "Returns")
        self.assertEqual(item.location, "Returns")
        self.assertEqual(prefs.default_location, "Returns")

        blocked = self.client.post(reverse("bin_location_delete", args=[location.pk]))
        self.assertRedirects(blocked, reverse("bin_location_edit", args=[location.pk]))
        self.assertTrue(BinLocation.objects.filter(name="Returns").exists())

        asset.location = "Main Store"
        asset.save()
        item.location = "Goods In"
        item.save()
        prefs.default_location = "Main Store"
        prefs.save()
        removed = self.client.post(reverse("bin_location_delete", args=[location.pk]))
        self.assertRedirects(removed, reverse("bin_location_list"))
        self.assertFalse(BinLocation.objects.filter(name="Returns").exists())
