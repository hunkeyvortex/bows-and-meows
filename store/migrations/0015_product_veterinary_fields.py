from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0014_order_inventory_reserved"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="active_ingredients",
            field=models.TextField(blank=True, help_text="Active ingredients exactly as printed on the package."),
        ),
        migrations.AddField(
            model_name="product",
            name="requires_prescription",
            field=models.BooleanField(default=False, help_text="Blocks ordinary cart purchase and displays a prescription warning."),
        ),
        migrations.AddField(
            model_name="product",
            name="target_species",
            field=models.CharField(blank=True, help_text="Examples: Dogs, cats, budgies, exotic birds.", max_length=120),
        ),
        migrations.AddField(
            model_name="product",
            name="usage_warning",
            field=models.TextField(blank=True, help_text="Safety, dosage or veterinary-use warning shown to customers."),
        ),
        migrations.AlterField(
            model_name="product",
            name="category",
            field=models.CharField(choices=[("dog_food", "Dog Food"), ("dog_treat", "Dog Treats"), ("dog_toy", "Dog Toys"), ("dog_grooming", "Dog Grooming"), ("dog_accessory", "Dog Accessories"), ("dog_health", "Dog Health"), ("cat_food", "Cat Food"), ("cat_treat", "Cat Treats"), ("cat_toy", "Cat Toys"), ("cat_litter", "Cat Litter"), ("cat_grooming", "Cat Grooming"), ("cat_accessory", "Cat Accessories"), ("cat_health", "Cat Health"), ("medicine", "Medicine"), ("supplement", "Supplements"), ("skin_coat", "Skin & Coat"), ("dental", "Dental Care"), ("joint_care", "Joint Care"), ("digestive", "Digestive Care"), ("parasite_control", "Flea, Tick & Deworming"), ("respiratory_care", "Respiratory Care"), ("kidney_care", "Kidney & Urinary Care"), ("heart_care", "Heart Care"), ("grooming_shampoo", "Shampoo & Coat Care"), ("hygiene", "Hygiene & Cleaning"), ("training_pads", "Training Pads"), ("bird_food", "Bird Food"), ("bird_supplement", "Bird Supplements"), ("bird_health", "Bird Health"), ("exotic_health", "Exotic Pet Health"), ("treat", "Treat"), ("accessory", "Accessory")], max_length=50),
        ),
        migrations.AlterField(
            model_name="product",
            name="pet_type",
            field=models.CharField(blank=True, choices=[("dog", "Dog"), ("cat", "Cat"), ("both", "Dog & Cat"), ("bird", "Bird"), ("exotic", "Exotic Pet")], max_length=10),
        ),
    ]
