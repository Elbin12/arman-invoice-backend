import logging
import requests
from ghl_auth.models import GHLAuthCredentials
from ghl_auth.token_service import ensure_fresh_credentials, ghl_request

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings

PIPELINE_ID = settings.PIPELINE_ID
PIPELINE_STAGE_ID = settings.PIPELINE_STAGE_ID
logger = logging.getLogger(__name__)

def get_or_create_product(access_token, location_id, product_name, custom_data, credentials=None):
    search_url = f"https://services.leadconnectorhq.com/products/?locationId={location_id}&search={product_name}"

    try:
        response = ghl_request(
            "GET",
            search_url,
            credentials=credentials,
            location_id=location_id,
            headers={"Authorization": f"Bearer {access_token}"} if access_token and not credentials else None,
        )
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
    return create_product(access_token, location_id, product_name, custom_data, credentials=credentials)


def create_product(access_token, location_id, product_name, custom_data, credentials=None):
    try:
        price = float(custom_data.get("price", 0))
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
        response = ghl_request(
            "POST",
            url,
            credentials=credentials,
            location_id=location_id,
            json=product_data,
            headers={"Authorization": f"Bearer {access_token}"} if access_token and not credentials else None,
        )
        print(response.json(), 'response')
        if response.status_code in [200, 201]:
            product = response.json()
            product_id = product.get('_id')
            return {"productId": product_id}
        else:
            print(f"Failed to create product: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error creating product: {e}")

    return None


def create_opportunity(contact_id, name, monetary_value, is_first_time):
    """
    Create an opportunity in GHL.

    Args:
        contact_id (str): GHL contact ID
        name (str): Opportunity name
        location_id (str): Location ID
        monetary_value (float, optional): Opportunity value
        assigned_to (str, optional): User ID to assign the opportunity to

    Returns:
        dict: Response from GHL API
    """

    url = 'https://services.leadconnectorhq.com/opportunities/'

    credentials = ensure_fresh_credentials()

    customFields = [
        {
            'id':"agYegyuAdz6FU958UaES",
            "key":"is_first_time",
            "field_value":is_first_time
        }
    ]

    payload = {
        "contactId": contact_id,
        "name": name,
        "locationId": credentials.location_id,
        "pipelineId": PIPELINE_ID,  # Your hardcoded pipeline ID
        "pipelineStageId": PIPELINE_STAGE_ID,  # Your hardcoded stage ID
        "status": "open",  # You can change as needed
        "customFields":customFields
    }

    if monetary_value:
        payload["monetaryValue"] = monetary_value

    response = ghl_request("POST", url, credentials=credentials, json=payload)
    return response.json()

def create_invoice(name, contact_id, services, credentials, customer_address=None, companyName=None, phoneNo=None, contactName=None, contact_email=None, discount=None):
    """
    Create an invoice in GHL for the given contact.

    Args:
        contact_id (str): GHL contact ID
        location_id (str): GHL location ID
        services (list): List of services (product objects)
        credentials: GHLAuthCredentials instance
        customer_address (str, optional): Customer address
        companyName (str, optional): Company name
        phoneNo (str, optional): Phone number
        contactName (str, optional): Contact name
        contact_email (str, optional): Contact email (preferred from GHL contact or webhook payload)
        discount (dict, optional): Optional. When omitted or None, no discount is applied (value=0, type=fixed).
            When provided: { "value": number, "type": "percentage"|"fixed", "validOnProductIds": optional }

    Returns:
        dict: Response from GHL API
    """
    url = "https://services.leadconnectorhq.com/invoices/"

    # Validate email is provided and valid
    if not contact_email or not isinstance(contact_email, str) or "@" not in contact_email:
        return {"error": "Valid contact email is required. Email must be provided from GHL contact or webhook payload."}

    # Ensure token is usable before product/invoice calls; 401 path will refresh again.
    try:
        credentials = ensure_fresh_credentials(credentials)
    except Exception as e:
        logger.error("Unable to refresh GHL credentials before invoice create: %s", e)
        return {"error": f"GHL credentials unavailable: {e}"}

    line_items = []

    for service in services:
        product_name = service.get("name", "Unnamed Service")
        print("Processing service:", product_name)  # DEBUG

        product_info = get_or_create_product(
            credentials.access_token,
            credentials.location_id,
            product_name,
            custom_data=service,
            credentials=credentials,
        )
        if not product_info:
            print(f"Skipping service: {product_name} (no product info)")
            continue  # <-- change return to continue, so other services are still added

        line_item = {
            "name": product_name,
            "description": service.get("description", ""),
            "currency": "USD",
            "qty": service.get("quantity", 1),
            "amount": service.get("price", 0.0),
            "productId": product_info["productId"],
        }

        if service.get("price", 0.0) > 0:
            line_item["taxes"] = [
                {
                    "_id": "sales-tax-8-25",
                    "name": "Sales Tax",
                    "rate": 8.25,
                    "calculation": "exclusive",
                    "description": "8.25% standard US sales tax"
                }
            ]

        line_items.append(line_item)

    print("Final line_items payload:", line_items)  # DEBUG

    # Build discount for GHL API (optional: from webhook payload when provided; otherwise no discount)
    discount_value = 0
    discount_type = "fixed"
    valid_on_product_ids = None
    if discount is not None and isinstance(discount, dict):
        try:
            discount_value = float(discount.get("value", 0) or 0)
        except (TypeError, ValueError):
            discount_value = 0
        discount_type = (discount.get("type") or "fixed").lower()
        if discount_type not in ("percentage", "fixed"):
            discount_type = "fixed"
        valid_on_product_ids = discount.get("validOnProductIds")
    discount_payload = {"value": discount_value, "type": discount_type}
    if valid_on_product_ids is not None:
        discount_payload["validOnProductIds"] = valid_on_product_ids

    contactDetails = {
        "id":contact_id,
        "name": contactName or "",
        "email": contact_email,
        "address":{"addressLine1":customer_address or ""},
        "companyName": companyName or "",
        "phoneNo": phoneNo or ""
    }

    businessDetails = {
        "logoUrl":'https://storage.googleapis.com/msgsndr/b8qvo7VooP3JD3dIZU42/media/683efc8fd5817643ff8194f0.jpeg',
        "name":"TruShine Window Cleaning",
    }

    sentTo = {
        "email":[contact_email]
    }

    issue_date = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")

    payload = {
        "altId": credentials.location_id,
        "altType":'location',
        "name": name,
        "businessDetails":businessDetails,
        "currency":"USD",
        "items": line_items,
        "discount": discount_payload,
        "contactDetails":contactDetails,
        "issueDate":issue_date,
        "sentTo": sentTo,
        "liveMode":True,
        "tipsConfiguration":{
            "tipsEnabled": False,
            "tipsPercentage": []
        }
    }

    response = ghl_request("POST", url, credentials=credentials, json=payload)
    try:
        return response.json()
    except Exception:
        return {"error": f"Invalid GHL invoice response ({response.status_code}): {response.text[:300]}"}




def updateJob(data):
    pass



def add_followers(id, followers, credentials):
    url = f'https://services.leadconnectorhq.com/opportunities/{id}/followers'
    payload = {"followers": followers}
    try:
        response = ghl_request("POST", url, credentials=credentials, json=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def send_invoice(invoiceId):
    url = f'https://services.leadconnectorhq.com/invoices/{invoiceId}/send'
    try:
        credentials = ensure_fresh_credentials()
    except Exception as e:
        return {"error": str(e)}

    payload = {
        "altId": credentials.location_id,
        "altType":'location',
        "userId": credentials.user_id,
        "action":'email',
        "liveMode":True,
    }

    try:
        response = ghl_request("POST", url, credentials=credentials, json=payload)
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
    try:
        credentials = ensure_fresh_credentials()
    except Exception as e:
        print(f"Error getting GHL credentials: {e}")
        return {}

    url = f"https://services.leadconnectorhq.com/opportunities/{opportunity_id}"

    try:
        response = ghl_request("GET", url, credentials=credentials)
        print(response.json(), 'response fetch opp')
        if response.status_code == 200:
            return response.json().get("opportunity", {})
        else:
            print(f"Failed to fetch opportunity. Status: {response.status_code}")
            return {}
    except Exception as e:
        print(f"Error fetching opportunity by ID: {str(e)}")
        return {}


def _normalize_contacts(payload):
    """Normalize GHL contact search responses to a list of contact dicts."""
    if not payload or not isinstance(payload, dict):
        return []
    contact = payload.get("contact")
    if isinstance(contact, dict) and (contact.get("id") or contact.get("_id")):
        return [contact]
    contacts = payload.get("contacts")
    if isinstance(contacts, list):
        return [c for c in contacts if isinstance(c, dict)]
    return []


def search_ghl_contact(access_token, email, locationId, credentials=None):
    """
    Find a GHL contact by email for a location.

    Uses exact duplicate lookup first, then advanced search. The deprecated
    GET /contacts/?query= list API often returns empty even when the contact exists.
    Auto-refreshes on 401 Invalid JWT when credentials are available.
    """
    if not email:
        return []

    email = email.strip()

    # 1) Exact match via duplicate lookup
    dup_url = 'https://services.leadconnectorhq.com/contacts/search/duplicate'
    try:
        dup_resp = ghl_request(
            "GET",
            dup_url,
            credentials=credentials,
            location_id=locationId,
            params={"email": email, "locationId": locationId},
            headers={"Authorization": f"Bearer {access_token}"} if access_token and not credentials else None,
        )
        print("Duplicate lookup response:", dup_resp.status_code, dup_resp.text)
        if dup_resp.status_code == 200:
            contacts = _normalize_contacts(dup_resp.json())
            if contacts:
                return contacts
    except Exception as e:
        print(f"Error in duplicate contact lookup: {e}")

    # 2) Advanced search with exact email filter
    search_url = 'https://services.leadconnectorhq.com/contacts/search'
    try:
        search_resp = ghl_request(
            "POST",
            search_url,
            credentials=credentials,
            location_id=locationId,
            json={
                "locationId": locationId,
                "page": 1,
                "pageLimit": 10,
                "filters": [
                    {"field": "email", "operator": "eq", "value": email}
                ],
            },
        )
        print("Advanced search response:", search_resp.status_code, search_resp.text)
        if search_resp.status_code == 200:
            contacts = _normalize_contacts(search_resp.json())
            if contacts:
                return contacts
    except Exception as e:
        print(f"Error in advanced contact search: {e}")

    print(f"No GHL contact found for email via duplicate/search: {email}")
    return []


def get_ghl_contact(access_token, contact_id, credentials=None):
    url = f'https://services.leadconnectorhq.com/contacts/{contact_id}'
    response = ghl_request(
        "GET",
        url,
        credentials=credentials,
        headers={"Authorization": f"Bearer {access_token}"} if access_token and not credentials else None,
    )
    print("Get contact response:", response.status_code, response.text)
    if response.status_code != 200:
        return None
    return response.json().get("contact")

def update_contact(contact_id, data, credentials=None):
    url = f'https://services.leadconnectorhq.com/contacts/{contact_id}'
    try:
        credentials = ensure_fresh_credentials(credentials)
    except Exception as e:
        print(e, 'errorrr')
        return {'error': 'Error while updating ghl contact'}
    print(credentials, 'creee')

    try:
        response = ghl_request("PUT", url, credentials=credentials, json=data)
        print(response.json(), 'responseeeeee')
        return response.json()
    except Exception as e:
        print(e, 'errorrr')
        return {'error':'Error while updating ghl contact'}

def getBussiness(access_token, businessId, credentials=None):
    url = 'https://services.leadconnectorhq.com/businesses/'
    response = ghl_request(
        "GET",
        url,
        credentials=credentials,
        params={"businessId": businessId},
        headers={"Authorization": f"Bearer {access_token}"} if access_token and not credentials else None,
    )
    print("Raw response business:", response.status_code, response.text, response.json())
    return response.json().get("business", [])


def add_invoice_paid_tag_to_contact(contact_id, location_id=None):
    """
    Add "invoice_paid" tag to a GHL contact

    Args:
        contact_id: GHL contact ID
        location_id: Optional location ID for credentials lookup

    Returns:
        dict with success status and response data or error message
    """
    try:
        try:
            credentials = ensure_fresh_credentials(location_id=location_id)
        except Exception:
            print("No GHL credentials found for adding invoice_paid tag")
            return {"success": False, "error": "No GHL credentials found"}

        # Fetch contact to get existing tags
        url = f'https://services.leadconnectorhq.com/contacts/{contact_id}'

        try:
            get_response = ghl_request("GET", url, credentials=credentials)
            if get_response.status_code != 200:
                print(f"Failed to fetch contact {contact_id}: {get_response.status_code}")
                return {"success": False, "error": f"Failed to fetch contact: {get_response.status_code}"}

            contact_data = get_response.json().get("contact", {})
            existing_tags = contact_data.get("tags", [])

            # Ensure tags is a list
            if not isinstance(existing_tags, list):
                existing_tags = []

            # Check if "invoice_paid" tag already exists
            if "invoice_paid" in existing_tags:
                print(f"Contact {contact_id} already has invoice_paid tag")
                return {"success": True, "message": "Tag already exists"}

            # Add "invoice_paid" tag
            updated_tags = list(set(existing_tags + ["invoice_paid"]))
            payload = {"tags": updated_tags}

            # Update contact with new tags
            update_result = update_contact(contact_id, payload, credentials=credentials)

            if update_result.get("error"):
                print(f"Error updating contact tags: {update_result.get('error')}")
                return {"success": False, "error": update_result.get("error")}

            print(f"Successfully added invoice_paid tag to contact {contact_id}")
            return {"success": True, "data": update_result}

        except requests.exceptions.RequestException as e:
            error_msg = f"Request error adding tag to contact: {str(e)}"
            print(error_msg)
            return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Unexpected error adding invoice_paid tag: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return {"success": False, "error": error_msg}


def record_payment_in_ghl(invoice, amount_paid):
    """
    Record payment in GHL (GoHighLevel) for the invoice

    Args:
        invoice: Invoice model instance
        amount_paid: Decimal amount that was paid

    Returns:
        dict with success status and response data or error message
    """
    # Check if invoice has GHL invoice ID
    if not invoice.ghl_invoice_id:
        print(f"Invoice {invoice.invoice_number} does not have GHL invoice ID, skipping GHL payment recording")
        return {"success": False, "error": "No GHL invoice ID found"}

    try:
        credentials = ensure_fresh_credentials(location_id=invoice.location_id)
    except Exception as e:
        print(f"Error getting GHL credentials: {e}")
        return {"success": False, "error": f"Error getting credentials: {str(e)}"}

    # Prepare the API request
    url = f'https://services.leadconnectorhq.com/invoices/{invoice.ghl_invoice_id}/record-payment'

    # Prepare payment data
    from datetime import datetime
    payment_data = {
        "altId": invoice.location_id,
        "altType": "location",
        "mode": "card",
        "card": {
            "brand": "stripe",
            "last4": "****"
        },
        "notes": f"Payment received via Stripe for invoice {invoice.invoice_number}",
        "amount": float(amount_paid),
        "meta": {
            "stripe_payment_intent_id": invoice.stripe_payment_intent_id or "",
            "stripe_checkout_session_id": invoice.stripe_checkout_session_id or ""
        },
        "fulfilledAt": datetime.now().isoformat() + "Z"
    }

    try:
        response = ghl_request("POST", url, credentials=credentials, json=payment_data, timeout=30)

        if response.status_code in [200, 201]:
            print(f"Successfully recorded payment in GHL for invoice {invoice.invoice_number}")
            return {
                "success": True,
                "data": response.json() if response.text else {}
            }
        else:
            error_msg = f"GHL API returned status {response.status_code}: {response.text}"
            print(f"Error recording payment in GHL: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "status_code": response.status_code
            }
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error recording payment in GHL: {str(e)}"
        print(error_msg)
        return {
            "success": False,
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"Unexpected error recording payment in GHL: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": error_msg
        }


def trigger_tip_webhook(job_id, tip_amount, notes=None):
    """
    Call Service Pilot tip webhook after a customer adds a tip and completes payment.
    POST https://services.theservicepilot.com/api/job/tip-webhook/
    """
    if not job_id or tip_amount is None or float(tip_amount) <= 0:
        return {"success": False, "error": "job_id and positive tip_amount required"}
    url = "https://services.theservicepilot.com/api/job/tip-webhook/"
    payload = {
        "job_id": str(job_id),
        "tip_amount": round(float(tip_amount), 2),
        "notes": (notes or "").strip() or "Customer tip from payment",
    }
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if response.status_code in (200, 201, 204):
            print(f"Tip webhook sent for job_id={job_id}, tip_amount={tip_amount}")
            return {"success": True, "data": response.json() if response.text else {}}
        return {
            "success": False,
            "error": f"Tip webhook returned {response.status_code}: {response.text}",
            "status_code": response.status_code,
        }
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error calling tip webhook: {e}"
        print(error_msg)
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error calling tip webhook: {e}"
        print(error_msg)
        return {"success": False, "error": error_msg}