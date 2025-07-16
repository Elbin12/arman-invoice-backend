import requests
from ghl_auth.models import GHLAuthCredentials
from api.models import Contact

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings

PIPELINE_ID = settings.PIPELINE_ID
PIPELINE_STAGE_ID = settings.PIPELINE_STAGE_ID

def get_or_create_product(access_token, location_id, product_name, custom_data):
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}',
        'Version': '2021-07-28'
    }

    search_url = f"https://services.leadconnectorhq.com/products/?locationId={location_id}&search={product_name}"
    
    try:
        response = requests.get(search_url, headers=headers)
        if response.status_code == 200:
            products = response.json().get('products', [])
            if products:
                product = products[0]
                return {
                    "productId": product.get('_id'),
                    "priceId": product.get("prices", [{}])[0].get("_id")
                }
    except Exception as e:
        print(f"Error searching for product: {e}")
    
    # If not found, create it
    return create_product(access_token, location_id, product_name, custom_data)


def create_product(access_token, location_id, product_name, custom_data):
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'Version': '2021-07-28'
    }

    try:
        price = float(custom_data.get("Price", 0))
    except (ValueError, TypeError):
        price = 0.0

    product_data = {
        "name": product_name,
        "locationId": location_id,
        "description": f"Auto-created product: {custom_data.get('description')}",
        "productType": "SERVICE",
        "availableInStore": True,
        "isTaxesEnabled": False,
        "isLabelEnabled": False,
        "slug": product_name.lower().replace(" ", "-").replace("_", "-"),
    }

    url = "https://services.leadconnectorhq.com/products/"

    try:
        response = requests.post(url, headers=headers, json=product_data)
        print(response.json(), 'response')
        if response.status_code in [200, 201]:
            product = response.json()
            product_id = product.get('_id')
            # price_id = product.get('prices', [{}])[0].get('_id')  # Extract first price
            return {"productId": product_id}
        else:
            print(f"Failed to create product: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error creating product: {e}")
    
    return None


def create_opportunity(contact_id, name, monetary_value=None):
    """
    Create an opportunity in GHL.

    Args:
        contact_id (str): GHL contact ID
        name (str): Opportunity name
        location_id (str): Location ID
        monetary_value (float, optional): Opportunity value
        assigned_to (str, optional): User ID to assign the opportunity to
        services (list of str, optional): List of service IDs to include (if field is mapped)

    Returns:
        dict: Response from GHL API
    """

    url = 'https://services.leadconnectorhq.com/opportunities/'

    credentials = GHLAuthCredentials.objects.first()

    headers = {
        "Authorization": f"Bearer {credentials.access_token}",
        "Content-Type": "application/json",
        "Version": "2021-07-28"
    }

    payload = {
        "contactId": contact_id,
        "name": name,
        "locationId": credentials.location_id,
        "pipelineId": PIPELINE_ID,  # Your hardcoded pipeline ID
        "pipelineStageId": PIPELINE_STAGE_ID,  # Your hardcoded stage ID
        "status": "open",  # You can change as needed
    }

    if monetary_value:
        payload["monetaryValue"] = monetary_value

    # if services:
    #     # Replace 'custom_field_services_abc123' with the actual custom field ID from GHL
    #     payload["customField"] = {
    #         "custom_field_services_abc123": services
    #     }

    response = requests.post(
        url,
        json=payload,
        headers=headers
    )

    return response.json()

def create_invoice(name, contact_id, services, credentials):
    """
    Create an invoice in GHL for the given contact.

    Args:
        contact_id (str): GHL contact ID
        location_id (str): GHL location ID
        services (list): List of services (product objects)
        credentials: GHLAuthCredentials instance

    Returns:
        dict: Response from GHL API
    """
    url = "https://services.leadconnectorhq.com/invoices/"
    headers = {
        "Authorization": f"Bearer {credentials.access_token}",
        "Content-Type": "application/json",
        "Version": "2021-07-28"
    }

    contact = Contact.objects.using('external').filter(contact_id=contact_id).first()

    if not contact:
        return {"error": "Contact not found"}
    
    line_items = []

    for service in services:
        product_name = service.get("name", "Unnamed Service")
        product_info = get_or_create_product(
            credentials.access_token,
            credentials.location_id,
            product_name,
            custom_data=service
        )
        if not product_info:
            return {"error": f"Failed to get/create product for service: {product_name}"}

        line_items.append({
            "name": product_name,
            "description": service.get("description", ""),
            "currency": "USD",
            "qty": service.get("quantity", 1),
            "amount": service.get("price", 0.0),
            "productId": product_info["productId"],
            "taxes": [
                {
                    "_id": "sales-tax-8-25",  # Your custom identifier
                    "name": "Sales Tax",
                    "rate": 8.25,
                    "calculation": "exclusive",
                    "description": f"8.25% standard US sales tax"
                }
            ]
        })

    discount= {
        "value":0,
        "type":'fixed' #percentage, fixed
    }

    contactDetails = {
        "id":contact_id,
        "name": contact.first_name,
        "email": contact.email
    }

    businessDetails = {
        "logoUrl":'https://storage.googleapis.com/msgsndr/b8qvo7VooP3JD3dIZU42/media/683efc8fd5817643ff8194f0.jpeg',
        "name":"TruShine Window Cleaning",
    }

    sentTo = {
        "email":[contact.email]
    }

    issue_date = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")

    payload = {
        "altId": credentials.location_id,
        "altType":'location',
        "name": name,
        "businessDetails":businessDetails,
        "currency":"USD",
        "items": line_items,
        "discount":discount,
        "contactDetails":contactDetails,
        "issueDate":issue_date,
        "sentTo": sentTo,
        "liveMode":True,
        "tipsConfiguration":{
            "tipsEnabled": False,
            "tipsPercentage": []
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    return response.json()




def updateJob(data):
    pass



def add_followers(id, followers, credentials):
    url = f'https://services.leadconnectorhq.com/opportunities/{id}/followers'
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {credentials.access_token}',
        'Content-Type': 'application/json',
        'Version': '2021-07-28'
    }

    payload = {
        "followers": followers
    }

    try:
        response = requests.post(url=url, headers=headers, json=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}
    
def send_invoice(invoiceId):
    url = f'https://services.leadconnectorhq.com/invoices/{invoiceId}/send'
    credentials = GHLAuthCredentials.objects.first()
    
    headers = {
        'Authorization': f'Bearer {credentials.access_token}',
        'Version': '2021-07-28'
    }

    payload = {
        "altId": credentials.location_id,
        "altType":'location',
        "userId": credentials.user_id,
        "action":'email',
        "liveMode":True,
    }

    try:
        response = requests.post(url=url, headers=headers, json=payload)
        print('invoice_response', response.json())
        return response.json()
    except Exception as e:
        return {"error": str(e)}
    

def extract_invoice_id_from_name(opportunity_name):
    try:
        return opportunity_name.rsplit(" - ", 1)[-1]
    except Exception:
        return None

def fetch_opportunity_by_id(opportunity_id):
    """
    Fetch a single opportunity's details from GHL by ID.
    """
    credentials = GHLAuthCredentials.objects.first()

    url = f"https://services.leadconnectorhq.com/opportunities/{opportunity_id}"

    headers = {
        "Authorization": f"Bearer {credentials.access_token}",
        "Content-Type": "application/json",
        "Version": "2021-07-28"
    }

    try:
        response = requests.get(url=url, headers=headers)
        print(response.json(), 'response fetch opp')
        if response.status_code == 200:
            return response.json().get("opportunity", {})
        else:
            print(f"Failed to fetch opportunity. Status: {response.status_code}")
            return {}
    except Exception as e:
        print(f"Error fetching opportunity by ID: {str(e)}")
        return {}
