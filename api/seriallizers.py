from rest_framework import serializers

from .models import Service, Contact, Job, Payout
from ghl_auth.models import GHLUser, CommissionRule

from datetime import datetime, timedelta
from pytz import timezone, UTC
from django.utils.timezone import localtime



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

class CommissionRuleEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommissionRule
        fields = ["num_other_employees", "commission_percentage"]

class CommissionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommissionRule
        fields = ['num_other_employees', 'commission_percentage']

class PayoutSerializer(serializers.ModelSerializer):
    created_at = serializers.SerializerMethodField()
    class Meta:
        model = Payout
        fields = ["opportunity_id", "opportunity_name", "amount", "created_at"]

    def get_created_at(self, obj):
        chicago_tz = timezone("America/Chicago")
        return obj.created_at.astimezone(chicago_tz).strftime('%Y-%m-%d %I:%M:%S %p')


class PayrollSerializer(serializers.ModelSerializer):
    total_payout = serializers.SerializerMethodField()
    payouts = serializers.SerializerMethodField()
    commission_rules = CommissionRuleSerializer(many=True, read_only=True)

    class Meta:
        model = GHLUser
        fields = ["user_id", "name", "email", "percentage", "total_payout", "payouts", "commission_rules"]

    def get_filtered_payouts(self, obj):
        payouts = obj.payouts.all()
        chicago_tz = timezone("America/Chicago")

        start_date = self.context.get("start_date")
        end_date = self.context.get("end_date")

        if start_date:
            try:
                start_date = datetime.fromisoformat(start_date)
                # Convert from naive → Chicago time → UTC
                start_date = chicago_tz.localize(start_date).astimezone(UTC)
                payouts = payouts.filter(created_at__gte=start_date)
            except ValueError:
                pass

        if end_date:
            try:
                end_date = datetime.fromisoformat(end_date)
                end_date = end_date + timedelta(days=1) - timedelta(microseconds=1)
                end_date = chicago_tz.localize(end_date).astimezone(UTC)
                payouts = payouts.filter(created_at__lte=end_date)
            except ValueError:
                pass

        return payouts

    def get_total_payout(self, obj):
        payouts = self.get_filtered_payouts(obj)
        return round(sum(p.amount for p in payouts), 2)

    def get_payouts(self, obj):
        payouts = self.get_filtered_payouts(obj)
        return PayoutSerializer(payouts, many=True, context=self.context).data