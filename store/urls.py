from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("", views.home, name="home"),

    path("cart/", views.cart, name="cart"),
    path("cart/add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("cart/remove/<int:product_id>/", views.remove_from_cart, name="remove_from_cart"),
    path("cart/increase/<int:product_id>/", views.increase_quantity, name="increase_quantity"),
    path("cart/decrease/<int:product_id>/", views.decrease_quantity, name="decrease_quantity"),

    path("checkout/", views.checkout, name="checkout"),
    path("order-success/<int:order_id>/", views.order_success, name="order_success"),
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("account/", views.account, name="account"),
    path("pets/", views.my_pets, name="my_pets"),
    path("pets/add/", views.add_pet, name="add_pet"),
    path("orders/", views.my_orders, name="my_orders"),
    path("crm/", views.crm_dashboard, name="crm_dashboard"),
    path("crm/customers/", views.crm_customers, name="crm_customers"),
    path("crm/customers/<int:user_id>/", views.crm_customer_detail, name="crm_customer_detail"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("crm/inventory/", views.crm_inventory, name="crm_inventory"),
    path("crm/inventory/<int:product_id>/edit/", views.crm_inventory_edit, name="crm_inventory_edit"),
    path("crm/orders/", views.crm_orders, name="crm_orders"),
    path("crm/orders/<int:order_id>/status/", views.crm_order_status, name="crm_order_status"),
    path("crm/reports/", views.crm_reports, name="crm_reports"),
    path("crm/inventory/add/", views.crm_inventory_add, name="crm_inventory_add"),
    path("product/<int:product_id>/", views.product_detail, name="product_detail"),
    path("product/<int:product_id>/review/",views.add_review,name="add_review"),
    path("dogs/", views.dog_products, name="dog_products"),
    path("cats/", views.cat_products, name="cat_products"),
    path("medicines/", views.medicine_products, name="medicine_products"),
    path("search/", views.search_products, name="search_products"),
    path("wishlist/", views.wishlist, name="wishlist"),
    path("wishlist/toggle/<int:product_id>/",views.toggle_wishlist,name="toggle_wishlist"),
    path("addresses/",views.my_addresses,name="my_addresses"),
    path("addresses/add/",views.add_address,name="add_address"),
    path("addresses/<int:address_id>/edit/",views.edit_address,name="edit_address"),
    path("addresses/<int:address_id>/delete/",views.delete_address,name="delete_address"),
    path("payment/verify/",views.verify_payment,name="verify_payment"),
   path(
    "payment/retry/<int:order_id>/",
    views.retry_payment,
    name="retry_payment"
),
    path("payment/failed/<int:order_id>/",views.payment_failed_view,name="payment_failed_view"),
    path("payment/cancelled/<int:order_id>/",views.payment_cancelled,name="payment_cancelled"),
    path(
    "password-reset/",
    auth_views.PasswordResetView.as_view(
        template_name="store/password_reset.html",
        email_template_name="store/emails/password_reset_email.html",
        subject_template_name="store/emails/password_reset_subject.txt",
    ),
    name="password_reset",
),

path(
    "password-reset/done/",
    auth_views.PasswordResetDoneView.as_view(
        template_name="store/password_reset_done.html"
    ),
    name="password_reset_done",
),

path(
    "password-reset/<uidb64>/<token>/",
    auth_views.PasswordResetConfirmView.as_view(
        template_name="store/password_reset_confirm.html"
    ),
    name="password_reset_confirm",
),

path(
    "password-reset/complete/",
    auth_views.PasswordResetCompleteView.as_view(
        template_name="store/password_reset_complete.html"
    ),
    name="password_reset_complete",
),
path(
    "crm/inventory/bulk-import/",
    views.crm_inventory_bulk_import,
    name="crm_inventory_bulk_import",
),
]
