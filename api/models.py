from django.db import models
from django.core.exceptions import ValidationError
import uuid

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
    amount = models.DecimalField(decimal_places=2, max_digits=5)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.name} - ₹{self.amount:.2f} (Opportunity: {self.opportunity_id})"


class Invoice(models.Model):
    """Model to store invoice data for public viewing"""
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
        ("cancelled", "Cancelled"),
    ]
    
    # Unique token for public access
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    
    # GHL Invoice IDs
    ghl_invoice_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    invoice_number = models.CharField(max_length=100, null=True, blank=True)
    
    # Invoice details
    name = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    currency = models.CharField(max_length=10, default="USD")
    
    # Financial fields
    total = models.DecimalField(max_digits=10, decimal_places=2)
    invoice_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Dates
    issue_date = models.DateField()
    due_date = models.DateField()
    
    # Contact details
    contact_id = models.CharField(max_length=100)
    contact_name = models.CharField(max_length=255)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, null=True, blank=True)
    contact_address = models.TextField(null=True, blank=True)
    contact_company_name = models.CharField(max_length=255, null=True, blank=True)
    
    # Business details
    business_name = models.CharField(max_length=255)
    business_logo_url = models.URLField(null=True, blank=True)
    
    # Location and company info
    location_id = models.CharField(max_length=100)
    company_id = models.CharField(max_length=100, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Additional metadata
    live_mode = models.BooleanField(default=True)
    raw_data = models.JSONField(default=dict, blank=True)  # Store full GHL response
    
    # Stripe payment tracking
    stripe_payment_intent_id = models.CharField(max_length=200, null=True, blank=True)
    stripe_checkout_session_id = models.CharField(max_length=200, null=True, blank=True)
    
    # Digital signature (stored as base64 image)
    signature = models.TextField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['ghl_invoice_id']),
            models.Index(fields=['invoice_number']),
        ]
    
    def __str__(self):
        return f"Invoice {self.invoice_number or self.token} - {self.contact_name}"
    
    @property
    def is_paid(self):
        """Check if invoice is fully paid"""
        return self.amount_due <= 0 or self.status == "paid"
    
    @property
    def payment_url(self):
        """Generate payment URL (to be implemented with payment gateway)"""
        return f"/invoice/{self.token}/pay"


class InvoiceItem(models.Model):
    """Model to store invoice line items"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    
    name = models.CharField(max_length=500)
    description = models.TextField(null=True, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Product reference
    product_id = models.CharField(max_length=100, null=True, blank=True)
    
    # Tax information
    tax_inclusive = models.BooleanField(default=False)
    taxes = models.JSONField(default=list, blank=True)  # Store tax details
    
    # GHL item ID
    ghl_item_id = models.CharField(max_length=100, null=True, blank=True)
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return f"{self.name} - {self.amount} {self.currency}"