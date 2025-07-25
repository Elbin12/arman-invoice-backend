# Generated by Django 5.2.4 on 2025-07-16 13:31

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_webhooklog'),
        ('ghl_auth', '0002_ghluser'),
    ]

    operations = [
        migrations.CreateModel(
            name='Payout',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('opportunity_id', models.CharField(max_length=100, unique=True)),
                ('amount', models.FloatField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payouts', to='ghl_auth.ghluser')),
            ],
        ),
        migrations.CreateModel(
            name='UserPercentage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('percentage', models.DecimalField(decimal_places=2, max_digits=10)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='percentage', to='ghl_auth.ghluser')),
            ],
        ),
    ]
