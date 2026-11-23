from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import account, assets, consumables, dashboard, movements, reporting, settings, stocktake, users


urlpatterns = [
    path("", account.home, name="home"),
    path("accounts/login/", account.RoleLoginView.as_view(), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("no-role/", account.no_role, name="no_role"),
    path("no-access/", account.no_access, name="no_access"),
    path("dashboard/", dashboard.dashboard, name="dashboard"),
    path("assets/", assets.asset_list, name="asset_list"),
    path("assets/receive/", assets.asset_create, name="asset_create"),
    path("assets/categories/", assets.category_list, name="asset_category_list"),
    path("assets/categories/new/", assets.category_create, name="asset_category_create"),
    path(
        "assets/categories/<int:category_id>/",
        assets.category_edit,
        name="asset_category_edit",
    ),
    path("assets/categories/<int:category_id>/delete/", assets.category_delete, name="asset_category_delete"),
    path("locations/", assets.bin_location_list, name="bin_location_list"),
    path("locations/new/", assets.bin_location_create, name="bin_location_create"),
    path("locations/<int:location_id>/", assets.bin_location_edit, name="bin_location_edit"),
    path(
        "locations/<int:location_id>/delete/",
        assets.bin_location_delete,
        name="bin_location_delete",
    ),
    path("assets/<barcode:barcode>/", assets.asset_detail, name="asset_detail"),
    path("assets/<barcode:barcode>/edit/", assets.asset_edit, name="asset_edit"),
    path("assets/<barcode:barcode>/delete/", assets.asset_delete, name="asset_delete"),
    path("assets/<barcode:barcode>/issue/", assets.asset_issue, name="asset_issue"),
    path("assets/<barcode:barcode>/return/", assets.asset_return, name="asset_return"),
    path("assets/<barcode:barcode>/label/", assets.asset_label, name="asset_label"),
    path("consumables/", consumables.consumable_list, name="consumable_list"),
    path("consumables/receive/", consumables.consumable_create, name="consumable_create"),
    path(
        "consumables/<barcode:barcode>/",
        consumables.consumable_detail,
        name="consumable_detail",
    ),
    path(
        "consumables/<barcode:barcode>/edit/",
        consumables.consumable_edit,
        name="consumable_edit",
    ),
    path(
        "consumables/<barcode:barcode>/delete/",
        consumables.consumable_delete,
        name="consumable_delete",
    ),
    path(
        "consumables/<barcode:barcode>/receive/",
        consumables.consumable_receive,
        name="consumable_receive",
    ),
    path(
        "consumables/<barcode:barcode>/issue/",
        consumables.consumable_issue,
        name="consumable_issue",
    ),
    path(
        "consumables/<barcode:barcode>/count/",
        consumables.consumable_count,
        name="consumable_count",
    ),
    path(
        "consumables/<barcode:barcode>/label/",
        consumables.consumable_label,
        name="consumable_label",
    ),
    path("goods-in/", movements.goods_in, name="goods_in"),
    path("goods-in/consumable/", movements.goods_in_consumable, name="goods_in_consumable"),
    path("goods-out/", movements.goods_out, name="goods_out"),
    path("goods-out/asset/", movements.goods_out_asset, name="goods_out_asset"),
    path(
        "goods-out/consumable/",
        movements.goods_out_consumable,
        name="goods_out_consumable",
    ),
    path("stocktake/", stocktake.stocktake_home, name="stocktake_home"),
    path("stocktake/assets/", stocktake.stocktake_assets, name="stocktake_assets"),
    path(
        "stocktake/consumables/",
        stocktake.stocktake_consumables,
        name="stocktake_consumables",
    ),
    path("reports/contents/", reporting.store_contents, name="store_contents"),
    path("reports/attributes/", reporting.attribute_report, name="attribute_report"),
    path("usage/", reporting.usage_list, name="usage_list"),
    path("analytics/", reporting.analytics, name="analytics"),
    path("settings/", settings.user_settings, name="user_settings"),
    path("users/", users.user_list, name="user_list"),
    path("users/new/", users.user_create, name="user_create"),
    path("users/<int:user_id>/", users.user_edit, name="user_edit"),
]
