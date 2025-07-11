from django.db import models

# Create your models here.


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