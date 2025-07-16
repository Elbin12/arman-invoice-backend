import requests
from celery import shared_task
from ghl_auth.models import GHLAuthCredentials
from django.conf import settings
from decimal import Decimal

from api.utils import send_invoice, extract_invoice_id_from_name
from ghl_auth.models import GHLUser
from .models import Payout

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


def handle_webhook_event(data):
    try:
        opportunity = data.get("opportunity", {})
        opportunity_id = opportunity.get('id','')
        opportunity_name = opportunity.get("name", "")
        monetary_value = Decimal(str(opportunity.get("monetaryValue", 0)))
        follower_ids = opportunity.get("followers", [])

        print('invoice id getting', follower_ids)
        invoice_id = extract_invoice_id_from_name(opportunity_name)

        print('sendinggg', invoice_id)
        if invoice_id:
            send_invoice(invoice_id)
            print('sent')
        else:
            print(f"Invoice ID could not be extracted from opportunity name: {opportunity_name}")

        for follower_id in follower_ids:
            try:
                user = GHLUser.objects.get(user_id=follower_id)
            except GHLUser.DoesNotExist:
                print(f"User with ID {follower_id} does not exist.")
                continue

            payout_amount = (monetary_value * user.percentage) / Decimal("100.00")

            # Ensure unique payout per opportunity-user combo
            Payout.objects.get_or_create(
                opportunity_id=opportunity_id,
                user=user,
                defaults={
                    "amount": float(payout_amount)
                }
            )
    except Exception as e:
        print(f"Error handling webhook event: {str(e)}")