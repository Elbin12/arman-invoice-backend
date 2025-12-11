import requests, logging
from celery import shared_task
from ghl_auth.models import GHLAuthCredentials
from django.conf import settings
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta

from api.utils import send_invoice, extract_invoice_id_from_name, fetch_opportunity_by_id, search_ghl_contact, create_invoice, update_contact, getBussiness
from ghl_auth.models import GHLUser, CommissionRule
from .models import Payout, Invoice, InvoiceItem


GHL_CLIENT_ID = settings.GHL_CLIENT_ID
GHL_CLIENT_SECRET = settings.GHL_CLIENT_SECRET

logger = logging.getLogger(__name__)

# @shared_task
# def make_api_call():
#     tokens = GHLAuthCredentials.objects.all()

#     for credentials in tokens:
    
#         print("credentials tokenL", credentials)
#         refresh_token = credentials.refresh_token

        
#         response = requests.post('https://services.leadconnectorhq.com/oauth/token', data={
#             'grant_type': 'refresh_token',
#             'client_id': GHL_CLIENT_ID,
#             'client_secret': GHL_CLIENT_SECRET,
#             'refresh_token': refresh_token
#         })
        
#         new_tokens = response.json()
#         obj, created = GHLAuthCredentials.objects.update_or_create(
#                 location_id= new_tokens.get("locationId"),
#                 defaults={
#                     "access_token": new_tokens.get("access_token"),
#                     "refresh_token": new_tokens.get("refresh_token"),
#                     "expires_in": new_tokens.get("expires_in"),
#                     "scope": new_tokens.get("scope"),
#                     "user_type": new_tokens.get("userType"),
#                     "company_id": new_tokens.get("companyId"),
#                     "user_id":new_tokens.get("userId"),
#                 }
#             )
#         print(response, 'responseee', new_tokens)
#         print("refreshed: ", obj)

@shared_task
def make_api_call():
    """Refresh OAuth tokens for all GHL credentials"""
    tokens = GHLAuthCredentials.objects.all()
    
    if not tokens.exists():
        logger.warning("No GHL credentials found to refresh")
        return

    for credentials in tokens:
        try:
            logger.info(f"Refreshing token for location: {credentials.location_id}")
            refresh_token = credentials.refresh_token

            # Make the refresh request
            response = requests.post(
                'https://services.leadconnectorhq.com/oauth/token',
                data={
                    'grant_type': 'refresh_token',
                    'client_id': GHL_CLIENT_ID,
                    'client_secret': GHL_CLIENT_SECRET,
                    'refresh_token': refresh_token
                },
                timeout=10  # Add timeout
            )
            
            # Check if request was successful
            if response.status_code != 200:
                logger.error(
                    f"Token refresh failed for location {credentials.location_id}. "
                    f"Status: {response.status_code}, Response: {response.text}"
                )
                continue
            
            # Parse response
            new_tokens = response.json()
            
            # Validate response contains required fields
            if 'access_token' not in new_tokens or 'refresh_token' not in new_tokens:
                logger.error(
                    f"Invalid token response for location {credentials.location_id}: "
                    f"{new_tokens}"
                )
                continue
            
            # Update credentials
            obj, created = GHLAuthCredentials.objects.update_or_create(
                location_id=new_tokens.get("locationId"),
                defaults={
                    "access_token": new_tokens.get("access_token"),
                    "refresh_token": new_tokens.get("refresh_token"),
                    "expires_in": new_tokens.get("expires_in"),
                    "scope": new_tokens.get("scope"),
                    "user_type": new_tokens.get("userType"),
                    "company_id": new_tokens.get("companyId"),
                    "user_id": new_tokens.get("userId"),
                }
            )
            
            action = "created" if created else "updated"
            logger.info(
                f"Successfully {action} credentials for location {obj.location_id}"
            )

            logger.info(
                f"Status: {response.status_code}, Response: {response.text}"
            )
            
        except requests.RequestException as e:
            logger.error(
                f"Network error refreshing token for location {credentials.location_id}: {e}"
            )
        except Exception as e:
            logger.error(
                f"Unexpected error refreshing token for location {credentials.location_id}: {e}",
                exc_info=True
            )


def save_invoice_to_db(ghl_response, contact_id, contact_name, contact_email, contact_phone, contact_address, company_name, location_id):
    """
    Save invoice data from GHL response to database
    """
    try:
        # Parse dates
        issue_date_str = ghl_response.get("issueDate", "")
        due_date_str = ghl_response.get("dueDate", "")
        
        issue_date = None
        due_date = None
        
        if issue_date_str:
            try:
                issue_date = datetime.fromisoformat(issue_date_str.replace('Z', '+00:00')).date()
            except:
                issue_date = datetime.now().date()
        
        if due_date_str:
            try:
                due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00')).date()
            except:
                # Default to 13 days from issue date
                issue_date = issue_date or datetime.now().date()
                due_date = (datetime.now() + timedelta(days=13)).date()
        
        if not issue_date:
            issue_date = datetime.now().date()
        if not due_date:
            due_date = (datetime.now() + timedelta(days=13)).date()
        
        # Extract business details
        business_details = ghl_response.get("businessDetails", {})
        business_name = business_details.get("name", "TruShine Window Cleaning")
        business_logo_url = business_details.get("logoUrl")
        
        # Extract contact details from response
        contact_details = ghl_response.get("contactDetails", {})
        contact_name = contact_details.get("name") or contact_name
        contact_email = contact_details.get("email") or contact_email
        contact_phone = contact_details.get("phoneNo") or contact_phone
        contact_address_obj = contact_details.get("address", {})
        contact_address = contact_address_obj.get("addressLine1") or contact_address
        company_name = contact_details.get("companyName") or company_name
        
        # Create or update invoice
        invoice, created = Invoice.objects.update_or_create(
            ghl_invoice_id=ghl_response.get("_id"),
            defaults={
                "invoice_number": ghl_response.get("invoiceNumber"),
                "name": ghl_response.get("name"),
                "status": ghl_response.get("status", "draft"),
                "currency": ghl_response.get("currency", "USD"),
                "total": Decimal(str(ghl_response.get("total", 0))),
                "invoice_total": Decimal(str(ghl_response.get("invoiceTotal", 0))) if ghl_response.get("invoiceTotal") else None,
                "amount_paid": Decimal(str(ghl_response.get("amountPaid", 0))),
                "amount_due": Decimal(str(ghl_response.get("amountDue", 0))),
                "issue_date": issue_date,
                "due_date": due_date,
                "contact_id": contact_id,
                "contact_name": contact_name,
                "contact_email": contact_email,
                "contact_phone": contact_phone,
                "contact_address": contact_address,
                "contact_company_name": company_name,
                "business_name": business_name,
                "business_logo_url": business_logo_url,
                "location_id": location_id,
                "company_id": ghl_response.get("companyId"),
                "live_mode": ghl_response.get("liveMode", True),
                "raw_data": ghl_response,
            }
        )



        print("invoice", invoice.token)
        
        # Save invoice items
        invoice_items = ghl_response.get("invoiceItems", [])
        for item_data in invoice_items:
            InvoiceItem.objects.update_or_create(
                invoice=invoice,
                ghl_item_id=item_data.get("_id"),
                defaults={
                    "name": item_data.get("name", ""),
                    "description": item_data.get("description"),
                    "currency": item_data.get("currency", "USD"),
                    "quantity": Decimal(str(item_data.get("qty", 1))),
                    "amount": Decimal(str(item_data.get("amount", 0))),
                    "product_id": item_data.get("productId"),
                    "tax_inclusive": item_data.get("taxInclusive", False),
                    "taxes": item_data.get("taxes", []),
                }
            )
        
        return invoice
    except Exception as e:
        logger.error(f"Error saving invoice to database: {e}", exc_info=True)
        raise


@shared_task
def handle_webhook_event(data):
    try:
        customer_email = data.get("customer_email")
        customer_name = data.get("customer_name")
        services = data.get("selected_services", [])
        customer_address = data.get("customer_address")
        location_id = data.get("location_id")

        if not customer_email:
            print("No customer email in webhook payload.")
            return {"error": "Customer email missing"}

        if location_id:
            credentials = GHLAuthCredentials.objects.get(location_id=location_id)
        else:
            credentials = GHLAuthCredentials.objects.first()

        # Search contact
        contacts = search_ghl_contact(credentials.access_token, customer_email, credentials.location_id)
        if not contacts:
            print(f"No GHL contact found for email: {customer_email}")
            return {"error": f"Contact not found for {customer_email}"}

        contact_id = contacts[0].get("id") or contacts[0].get("_id")

        # bussinessName = None
        companyName = contacts[0].get("companyName")
        phoneNo = contacts[0].get("phone")
        contactName = contacts[0].get("contactName")
        # if businessId:
        #     print(f"Contact belongs to businessId: {businessId}.")
        #     business_info = getBussiness(credentials.access_token, businessId)
        #     bussinessName = business_info.get("name")

        print("companyName", companyName)
        tags = contacts[0].get("tags")
        if not contact_id:
            print("Contact found, but ID missing.")
            return {"error": "Invalid contact data"}
        
        print("Contact found,", contact_id)
        # Invoice name
        invoice_name = f"Invoice for {customer_name or customer_email} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # Create invoice
        response = create_invoice(
            name=invoice_name,
            contact_id=contact_id,
            services=services,
            credentials=credentials,
            customer_address=customer_address,
            companyName=companyName,
            phoneNo=phoneNo,
            contactName=contactName,
        )

        print("Invoice response:", response)
        print("Tags before check:", tags)
        if response and not response.get("error"):
            invoice_id = response.get("_id")

            # Save invoice to database if location_id matches
            saved_invoice = None
            location_id = "b8qvo7VooP3JD3dIZU42"
            if location_id == "b8qvo7VooP3JD3dIZU42":
                try:
                    saved_invoice = save_invoice_to_db(response, contact_id, contactName, contacts[0].get("email"), phoneNo, customer_address, companyName, location_id)
                    print(f"Invoice saved to database with token: {saved_invoice.token}")
                except Exception as e:
                    print(f"Error saving invoice to database: {e}")
                    logger.error(f"Error saving invoice to database: {e}", exc_info=True)

            existing_tags = tags if isinstance(tags, list) else []
            print("Existing tags:", existing_tags)

            try:
                if "card authorized" not in [t.lower() for t in existing_tags]:
                    print("Card not authorized → sending invoice...")
                    send_resp = send_invoice(invoice_id)
                    print("Send invoice response:", send_resp)
                    
                    # Update invoice status if saved
                    if saved_invoice and send_resp and not send_resp.get("error"):
                        saved_invoice.status = "sent"
                        if send_resp.get("invoice", {}).get("sentAt"):
                            try:
                                sent_at_str = send_resp.get("invoice", {}).get("sentAt")
                                saved_invoice.sent_at = datetime.fromisoformat(sent_at_str.replace('Z', '+00:00'))
                            except:
                                pass
                        saved_invoice.save()
                else:
                    print("Card authorized → skipping invoice send.")
                    send_resp = "skipped"
            except Exception as e:
                print("Error sending invoice:", e)
                send_resp = None

            # Avoid duplicates
            updated_tags = list(set(existing_tags + ["Invoice Created"]))
            payload = {"tags": updated_tags}
            
            # Add invoice URL to custom field if location matches and invoice was saved
            if location_id == "b8qvo7VooP3JD3dIZU42" and saved_invoice:
                try:
                    # Get existing custom fields from contact
                    existing_custom_fields = contacts[0].get("customFields") or []
                    if not isinstance(existing_custom_fields, list):
                        existing_custom_fields = []
                    
                    # Get FRONTEND_URL from settings
                    frontend_url = settings.FRONTEND_URL or "http://localhost:5173"
                    # Remove trailing slash if present
                    frontend_url = frontend_url.rstrip('/')
                    
                    # Construct invoice URL
                    invoice_url = f"{frontend_url}/invoice/{saved_invoice.token}/"
                    
                    # Check if custom field already exists
                    custom_field_id = "G4IXyj5y49rKinuXbnCA"
                    custom_fields_updated = False
                    
                    # Update existing custom field if it exists
                    for field in existing_custom_fields:
                        if field.get("id") == custom_field_id:
                            field["field_value"] = invoice_url
                            custom_fields_updated = True
                            break
                    
                    # Add new custom field if it doesn't exist
                    if not custom_fields_updated:
                        existing_custom_fields.append({
                            "id": custom_field_id,
                            "field_value": invoice_url
                        })
                    
                    # Add customFields to payload
                    payload["customFields"] = existing_custom_fields
                    print(f"Adding invoice URL to custom field: {invoice_url}")
                    print(f"Custom fields payload: {payload.get('customFields')}")
                except Exception as e:
                    print(f"Error adding invoice URL to custom field: {e}")
                    logger.error(f"Error adding invoice URL to custom field: {e}", exc_info=True)
            
            update_resp = update_contact(contact_id, payload)
            print("Contact update response:", update_resp)

            result = {
                "invoice": response,
                "contact_update": update_resp,
                "invoice_send": send_resp
            }
            
            # Add invoice token to response if saved
            if saved_invoice:
                result["invoice_token"] = str(saved_invoice.token)
                result["invoice_url"] = f"/invoice/{saved_invoice.token}/"
            
            return result

        return response

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