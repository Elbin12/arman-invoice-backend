from rest_framework import serializers

from .models import Service, Contact, Job, Payout
from ghl_auth.models import GHLUser

from datetime import datetime



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


class GHLUserPercentageEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = GHLUser
        fields = ["percentage"]


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = ["opportunity_id", "opportunity_name", "amount", "created_at"]


class PayrollSerializer(serializers.ModelSerializer):
    total_payout = serializers.SerializerMethodField()
    payouts = serializers.SerializerMethodField()

    class Meta:
        model = GHLUser
        fields = ["user_id", "name", "email", "percentage", "total_payout", "payouts"]

    def get_filtered_payouts(self, obj):
        payouts = obj.payouts.all()

        start_date = self.context.get("start_date")
        end_date = self.context.get("end_date")

        print(start_date, end_date, 'dates')

        if start_date:
            try:
                start_date = datetime.fromisoformat(start_date)
                payouts = payouts.filter(created_at__gte=start_date)
            except ValueError:
                pass

        if end_date:
            try:
                end_date = datetime.fromisoformat(end_date)
                payouts = payouts.filter(created_at__lte=end_date)
            except ValueError:
                pass

        return payouts

    def get_total_payout(self, obj):
        return round(sum(p.amount for p in obj.payouts.all()), 2)

    def get_payouts(self, obj):
        payouts = self.get_filtered_payouts(obj)
        return PayoutSerializer(payouts, many=True).data