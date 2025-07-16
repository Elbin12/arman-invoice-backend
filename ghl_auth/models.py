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
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    calendar_id = models.CharField(max_length=50, null=True, blank=True)
    location_id = models.CharField(max_length=50, null=True, blank=True, default="")
    percentage = models.DecimalField(decimal_places=2, max_digits=10, default=20)

    def __str__(self):
        return self.name