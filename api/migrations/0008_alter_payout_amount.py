# Generated by Django 5.2.4 on 2025-07-21 19:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_payout_opportunity_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payout',
            name='amount',
            field=models.DecimalField(decimal_places=2, max_digits=5),
        ),
    ]
