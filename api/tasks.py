import requests
from celery import shared_task
from ghl_auth.models import GHLAuthCredentials
from django.conf import settings

from api.utils import send_invoice, extract_invoice_id_from_name


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
def handle_webhook_event(data, event_type):
    try:
        if event_type in ["OpportunityStatusUpdate"]:
            opportunity = data.get("opportunity", {})
            status = opportunity.get("status", "").lower()
            opportunity_name = opportunity.get("name", "")
            
            # Only proceed if status is completed
            if status == "completed":
                invoice_id = extract_invoice_id_from_name(opportunity_name)

                if invoice_id:
                    send_invoice(invoice_id)
                else:
                    print(f"Invoice ID could not be extracted from opportunity name: {opportunity_name}")
    except Exception as e:
        print(f"Error handling webhook event: {str(e)}")