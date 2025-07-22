from django.db import models

# Create your models here.


class GHLAuthCredentials(models.Model):
    user_id = models.CharField(max_length=255)
    access_token = models.TextField()
    refresh_token = models.TextField()
    expires_in = models.IntegerField()
    scope = models.TextField(null=True, blank=True)
    user_type = models.CharField(max_length=50, null=True, blank=True)
    company_id = models.CharField(max_length=255, null=True, blank=True)
    location_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.user_id} - {self.company_id}"
    
class GHLUser(models.Model):
    user_id = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=100, null=True)
    last_name = models.CharField(max_length=100, null=True)
    name = models.CharField(max_length=200, null=True)
    email = models.EmailField(null=True)
    phone = models.CharField(max_length=20, null=True)
    calendar_id = models.CharField(max_length=50, null=True, blank=True)
    location_id = models.CharField(max_length=50, null=True, blank=True, default="")
    percentage = models.DecimalField(decimal_places=2, max_digits=10, default=20)

    def __str__(self):
        return self.name
    
class CommissionRule(models.Model):
    ghl_user = models.ForeignKey(GHLUser, on_delete=models.CASCADE, related_name='commission_rules')
    num_other_employees = models.IntegerField(help_text="0 means working alone")
    commission_percentage = models.DecimalField(decimal_places=2, max_digits=5)

    class Meta:
        unique_together = ['ghl_user', 'num_other_employees']