from rest_framework import serializers

from .models import Service, Contact, Job, Payout, UserPercentage
from ghl_auth.models import GHLUser



class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = '__all__'

class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = '__all__'

class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = '__all__'

    def validate_contact_id(self, value):
        if not Contact.objects.using('external').filter(contact_id=value).exists():
            raise serializers.ValidationError("Invalid contact ID.")
        return value

    def validate_service_ids(self, value):
        invalid_services = [
            sid for sid in value
            if not Service.objects.using('external').filter(service_id=sid).exists()
        ]
        if invalid_services:
            raise serializers.ValidationError(f"Invalid service IDs: {invalid_services}")
        return value
    
class GHLUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = GHLUser
        fields = "__all__"


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = ["opportunity_id", "amount", "created_at"]


class PayrollSerializer(serializers.ModelSerializer):
    total_payout = serializers.SerializerMethodField()
    payouts = PayoutSerializer(many=True)

    class Meta:
        model = GHLUser
        fields = ["user_id", "name", "email", "total_payout", "payouts"]

    def get_total_payout(self, obj):
        return round(sum(p.amount for p in obj.payouts.all()), 2)

class GHLUserSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = GHLUser
        fields = ["id", "user_id", "name", "email"]
    
class UserPercentageListSerializer(serializers.ModelSerializer):
    user = GHLUserSimpleSerializer(read_only=True)

    class Meta:
        model = UserPercentage
        fields = ["id", "user", "percentage"]

class UserPercentageEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPercentage
        fields = ["percentage"]