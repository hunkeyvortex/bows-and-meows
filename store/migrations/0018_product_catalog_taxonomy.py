from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0017_product_is_archived")]

    operations = [
        migrations.AddField(model_name="product", name="product_type", field=models.CharField(blank=True, choices=[("food", "Food"), ("medicine", "Medicine"), ("supplement", "Supplement"), ("treat", "Treat"), ("supply", "Supply & Accessory"), ("grooming", "Grooming & Hygiene"), ("vaccine", "Vaccination")], db_index=True, max_length=20)),
        migrations.AddField(model_name="product", name="care_area", field=models.CharField(blank=True, choices=[("", "General / Not Applicable"), ("allergy", "Allergy Relief"), ("antibiotic", "Antibiotic"), ("anxiety", "Anxiety Care"), ("cancer", "Cancer Care"), ("cardiac", "Cardiac Care"), ("deworming", "Deworming"), ("diabetes", "Diabetes Care"), ("eye_ear", "Eye & Ear Care"), ("flea_tick", "Flea & Tick Care"), ("digestive", "Digestive Care"), ("joint", "Hip & Joint Care"), ("immunity", "Immunity Support"), ("liver", "Liver Care"), ("prenatal", "Pre & Post Natal Care"), ("respiratory", "Respiratory Care"), ("skin_coat", "Skin & Coat Care"), ("renal", "Renal & Urinary Care"), ("wound_pain", "Wound & Pain Relief"), ("dental", "Dental & Oral Care"), ("nutrition", "Everyday Nutrition")], db_index=True, max_length=30)),
        migrations.AlterField(model_name="product", name="pet_type", field=models.CharField(blank=True, choices=[("dog", "Dog"), ("cat", "Cat"), ("both", "Dog & Cat"), ("bird", "Bird"), ("exotic", "Exotic Pet"), ("small_pet", "Small Pet"), ("farm", "Farm Animal"), ("fish_reptile", "Fish & Reptile")], max_length=15)),
    ]
