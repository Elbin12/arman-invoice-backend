import requests
from celery import shared_task
from ghl_auth.models import GHLAuthCredentials
from django.conf import settings
from decimal import Decimal

from api.utils import send_invoice, extract_invoice_id_from_name, fetch_opportunity_by_id
from ghl_auth.models import GHLUser, CommissionRule
from .models import Payout

from decimal import Decimal, ROUND_HALF_UP

GHL_CLIENT_ID = settings.GHL_CLIENT_ID
GHL_CLIENT_SECRET = settings.GHL_CLIENT_SECRET

@shared_task
def make_api_call():
    tokens = GHLAuthCredentials.objects.all()

    for credentials in tokens:
    
        print("credentials tokenL", credentials)
        refresh_token = credentials.refresh_token

        
        response = requests.post('https://services.leadconnectorhq.com/oauth/token', data={
            'grant_type': 'refresh_token',
            'client_id': GHL_CLIENT_ID,
            'client_secret': GHL_CLIENT_SECRET,
            'refresh_token': refresh_token
        })
        
        new_tokens = response.json()
        obj, created = GHLAuthCredentials.objects.update_or_create(
                location_id= new_tokens.get("locationId"),
                defaults={
                    "access_token": new_tokens.get("access_token"),
                    "refresh_token": new_tokens.get("refresh_token"),
                    "expires_in": new_tokens.get("expires_in"),
                    "scope": new_tokens.get("scope"),
                    "user_type": new_tokens.get("userType"),
                    "company_id": new_tokens.get("companyId"),
                    "user_id":new_tokens.get("userId"),
                }
            )
        print("refreshed: ", obj)


@shared_task
def handle_webhook_event(data):
    try:
        opportunity_name = data.get('opportunity_name')
        invoice_id = extract_invoice_id_from_name(opportunity_name)

        print('sendinggg', invoice_id)
        if invoice_id:
            send_invoice(invoice_id)
            print('sent')
        else:
            print(f"Invoice ID could not be extracted from opportunity name: {opportunity_name}")

    except Exception as e:
        print(f"Error handling webhook event: {str(e)}")

@shared_task
def payroll_webhook_event(data):
    try:
        opportunity_id = data.get('id')
        fetched_opportunity = fetch_opportunity_by_id(opportunity_id)

        assignedTo = fetched_opportunity.get("assignedTo")
        opportunity_name = fetched_opportunity.get('name')
        monetary_value = Decimal(str(fetched_opportunity.get("monetaryValue")))
        follower_ids = fetched_opportunity.get("followers", [])

        print('followers', follower_ids)
        is_first_time = False
        custom_fields = fetched_opportunity.get("customFields", [])
        for field in custom_fields:
            if field.get("id") == "agYegyuAdz6FU958UaES":
                field_value = field.get("fieldValue")
                if isinstance(field_value, list) and field_value and field_value[0] is True:
                    is_first_time = True
                break
        print(is_first_time, 'is_first', assignedTo)

        try:
            estimator = GHLUser.objects.get(user_id=assignedTo)
            percentage = 15 if is_first_time else 2
            payout_amount = (monetary_value * percentage) / Decimal("100.00")
            payout_amount = payout_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Ensure unique payout per opportunity-user combo
            Payout.objects.get_or_create(
                opportunity_id=opportunity_id,
                opportunity_name=opportunity_name,
                user=estimator,
                defaults={
                    "amount": payout_amount
                }
            )
        except GHLUser.DoesNotExist:
            print(f"User with ID {assignedTo} for estimator does not exist.")
        
        followers_count = len(follower_ids)
        print(followers_count, 'followers_count')
        num_other_employees = followers_count-1
        print(num_other_employees, 'num_other_employees')

        for follower_id in follower_ids:
            try:
                user = GHLUser.objects.get(user_id=follower_id)
            except GHLUser.DoesNotExist:
                print(f"User with ID {follower_id} does not exist.")
                continue

            try:
                if num_other_employees == 0:
                    # Use flat_percentage stored in GHLUser
                    payout_amount = (monetary_value * user.percentage) / Decimal("100.00")
                    payout_amount = payout_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                else:
                    commission = CommissionRule.objects.get(ghl_user=user, num_other_employees=num_other_employees)
                    payout_amount = (monetary_value * commission.commission_percentage) / Decimal("100.00")

                # Ensure unique payout per opportunity-user combo
                Payout.objects.get_or_create(
                    opportunity_id=opportunity_id,
                    opportunity_name=opportunity_name,
                    user=user,
                    defaults={
                        "amount": payout_amount
                    }
                )
            except CommissionRule.DoesNotExist:
                print(f"commission not found for {follower_id} with {num_other_employees} other employees")
                continue
    except Exception as e:
        print(f"Error handling webhook event: {str(e)}")


@shared_task
def handle_user_create_webhook_event(data, event_type):
    try:
        if event_type in ["UserCreate"]:
            user_id = data.get("id")
            user, created = GHLUser.objects.update_or_create(
                user_id=user_id,
                defaults={
                    "first_name": data.get("firstName"),
                    "last_name": data.get("lastName"),
                    "name": data.get("name"),
                    "email": data.get("email"),
                    "phone": data.get("phone"),
                    "location_id": data.get("locationId"),
                }
            )
            print("User created/updated:", user_id)
    except Exception as e:
        print(f"Error handling webhook event: {str(e)}")