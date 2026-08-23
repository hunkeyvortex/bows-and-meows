from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Address, Coupon, Order, OrderItem, Product, ProductVariant, Wishlist
from .views import _reserve_order_inventory, _restore_order_inventory


class EmailAuthenticationTests(TestCase):
    def test_customer_can_login_with_email(self):
        user = User.objects.create_user(username="legacy-name", email="pet@example.com", password="Strong-pass-938!")
        response = self.client.post(reverse("login"), {
            "identifier": "PET@example.com", "password": "Strong-pass-938!",
        })
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_existing_username_login_still_works(self):
        user = User.objects.create_user(username="legacy-name", email="pet@example.com", password="Strong-pass-938!")
        self.client.post(reverse("login"), {"identifier": "legacy-name", "password": "Strong-pass-938!"})
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_email_registration_generates_internal_username(self):
        response = self.client.post(reverse("register"), {
            "full_name": "Daniyal Shaikh", "email": "daniyal@example.com",
            "password1": "Strong-pass-938!", "password2": "Strong-pass-938!",
        })
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        user = User.objects.get(email="daniyal@example.com")
        self.assertEqual(user.first_name, "Daniyal")
        self.assertTrue(user.username.startswith("daniyal"))


class CouponCalculationTests(TestCase):
    def test_zero_maximum_discount_means_unlimited(self):
        coupon = Coupon(code="WELCOME5", discount_percent=5, maximum_discount=Decimal("0.00"))
        self.assertEqual(coupon.discount_for(Decimal("2002.00")), Decimal("100.10"))

    def test_positive_maximum_discount_caps_saving(self):
        coupon = Coupon(code="SAVE20", discount_percent=20, maximum_discount=Decimal("75.00"))
        self.assertEqual(coupon.discount_for(Decimal("1000.00")), Decimal("75.00"))

    def test_click_to_apply_coupon_reduces_cart_total(self):
        product = Product.objects.create(name="Food", category="dog_food", price=Decimal("1000.00"), stock=2)
        Coupon.objects.create(code="CLICK10", discount_percent=10)
        session = self.client.session
        session["cart"] = {str(product.id): {"product_id": product.id, "variant_id": None, "quantity": 1}}
        session.save()
        response = self.client.post(reverse("apply_coupon"), {"coupon_code": "CLICK10"})
        self.assertRedirects(response, reverse("cart"))
        response = self.client.get(reverse("cart"))
        self.assertEqual(response.context["discount"], Decimal("100.00"))
        self.assertEqual(response.context["total"], Decimal("900.00"))

    def test_exhausted_coupon_message_is_consumed_on_checkout(self):
        product = Product.objects.create(name="Food", category="dog_food", price=Decimal("1000.00"), stock=2)
        Coupon.objects.create(code="ONCE", discount_percent=10, usage_limit=1, times_used=1)
        session = self.client.session
        session["cart"] = {str(product.id): {"product_id": product.id, "variant_id": None, "quantity": 1}}
        session.save()
        response = self.client.post(
            reverse("apply_coupon"),
            {"coupon_code": "ONCE", "next": reverse("checkout")},
            follow=True,
        )
        self.assertContains(response, "This coupon has reached its usage limit.")
        self.assertNotContains(self.client.get(reverse("checkout")), "This coupon has reached its usage limit.")


class HomepageFoodRankingTests(TestCase):
    def test_popular_picks_are_balanced_between_dogs_and_cats(self):
        for index in range(6):
            Product.objects.create(
                name=f"Popular Dog Food {index}",
                pet_type="dog",
                category="dog_food",
                product_type="food",
                price=Decimal("299.00"),
                stock=5,
                is_available=True,
            )
            Product.objects.create(
                name=f"Popular Cat Food {index}",
                pet_type="cat",
                category="cat_food",
                product_type="food",
                price=Decimal("199.00"),
                stock=5,
                is_available=True,
            )

        response = self.client.get(reverse("home"))
        picks = response.context["popular_picks"]
        dog_count = sum(product.category.startswith("dog_") for product in picks)
        cat_count = sum(product.category.startswith("cat_") for product in picks)

        self.assertEqual(len(picks), 10)
        self.assertEqual(dog_count, 5)
        self.assertEqual(cat_count, 5)

    def test_top_selling_food_rejects_misclassified_clothing(self):
        real_food = Product.objects.create(
            name="Pedigree Chicken and Vegetables Adult Dog Dry Food",
            brand="Pedigree",
            pet_type="dog",
            category="dog_food",
            product_type="food",
            price=Decimal("799.00"),
            stock=10,
            is_available=True,
        )
        clothing = Product.objects.create(
            name="Dog Winter Hoodie Shirt",
            brand="Fashion Paws",
            pet_type="dog",
            category="dog_food",
            product_type="food",
            price=Decimal("499.00"),
            stock=10,
            is_available=True,
        )

        response = self.client.get(reverse("home"))
        ranked_ids = [product.id for product in response.context["top_dog_foods"]]

        self.assertIn(real_food.id, ranked_ids)
        self.assertNotIn(clothing.id, ranked_ids)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class CategoryBestSellerRankingTests(TestCase):
    def product(self, name, *, category="dog_food", pet_type="dog", stock=10, featured=False, available=True):
        return Product.objects.create(
            name=name,
            category=category,
            pet_type=pet_type,
            product_type="food",
            price=Decimal("499.00"),
            stock=stock,
            is_featured=featured,
            is_available=available,
        )

    def sale(self, product, quantity, *, status="delivered", payment_status="paid"):
        order = Order.objects.create(
            customer_name="Best Seller Test",
            email="buyer@example.com",
            phone="9999999999",
            address="Test address",
            status=status,
            payment_status=payment_status,
            total_amount=product.price * quantity,
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            price=product.price,
        )

    def best_sellers(self, route_name):
        return list(self.client.get(reverse(route_name)).context["best_sellers"])

    def test_quantity_ten_ranks_over_quantity_four(self):
        lower = self.product("Four-unit seller")
        higher = self.product("Ten-unit seller")
        self.sale(lower, 4)
        self.sale(higher, 10)
        ranked = self.best_sellers("dog_products")
        self.assertLess(ranked.index(higher), ranked.index(lower))

    def test_cancelled_and_failed_orders_do_not_boost_rank(self):
        valid = self.product("Valid seller")
        invalid = self.product("Invalid seller")
        self.sale(valid, 10)
        self.sale(invalid, 100, status="cancelled")
        self.sale(invalid, 100, status="confirmed", payment_status="failed")
        ranked = self.best_sellers("dog_products")
        self.assertLess(ranked.index(valid), ranked.index(invalid))
        self.assertEqual(next(p for p in ranked if p.id == invalid.id).sold_count, 0)

    def test_dog_sales_never_enter_cat_best_sellers(self):
        dog = self.product("Dog-only seller")
        cat = self.product("Cat seller", category="cat_food", pet_type="cat")
        self.sale(dog, 50)
        ranked = self.best_sellers("cat_products")
        self.assertNotIn(dog.id, [product.id for product in ranked])
        self.assertIn(cat.id, [product.id for product in ranked])

    def test_no_sales_uses_market_then_featured_fallback_without_duplicates(self):
        market = self.product("Royal Canin Mini Puppy Dry Dog Food")
        featured = self.product("Featured fallback", featured=True)
        self.product("Ordinary fallback one")
        self.product("Ordinary fallback two")
        self.product("Ordinary fallback three")
        ranked = self.best_sellers("dog_products")
        self.assertEqual(ranked[0].id, market.id)
        self.assertLess(ranked.index(featured), 4)
        self.assertEqual(len(ranked), 4)
        self.assertEqual(len({product.id for product in ranked}), 4)

    def test_unavailable_and_out_of_stock_products_are_not_best_sellers(self):
        unavailable = self.product("Unavailable", available=False)
        out_of_stock = self.product("Out of stock", stock=0)
        available = self.product("Available")
        self.sale(unavailable, 100)
        self.sale(out_of_stock, 100)
        ranked_ids = [product.id for product in self.best_sellers("dog_products")]
        self.assertIn(available.id, ranked_ids)
        self.assertNotIn(unavailable.id, ranked_ids)
        self.assertNotIn(out_of_stock.id, ranked_ids)

    def test_category_filter_sheet_reuses_one_form_on_every_listing(self):
        self.product("Shared listing product")
        for route_name in (
            "dog_products", "cat_products", "medicine_products",
            "wellness_products", "grooming_products", "bird_products",
            "small_pet_products", "farm_animal_products",
            "fish_reptile_products", "vaccination_products",
        ):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200, route_name)
            self.assertEqual(
                response.content.decode().count('id="category-filter-sheet"'),
                1,
                route_name,
            )

    def test_filter_count_and_query_values_are_preserved(self):
        self.product("Filtered product")
        response = self.client.get(reverse("dog_products"), {
            "q": "Filtered",
            "brand": "Example Brand",
            "sort": "price_low",
        })
        self.assertEqual(response.context["active_filter_count"], 3)
        self.assertContains(response, "Filter (3)")
        self.assertContains(response, 'name="q" value="Filtered"')
        self.assertContains(response, 'value="price_low" selected')

    def test_product_page_title_does_not_include_component_css(self):
        product = Product.objects.create(
            name="Clean Title Dog Food",
            category="dog_food",
            product_type="food",
            price=Decimal("299.00"),
            stock=5,
            is_available=True,
        )

        response = self.client.get(reverse("product_detail", args=[product.id]))

        self.assertContains(response, "<title>\nClean Title Dog Food | Boww & Meow\n</title>", html=False)
        title_markup = response.content.decode().split("</title>", 1)[0]
        self.assertNotIn("<style>", title_markup)

    def test_checkout_uses_shared_bow_and_meow_storefront(self):
        product = Product.objects.create(
            name="Checkout Dog Food",
            category="dog_food",
            product_type="food",
            price=Decimal("399.00"),
            stock=5,
            is_available=True,
        )
        session = self.client.session
        session["cart"] = {
            str(product.id): {
                "product_id": product.id,
                "variant_id": None,
                "quantity": 1,
            }
        }
        session.save()

        response = self.client.get(reverse("checkout"))

        self.assertContains(response, 'aria-label="Boww & Meow home"')
        self.assertNotContains(response, "Bows & Meows")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class CategoryFilteringRegressionTests(TestCase):
    def product(
        self,
        name,
        *,
        brand="Royal Canin",
        category="dog_food",
        pet_type="dog",
        product_type="",
        price="500.00",
        care_area="",
        available=True,
    ):
        return Product.objects.create(
            name=name,
            brand=brand,
            category=category,
            pet_type=pet_type,
            product_type=product_type,
            price=Decimal(price),
            care_area=care_area,
            stock=10,
            is_available=available,
        )

    def results(self, route_name="dog_products", **params):
        response = self.client.get(reverse(route_name), params)
        return response, list(response.context["products"])

    def test_combined_royal_food_filters_return_every_matching_product_in_price_order(self):
        expected = [
            self.product("Royal Canin Food 500", price="500.00"),
            self.product("Royal Canin Food 800", price="800.00"),
            self.product("Royal Canin Food 1200", price="1200.00"),
        ]
        grooming = self.product(
            "Royal Canin Grooming Product",
            category="dog_grooming",
            product_type="grooming",
            price="100.00",
        )
        response, products = self.results(
            q="Royal",
            brand="Royal Canin",
            product_type="food",
            care_area="",
            sort="price_low",
        )
        self.assertEqual([product.id for product in products], [product.id for product in expected])
        self.assertNotIn(grooming.id, [product.id for product in products])
        self.assertEqual(response.context["page_obj"].paginator.count, 3)

    def test_brand_filter_returns_multiple_products_and_normalizes_case_and_outer_space(self):
        first = self.product("First", brand=" Royal Canin ")
        second = self.product("Second", brand="royal canin")
        _, products = self.results(brand="ROYAL CANIN")
        self.assertEqual({product.id for product in products}, {first.id, second.id})

    def test_search_uses_or_across_name_and_brand(self):
        name_match = self.product("Royal Nutrition", brand="Another Brand")
        brand_match = self.product("Mini Adult", brand="Royal Canin")
        self.product("Unrelated", brand="Another Brand")
        _, products = self.results(q="Royal")
        self.assertEqual({product.id for product in products}, {name_match.id, brand_match.id})

    def test_food_filter_uses_category_even_when_imported_product_type_is_blank(self):
        blank_type = self.product("Blank imported type", product_type="")
        explicit_type = self.product("Explicit food type", product_type="food")
        wrong_category = self.product(
            "Food-labelled grooming",
            category="dog_grooming",
            product_type="food",
        )
        _, products = self.results(product_type="food")
        self.assertEqual({product.id for product in products}, {blank_type.id, explicit_type.id})
        self.assertNotIn(wrong_category.id, [product.id for product in products])

    def test_price_sort_uses_available_variant_selling_price_without_reducing_count(self):
        base_cheaper = self.product("Base cheaper", price="300.00")
        variant_cheaper = self.product("Variant cheaper", price="900.00")
        ProductVariant.objects.create(
            product=base_cheaper,
            size="1 KG",
            price=Decimal("700.00"),
            stock=2,
            sku="SORT-700",
        )
        ProductVariant.objects.create(
            product=variant_cheaper,
            size="1 KG",
            price=Decimal("400.00"),
            stock=2,
            sku="SORT-400",
        )
        _, unsorted_products = self.results(q="cheaper")
        _, sorted_products = self.results(q="cheaper", sort="price_low")
        self.assertEqual(len(sorted_products), len(unsorted_products))
        self.assertEqual([p.id for p in sorted_products], [variant_cheaper.id, base_cheaper.id])

    def test_blank_care_area_does_not_filter_and_specific_value_does(self):
        general = self.product("General care", care_area="")
        dental = self.product("Dental care", care_area="dental")
        _, all_products = self.results(q="care", care_area="")
        _, dental_products = self.results(q="care", care_area="dental")
        self.assertEqual({p.id for p in all_products}, {general.id, dental.id})
        self.assertEqual([p.id for p in dental_products], [dental.id])

    def test_category_isolation_and_unavailable_rules_remain_active(self):
        dog = self.product("Royal Dog Food")
        cat = self.product("Royal Cat Food", category="cat_food", pet_type="cat")
        unavailable = self.product("Royal Hidden Dog Food", available=False)
        _, dog_products = self.results(q="Royal", product_type="food")
        self.assertIn(dog.id, [p.id for p in dog_products])
        self.assertNotIn(cat.id, [p.id for p in dog_products])
        self.assertNotIn(unavailable.id, [p.id for p in dog_products])


class StoreSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            password="strong-test-password",
        )
        self.other_user = User.objects.create_user(
            username="other-customer",
            password="strong-test-password",
        )
        self.product = Product.objects.create(
            name="Test Food",
            category="dog_food",
            price=Decimal("199.00"),
            stock=5,
            is_available=True,
        )

    def test_cart_mutations_reject_get_requests(self):
        for route_name in (
            "add_to_cart",
            "buy_now",
            "remove_from_cart",
            "increase_quantity",
            "decrease_quantity",
        ):
            response = self.client.get(reverse(route_name, args=[self.product.id]))
            self.assertEqual(response.status_code, 405)

    def test_buy_now_replaces_cart_and_redirects_selected_variant_to_checkout(self):
        variant = ProductVariant.objects.create(
            product=self.product,
            size="4 KG",
            price=Decimal("699.00"),
            stock=3,
            sku="BUY-NOW-4KG",
        )
        session = self.client.session
        session["cart"] = {"old": {"product_id": 999, "variant_id": None, "quantity": 2}}
        session["coupon_code"] = "OLD"
        session.save()

        response = self.client.post(
            reverse("buy_now", args=[self.product.id]),
            {"variant": variant.id},
        )

        self.assertRedirects(response, reverse("checkout"), fetch_redirect_response=False)
        cart = self.client.session["cart"]
        self.assertEqual(len(cart), 1)
        self.assertEqual(list(cart.values())[0]["variant_id"], variant.id)
        self.assertEqual(list(cart.values())[0]["quantity"], 1)
        self.assertNotIn("coupon_code", self.client.session)

    def test_reorder_rebuilds_cart_and_redirects_to_checkout(self):
        order = Order.objects.create(
            user=self.user, customer_name="Customer", email="c@example.com",
            phone="9999999999", address="Test address", total_amount=Decimal("398.00"),
        )
        OrderItem.objects.create(order=order, product=self.product, quantity=2, price=self.product.price)
        self.client.force_login(self.user)
        response = self.client.post(reverse("reorder", args=[order.id]))
        self.assertRedirects(response, reverse("checkout"), fetch_redirect_response=False)
        cart = self.client.session["cart"]
        self.assertEqual(list(cart.values())[0]["quantity"], 2)

    def test_customer_cannot_reorder_another_customers_order(self):
        order = Order.objects.create(
            user=self.other_user, customer_name="Other", email="o@example.com",
            phone="9999999999", address="Other address", total_amount=Decimal("199.00"),
        )
        OrderItem.objects.create(order=order, product=self.product, quantity=1, price=self.product.price)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse("reorder", args=[order.id])).status_code, 404)

    def test_public_help_and_policy_pages_render(self):
        for route_name in (
            "contact_page",
            "faq_page",
            "shipping_policy",
            "returns_policy",
            "veterinary_disclaimer",
            "privacy_policy",
            "terms_page",
        ):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200, route_name)
            self.assertContains(response, "Help & policies")

    def test_prescription_product_is_blocked_from_normal_cart(self):
        medicine = Product.objects.create(
            name="Prescription Medicine",
            category="medicine",
            price=Decimal("499.00"),
            stock=4,
            is_available=True,
            requires_prescription=True,
        )

        response = self.client.post(reverse("add_to_cart", args=[medicine.id]))

        self.assertRedirects(
            response,
            reverse("product_detail", args=[medicine.id]),
            fetch_redirect_response=False,
        )
        self.assertFalse(self.client.session.get("cart"))

    def test_wishlist_mutation_rejects_get(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("toggle_wishlist", args=[self.product.id])
        )
        self.assertEqual(response.status_code, 405)
        self.assertFalse(Wishlist.objects.exists())

    def test_address_delete_rejects_get(self):
        address = Address.objects.create(
            user=self.user,
            full_name="Test Customer",
            phone="9876543210",
            address_line1="1 Test Road",
            city="Pune",
            state="Maharashtra",
            pincode="411001",
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("delete_address", args=[address.id]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Address.objects.filter(id=address.id).exists())

    def test_logout_rejects_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)

    def test_order_success_requires_owner_or_checkout_session(self):
        order = Order.objects.create(
            user=self.other_user,
            customer_name="Private Customer",
            email="private@example.com",
            phone="9876543210",
            address="Private address",
            total_amount=Decimal("199.00"),
        )

        response = self.client.get(reverse("order_success", args=[order.id]))
        self.assertRedirects(
            response,
            reverse("home"),
            fetch_redirect_response=False,
        )

        self.client.force_login(self.other_user)
        response = self.client.get(reverse("order_success", args=[order.id]))
        self.assertEqual(response.status_code, 200)

    def test_external_login_redirect_is_rejected(self):
        response = self.client.post(
            reverse("login") + "?next=https://evil.example/steal",
            {
                "username": "customer",
                "password": "strong-test-password",
            },
        )
        self.assertRedirects(
            response,
            reverse("home"),
            fetch_redirect_response=False,
        )


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class InventoryTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff",
            password="strong-test-password",
            is_staff=True,
        )
        self.client.force_login(self.staff)

    def test_inventory_add_creates_posted_variant_values(self):
        response = self.client.post(
            reverse("crm_inventory_add"),
            {
                "name": "Healthy Dog Food",
                "brand": "Test Brand",
                "pet_type": "dog",
                "category": "dog_food",
                "life_stage": "adult",
                "target_species": "Dogs",
                "active_ingredients": "Test ingredient 10 mg",
                "usage_warning": "Use only under veterinary guidance.",
                "requires_prescription": "on",
                "price": "499.00",
                "stock": "0",
                "is_available": "on",
                "variant_size": ["1 kg"],
                "variant_price": ["499.00"],
                "variant_original_price": ["549.00"],
                "variant_stock": ["7"],
                "variant_sku": ["TEST-1KG"],
            },
        )

        product = Product.objects.get(name="Healthy Dog Food")
        self.assertRedirects(
            response,
            reverse("crm_inventory_edit", args=[product.id]),
        )
        variant = ProductVariant.objects.get(product=product)
        self.assertEqual(variant.price, Decimal("499.00"))
        self.assertEqual(variant.original_price, Decimal("549.00"))
        self.assertEqual(variant.stock, 7)
        self.assertEqual(variant.sku, "TEST-1KG")
        product.refresh_from_db()
        self.assertEqual(product.stock, 7)
        self.assertEqual(product.target_species, "Dogs")
        self.assertEqual(product.active_ingredients, "Test ingredient 10 mg")
        self.assertTrue(product.requires_prescription)

    def test_specialist_storefronts_render(self):
        for route_name in (
            "medicine_products",
            "wellness_products",
            "grooming_products",
            "bird_products",
            "small_pet_products",
            "farm_animal_products",
            "fish_reptile_products",
            "vaccination_products",
        ):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200, route_name)

    def test_product_can_be_archived_and_restored_without_deletion(self):
        product = Product.objects.create(
            name="Seasonal Product",
            category="dog_food",
            price=Decimal("299.00"),
            stock=5,
            is_available=True,
        )

        response = self.client.post(reverse("crm_inventory_archive", args=[product.id]))
        self.assertRedirects(response, reverse("crm_inventory"))
        product.refresh_from_db()
        self.assertTrue(product.is_archived)
        self.assertFalse(
            self.client.get(reverse("product_detail", args=[product.id])).status_code == 200
        )
        self.client.logout()
        self.assertEqual(
            self.client.post(reverse("add_to_cart", args=[product.id])).status_code,
            404,
        )

        self.client.force_login(self.staff)
        self.client.post(reverse("crm_inventory_restore", args=[product.id]))
        product.refresh_from_db()
        self.assertFalse(product.is_archived)
        self.assertTrue(Product.objects.filter(id=product.id).exists())

    def test_product_variants_are_deduplicated_for_customers(self):
        product = Product.objects.create(
            name="Duplicate Size Product",
            category="cat_food",
            price=Decimal("250.00"),
            stock=7,
            is_available=True,
        )
        ProductVariant.objects.create(
            product=product,
            size="1.2 kg",
            price=Decimal("529.00"),
            stock=3,
        )
        cheaper = ProductVariant.objects.create(
            product=product,
            size="1.2 KG",
            price=Decimal("499.00"),
            stock=4,
        )

        self.assertEqual(product.available_variants, [cheaper])
        self.assertEqual(product.display_price, Decimal("499.00"))

    def test_bulk_image_manager_offers_uploads_and_urls(self):
        product = Product.objects.create(
            name="Image Upload Product",
            category="dog_food",
            price=Decimal("299.00"),
            stock=2,
            is_available=True,
        )

        response = self.client.get(reverse("crm_bulk_images"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, f'name="main_upload_{product.id}"')
        self.assertContains(response, f'name="ingredients_upload_{product.id}"')
        self.assertContains(response, f'name="nutrition_upload_{product.id}"')
        self.assertContains(response, f'name="feeding_upload_{product.id}"')
        self.assertContains(response, 'name="batch_images"')
        self.assertContains(response, 'value="batch_upload"')
        self.assertContains(response, "Choose multiple images")

    def test_all_primary_crm_pages_render_with_new_theme(self):
        for route_name in (
            "crm_dashboard",
            "crm_customers",
            "crm_orders",
            "crm_inventory",
            "crm_reports",
            "crm_inventory_add",
            "crm_inventory_bulk_import",
            "crm_bulk_images",
        ):
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200, route_name)
            self.assertContains(response, "store/crm.css")


class PaymentInventoryTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Reserved Food",
            category="dog_food",
            price=Decimal("250.00"),
            stock=3,
            is_available=True,
        )
        self.order = Order.objects.create(
            customer_name="Guest Customer",
            email="guest@example.com",
            phone="9876543210",
            address="Guest address",
            payment_method="online",
            total_amount=Decimal("500.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            price=Decimal("250.00"),
        )

    def grant_guest_access(self):
        session = self.client.session
        session["order_access_ids"] = [self.order.id]
        session.save()

    def test_reservation_and_restoration_are_idempotent(self):
        _reserve_order_inventory(self.order)
        _reserve_order_inventory(self.order)
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.product.stock, 1)
        self.assertTrue(self.order.inventory_reserved)

        _restore_order_inventory(self.order)
        _restore_order_inventory(self.order)
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertFalse(self.order.inventory_reserved)

    def test_guest_can_cancel_own_session_order_and_stock_is_restored(self):
        self.grant_guest_access()
        _reserve_order_inventory(self.order)

        response = self.client.post(
            reverse("payment_cancelled", args=[self.order.id])
        )

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertFalse(self.order.inventory_reserved)
        self.assertEqual(self.order.payment_status, "failed")

    def test_payment_result_mutations_reject_get(self):
        self.grant_guest_access()
        for route_name in (
            "retry_payment",
            "payment_failed_view",
            "payment_cancelled",
        ):
            response = self.client.get(reverse(route_name, args=[self.order.id]))
            self.assertEqual(response.status_code, 405)
