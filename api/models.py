from django.db import models
from django.core.exceptions import ValidationError

# Create your models here.


class WebhookLog(models.Model):
    received_at = models.DateTimeField(auto_now_add=True)
    data = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.webhook_id} : {self.received_at}"


class Service(models.Model):
    """
    Main service model that represents a service offering
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'data_management_app_service'
        ordering = ['name']
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self):
        return self.name
    
class Contact(models.Model):
    contact_id = models.CharField(max_length=100, unique=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    dnd = models.BooleanField(default=False)
    country = models.CharField(max_length=50, blank=True, null=True)
    date_added = models.DateTimeField(blank=True, null=True)
    tags = models.JSONField(default=list, blank=True)
    custom_fields = models.JSONField(default=list, blank=True)
    location_id = models.CharField(max_length=100)
    timestamp = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'data_management_app_contact'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"
    
class Job(models.Model):
    contact_id = models.CharField(max_length=100)
    pipeline_id = models.CharField(max_length=100)
    location_id = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    pipeline_stage_id = models.CharField(max_length=100, blank=True, null=True)

    STATUS_CHOICES = [
        ("open", "Open"),
        ("won", "Won"),
        ("lost", "Lost"),
        ("abandoned", "Abandoned"),
        ("all", "All"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    monetary_value = models.FloatField(blank=True, null=True)
    assigned_to = models.CharField(max_length=100, blank=True, null=True)

    service_ids = models.JSONField(default=list)

    def clean(self):
        if not Contact.objects.using('external').filter(contact_id=self.contact_id).exists():
            raise ValidationError("Invalid contact ID.")
        

class Payout(models.Model):
    opportunity_id = models.CharField(max_length=100)
    opportunity_name = models.CharField(max_length=500, null=True, blank=True)
    user = models.ForeignKey("ghl_auth.GHLUser", on_delete=models.CASCADE, related_name="payouts")
    amount = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.name} - ₹{self.amount:.2f} (Opportunity: {self.opportunity_id})"