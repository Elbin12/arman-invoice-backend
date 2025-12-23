from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.generics import ListAPIView
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
import stripe
import os

from .models import Service, Contact, Job, WebhookLog, Invoice, InvoiceItem
from ghl_auth.models import GHLAuthCredentials, GHLUser, CommissionRule
from .seriallizers import ServiceSerializer, ContactSerializer, GHLUserSerializer, PayrollSerializer, GHLUserPercentageEditSerializer, CommissionRuleEditSerializer
from .utils import create_opportunity, create_invoice, add_followers, record_payment_in_ghl, add_invoice_paid_tag_to_contact
from .tasks import handle_webhook_event, handle_user_create_webhook_event, payroll_webhook_event

import json
# Create your views here.


@csrf_exempt
def webhook_handler(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        print("date:----- ", data)
        WebhookLog.objects.create(data=data)
        # Call function directly (non-celery)
        result = handle_webhook_event(data)
        
        # Prepare response
        response_data = {"message": "Webhook received"}
        
        # If location_id matches and invoice was saved, include invoice URL in response
        location_id = data.get("location_id")
        if location_id == "b8qvo7VooP3JD3dIZU42" and result and result.get("invoice_url"):
            # The function already returns the full invoice URL
            response_data["invoice_url"] = result.get("invoice_url")
            response_data["invoice_token"] = result.get("invoice_token")
        
        return JsonResponse(response_data, status=200)
    except Exception as e:
        print(f"Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def user_create_webhook_handler(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        print("date:----- ", data)
        WebhookLog.objects.create(data=data)
        event_type = data.get("type")
        handle_user_create_webhook_event.delay(data, event_type)
        return JsonResponse({"message":"Webhook received"}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
@csrf_exempt
def payroll_webhook_handler(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        print("date:----- ", data)
        WebhookLog.objects.create(data=data)
        payroll_webhook_event.delay(data)
        return JsonResponse({"message":"Webhook received"}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

    
class ServicesView(ListAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceSerializer

    def get_queryset(self):
        name = self.request.query_params.get('name')
        queryset = Service.objects.using('external').all()
        if name:
            queryset = queryset.filter(name__icontains=name)
        return queryset
        
class ContactsView(ListAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ContactSerializer

    def get_queryset(self):
        search = self.request.query_params.get('search', '')
        return Contact.objects.using('external').filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )
    
class CreateJob(APIView):
    def post(self, request):
        contact_id = request.data.get('contact_id')
        assigned_to = request.data.get('assigned_to')
        name = request.data.get('title')
        is_first_time = request.data.get('is_first_time')
        credentials = GHLAuthCredentials.objects.first()
        if not credentials:
            return Response({"error": "No GHL credentials configured."}, status=500)
        
        assigned_to_ids = assigned_to if isinstance(assigned_to, list) else [assigned_to]
        num_other_employees = len(assigned_to_ids)-1

        for user_id in assigned_to_ids:
            try:
                user = GHLUser.objects.get(user_id=user_id)
            except GHLUser.DoesNotExist:
                return Response({"error": f"User with ID {user_id} not found."}, status=400)
            
            # Check commission rule
            rule = CommissionRule.objects.filter(ghl_user=user, num_other_employees=num_other_employees).first()

            if rule:
                continue  # Valid rule exists
            
            # If no rule but 0 user, check flat_percentage
            if num_other_employees == 0 and user.percentage is not None:
                if user.percentage is not None:
                    continue  # Valid flat_percentage
                else:
                    return Response({
                        "error": f"Please set the flat commission percentage for {user.first_name} {user.last_name} when working alone."
                    }, status=400)
            return Response({
                "error": f"No commission rule for user {user.first_name} {user.last_name} when working with {num_other_employees} other(s)."
            }, status=400)

        # You need to fetch service info from DB or pass it in request
        services = request.data.get("service")  # Expects a list of dicts

        # Step 1: Create Invoice
        invoice_response = create_invoice(
            name=name,
            contact_id=contact_id,
            services=services,
            credentials=credentials
        )

        invoice_id = invoice_response.get("_id")
        print(invoice_response)
        if not invoice_id:
            return Response({
                "message": "Job created, but failed to create invoice in GHL.",
                "invoice_error": invoice_response
            }, status=207)
        
        total = invoice_response.get("total")

        # Step 2: Create Opportunity with invoice reference
        opportunity_name = f"{name} - {invoice_id}"
        ghl_response = create_opportunity(
            contact_id=contact_id,
            name=opportunity_name,
            monetary_value=total,
            is_first_time=is_first_time
        )

        print(ghl_response.get('opportunity').get('id'), 'idddd')

        opp_id = ghl_response.get('opportunity').get("id")

        if opp_id:
            add_followers(opp_id, assigned_to, credentials)
            return Response({
                "message": "Job created, invoice and opportunity created in GHL.",
                "job_id": ghl_response.get("id"),
                "invoice_id": invoice_id,
                "ghl_opportunity_response": ghl_response
            }, status=201)
        else:
            return Response({
                "message": "Job & Invoice created, but failed to create opportunity.",
                "invoice_id": invoice_id,
                "ghl_error": ghl_response
            }, status=207)
        
class GHLUserSearchView(ListAPIView):
    serializer_class = GHLUserSerializer
    permission_classes = [AllowAny]


    def get_queryset(self):
        search = self.request.query_params.get('search', '')
        return GHLUser.objects.filter(
            Q(user_id__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )
    
class PayrollView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        user_id = request.query_params.get("user_id")

        users_qs = GHLUser.objects.prefetch_related("payouts").order_by("first_name")

        # If user_id is passed, filter to just that user
        if user_id:
            try:
                user = users_qs.get(user_id=user_id)
            except GHLUser.DoesNotExist:
                return Response({"detail": "User not found"}, status=404)

            serializer = PayrollSerializer(user, context={
                "start_date": start_date,
                "end_date": end_date
            })
        else:
            serializer = PayrollSerializer(users_qs, many=True, context={
                "start_date": start_date,
                "end_date": end_date
            })

        return Response(serializer.data)
    
    def put(self, request, user_id):
        try:
            user = GHLUser.objects.get(user_id=user_id)
        except GHLUser.DoesNotExist:
            return Response({"error": "User not found."}, status=404)

        serializer = GHLUserPercentageEditSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Percentage updated",
                "percentage": serializer.data
            })
        return Response(serializer.errors, status=400)
    
class CommissionRuleUpdateView(APIView):
    permission_classes = [IsAdminUser]

    def put(self, request, user_id):
        """
        Edit or add commission rules for a given user.
        """
        try:
            user = GHLUser.objects.get(user_id=user_id)
        except GHLUser.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        rules_data = request.data.get("commission_rules", [])
        if not rules_data:
            return Response({"error":"commission rules are required"}, status=400)
        if not isinstance(rules_data, list):
            return Response({"error": "commission_rules must be a list"}, status=400)

        serializer = CommissionRuleEditSerializer(data=rules_data, many=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        
        # Only collect submitted IDs for updating existing rules
        submitted_ids = [item.get("id") for item in serializer.validated_data if item.get("id")]

        # DELETE rules not in the new list
        CommissionRule.objects.filter(ghl_user=user).exclude(id__in=submitted_ids).delete()
        for item in serializer.validated_data:
            num_employees = item["num_other_employees"]
            percentage = item["commission_percentage"]

            rule, created = CommissionRule.objects.update_or_create(
                ghl_user=user,
                num_other_employees=num_employees,
                defaults={"commission_percentage": percentage}
            )
        return Response({"message": "Commission rules updated", "data":serializer.data}, status=200)
    
    def delete(self, request, user_id, commission_id):
        try:
            user = GHLUser.objects.get(user_id=user_id)
        except GHLUser.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        try:
            rule = CommissionRule.objects.get(id=commission_id, ghl_user=user)
        except CommissionRule.DoesNotExist:
            return Response({"error": "Commission rule not found for this user."}, status=404)

        rule.delete()
        return Response({"message": "Commission rule deleted successfully."}, status=200)


class CreateJobValidations(APIView):
    authentication_classes = []
    permission_classes = []
    def post(self, request):
        assigned_to = request.data.get('assigned_to')
        assigned_to_ids = assigned_to if isinstance(assigned_to, list) else [assigned_to]
        num_other_employees = len(assigned_to_ids)-1

        messages = []
        success = True

        if not assigned_to:
            return Response({"error": "Assigned users cannot be empty."}, status=400)

        for user_id in assigned_to_ids:
            try:
                user = GHLUser.objects.get(user_id=user_id)
            except GHLUser.DoesNotExist:
                messages.append(f"User with ID {user_id} not found.")
                success = False
                continue

            rule = CommissionRule.objects.filter(
                ghl_user=user, num_other_employees=num_other_employees
            ).first()

            if rule:
                messages.append(
                    f"{rule.commission_percentage}% for {user.first_name} (working with {num_other_employees} other(s))."
                )
            elif num_other_employees == 0 and user.percentage is not None:
                messages.append(
                    f"{user.percentage}% for {user.first_name} (working alone)."
                )
            else:
                messages.append(
                    f"No commission rule for {user.first_name} (working with {num_other_employees} other(s))."
                )
                success = False

        return Response({
            "success": success,
            "messages": messages
        })


class PublicInvoiceView(APIView):
    """
    Public view for invoice details - no authentication required
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def get(self, request, token):
        """
        Retrieve invoice details by token
        """
        try:
            invoice = Invoice.objects.prefetch_related('items').get(token=token)
        except Invoice.DoesNotExist:
            return Response(
                {"error": "Invoice not found"},
                status=404
            )
        
        # Serialize invoice data
        invoice_data = {
            "token": str(invoice.token),
            "invoice_number": invoice.invoice_number,
            "name": invoice.name,
            "status": invoice.status,
            "currency": invoice.currency,
            "total": str(invoice.total),
            "invoice_total": str(invoice.invoice_total) if invoice.invoice_total else None,
            "amount_paid": str(invoice.amount_paid),
            "amount_due": str(invoice.amount_due),
            "is_paid": invoice.is_paid,
            "issue_date": invoice.issue_date.isoformat() if invoice.issue_date else None,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "contact": {
                "name": invoice.contact_name,
                "email": invoice.contact_email,
                "phone": invoice.contact_phone,
                "address": invoice.contact_address,
                "company_name": invoice.contact_company_name,
            },
            "business": {
                "name": invoice.business_name,
                "logo_url": invoice.business_logo_url,
            },
            "items": [
                {
                    "name": item.name,
                    "description": item.description,
                    "quantity": str(item.quantity),
                    "amount": str(item.amount),
                    "currency": item.currency,
                    "taxes": item.taxes,
                    "tax_inclusive": item.tax_inclusive,
                }
                for item in invoice.items.all()
            ],
            "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
            "sent_at": invoice.sent_at.isoformat() if invoice.sent_at else None,
            "signature": invoice.signature,
            "signed_at": invoice.signed_at.isoformat() if invoice.signed_at else None,
        }
        
        return Response(invoice_data)


class SaveInvoiceSignature(APIView):
    """
    Save digital signature for an invoice
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request, token):
        """
        Save signature for invoice
        """
        try:
            invoice = Invoice.objects.get(token=token)
        except Invoice.DoesNotExist:
            return Response(
                {"error": "Invoice not found"},
                status=404
            )
        
        signature = request.data.get('signature')
        if not signature:
            return Response(
                {"error": "Signature is required"},
                status=400
            )
        
        # Save signature and timestamp
        invoice.signature = signature
        invoice.signed_at = timezone.now()
        invoice.save()
        
        return Response({
            "message": "Signature saved successfully",
            "signed_at": invoice.signed_at.isoformat()
        })


class VerifyPaymentStatus(APIView):
    """
    Verify and update payment status from Stripe checkout session
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request, token):
        """
        Verify payment status with Stripe and update invoice if paid
        """
        try:
            invoice = Invoice.objects.get(token=token)
        except Invoice.DoesNotExist:
            return Response(
                {"error": "Invoice not found"},
                status=404
            )
        
        # Check if invoice is already marked as paid
        if invoice.is_paid:
            return Response({
                "status": "paid",
                "message": "Invoice is already marked as paid",
                "invoice": {
                    "status": invoice.status,
                    "amount_paid": str(invoice.amount_paid),
                    "amount_due": str(invoice.amount_due),
                    "is_paid": invoice.is_paid
                }
            })
        
        # Check if we have a checkout session ID
        if not invoice.stripe_checkout_session_id:
            return Response({
                "status": "pending",
                "message": "No payment session found for this invoice"
            })
        
        # Initialize Stripe
        stripe_secret_key = settings.STRIPE_SECRET_KEY
        if not stripe_secret_key:
            return Response(
                {"error": "Stripe is not configured"},
                status=500
            )
        
        stripe.api_key = stripe_secret_key
        
        try:
            # Retrieve the checkout session from Stripe
            session = stripe.checkout.Session.retrieve(invoice.stripe_checkout_session_id)
            
            # Check payment status
            if session.payment_status == 'paid':
                # Payment was successful - update invoice
                payment_intent_id = session.payment_intent
                if payment_intent_id:
                    invoice.stripe_payment_intent_id = payment_intent_id
                
                # Get amount paid from session
                amount_total = session.amount_total or 0  # Amount in cents
                amount_paid = float(amount_total) / 100  # Convert to dollars
                
                # Check if invoice was already paid to avoid duplicate GHL calls
                was_already_paid = invoice.is_paid
                
                # Update invoice status
                invoice.status = 'paid'
                invoice.amount_paid = amount_paid
                invoice.amount_due = max(0, float(invoice.total) - amount_paid)
                invoice.save()
                
                # Record payment in GHL (only if it wasn't already paid)
                ghl_result = {"success": False, "error": "Already processed"}
                tag_result = {"success": False, "error": "Already processed"}
                if not was_already_paid:
                    ghl_result = record_payment_in_ghl(invoice, amount_paid)
                    if not ghl_result.get("success"):
                        print(f"Warning: Failed to record payment in GHL: {ghl_result.get('error')}")
                        # Don't fail the request if GHL recording fails, just log it
                    
                    # Add "invoice_paid" tag to GHL contact
                    tag_result = add_invoice_paid_tag_to_contact(invoice.contact_id, invoice.location_id)
                    if tag_result.get("success"):
                        print(f"Successfully added invoice_paid tag to contact {invoice.contact_id}")
                    else:
                        print(f"Warning: Failed to add invoice_paid tag to contact {invoice.contact_id}: {tag_result.get('error')}")
                
                return Response({
                    "status": "paid",
                    "message": "Payment verified and invoice updated",
                    "invoice": {
                        "status": invoice.status,
                        "amount_paid": str(invoice.amount_paid),
                        "amount_due": str(invoice.amount_due),
                        "is_paid": invoice.is_paid
                    },
                    "ghl_payment_recorded": ghl_result.get("success", False),
                    "tag_added": tag_result.get("success", False)
                })
            else:
                # Payment not yet completed
                return Response({
                    "status": session.payment_status,
                    "message": f"Payment status: {session.payment_status}",
                    "invoice": {
                        "status": invoice.status,
                        "amount_paid": str(invoice.amount_paid),
                        "amount_due": str(invoice.amount_due),
                        "is_paid": invoice.is_paid
                    }
                })
                
        except stripe.error.StripeError as e:
            print(f"Stripe error verifying payment: {e}")
            return Response(
                {"error": f"Failed to verify payment: {str(e)}"},
                status=500
            )
        except Exception as e:
            print(f"Error verifying payment: {e}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": f"Failed to verify payment: {str(e)}"},
                status=500
            )


class CreateStripeCheckoutSession(APIView):
    """
    Create a Stripe Checkout Session for invoice payment
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request, token):
        try:
            # Check if Stripe API key is configured
            stripe_secret_key = settings.STRIPE_SECRET_KEY
            if not stripe_secret_key:
                # Debug: Print environment variable status
                print(f"DEBUG: STRIPE_SECRET_KEY from env: {os.getenv('STRIPE_SECRET_KEY')}")
                print(f"DEBUG: STRIPE_SECRET_KEY from settings: {settings.STRIPE_SECRET_KEY}")
                return Response(
                    {"error": "Stripe API key is not configured. Please check your .env file and restart the server."},
                    status=500
                )
            
            # Get invoice
            invoice = Invoice.objects.get(token=token)
            
            # Check if already paid
            if invoice.is_paid:
                return Response(
                    {"error": "Invoice is already paid"},
                    status=400
                )
            
            # Check if signature is required
            if not invoice.signature:
                return Response(
                    {"error": "Please sign the invoice before proceeding with payment"},
                    status=400
                )
            
            # Check if amount due is valid
            if invoice.amount_due <= 0:
                return Response(
                    {"error": "No amount due for this invoice"},
                    status=400
                )
            
            # Initialize Stripe with API key
            stripe_secret_key = settings.STRIPE_SECRET_KEY
            if not stripe_secret_key:
                print("ERROR: STRIPE_SECRET_KEY is not set in environment variables")
                return Response(
                    {"error": "Payment service is not configured. Please contact support."},
                    status=500
                )
            
            stripe.api_key = stripe_secret_key
            
            # Get frontend URL for success/cancel redirects
            frontend_url = settings.FRONTEND_URL or "http://localhost:5173"
            frontend_url = frontend_url.rstrip('/')
            
            # Create Checkout Session
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': invoice.currency.lower(),
                        'product_data': {
                            'name': f"Invoice #{invoice.invoice_number or 'N/A'}",
                            'description': invoice.name,
                        },
                        'unit_amount': int(float(invoice.amount_due) * 100),  # Convert to cents
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=f'{frontend_url}/invoice/{token}/?payment=success',
                cancel_url=f'{frontend_url}/invoice/{token}/?payment=cancelled',
                customer_email=invoice.contact_email,
                metadata={
                    'invoice_token': str(invoice.token),
                    'invoice_id': str(invoice.id),
                    'invoice_number': invoice.invoice_number or '',
                },
            )
            
            # Save checkout session ID to invoice
            invoice.stripe_checkout_session_id = checkout_session.id
            invoice.save()
            
            return Response({
                'checkout_url': checkout_session.url,
                'session_id': checkout_session.id
            })
            
        except Invoice.DoesNotExist:
            return Response(
                {"error": "Invoice not found"},
                status=404
            )
        except stripe.error.StripeError as e:
            print(f"Stripe API error: {e}")
            return Response(
                {"error": f"Payment processing error: {str(e)}"},
                status=500
            )
        except Exception as e:
            print(f"Error creating Stripe checkout session: {e}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": f"Failed to create payment session: {str(e)}"},
                status=500
            )


@csrf_exempt
def stripe_webhook_handler(request):
    """
    Handle Stripe webhook events (without verification for now)
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        payload = request.body
        # Skip webhook verification for now - add later
        # sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        # event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        
        data = json.loads(payload)
        event_type = data.get('type')
        
        print(f"Received Stripe webhook: {event_type}")
        
        if event_type == 'checkout.session.completed':
            # Payment was successful
            session = data.get('data', {}).get('object', {})
            session_id = session.get('id')
            payment_status = session.get('payment_status')
            
            if payment_status == 'paid':
                # Find invoice by checkout session ID
                try:
                    invoice = Invoice.objects.get(stripe_checkout_session_id=session_id)
                    
                    # Get payment intent details
                    payment_intent_id = session.get('payment_intent')
                    if payment_intent_id:
                        invoice.stripe_payment_intent_id = payment_intent_id
                    
                    # Get amount paid from session
                    amount_total = session.get('amount_total', 0)  # Amount in cents
                    amount_paid = float(amount_total) / 100  # Convert to dollars
                    
                    # Check if invoice was already paid to avoid duplicate GHL calls
                    was_already_paid = invoice.is_paid
                    
                    # Update invoice status
                    invoice.status = 'paid'
                    invoice.amount_paid = amount_paid
                    invoice.amount_due = max(0, float(invoice.total) - amount_paid)
                    invoice.save()
                    
                    print(f"Invoice {invoice.invoice_number} marked as paid. Amount: ${amount_paid}")
                    
                    # Record payment in GHL (only if it wasn't already paid)
                    if not was_already_paid:
                        ghl_result = record_payment_in_ghl(invoice, amount_paid)
                        if ghl_result.get("success"):
                            print(f"Payment recorded in GHL for invoice {invoice.invoice_number}")
                        else:
                            print(f"Warning: Failed to record payment in GHL for invoice {invoice.invoice_number}: {ghl_result.get('error')}")
                        
                        # Add "invoice_paid" tag to GHL contact
                        tag_result = add_invoice_paid_tag_to_contact(invoice.contact_id, invoice.location_id)
                        if tag_result.get("success"):
                            print(f"Successfully added invoice_paid tag to contact {invoice.contact_id}")
                        else:
                            print(f"Warning: Failed to add invoice_paid tag to contact {invoice.contact_id}: {tag_result.get('error')}")
                    else:
                        print(f"Invoice {invoice.invoice_number} was already marked as paid, skipping GHL payment recording")
                    
                except Invoice.DoesNotExist:
                    print(f"Invoice not found for session: {session_id}")
                except Exception as e:
                    print(f"Error updating invoice: {e}")
                    import traceback
                    traceback.print_exc()
        
        elif event_type == 'payment_intent.payment_failed':
            # Payment failed
            payment_intent = data.get('data', {}).get('object', {})
            payment_intent_id = payment_intent.get('id')
            
            try:
                invoice = Invoice.objects.get(stripe_payment_intent_id=payment_intent_id)
                # You might want to add a 'failed' status or keep it as 'sent'
                # For now, we'll just log it
                print(f"Payment failed for invoice {invoice.invoice_number}")
            except Invoice.DoesNotExist:
                print(f"Invoice not found for payment intent: {payment_intent_id}")
        
        elif event_type == 'checkout.session.async_payment_failed':
            # Async payment failed
            session = data.get('data', {}).get('object', {})
            session_id = session.get('id')
            
            try:
                invoice = Invoice.objects.get(stripe_checkout_session_id=session_id)
                print(f"Async payment failed for invoice {invoice.invoice_number}")
            except Invoice.DoesNotExist:
                print(f"Invoice not found for session: {session_id}")
        
        return JsonResponse({"status": "success"})
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def invoice_paid_webhook_handler(request):
    """
    Webhook handler to mark invoice as paid when payment is received
    Receives ghl_invoice_id and marks the corresponding invoice as paid
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        ghl_invoice_id = data.get('ghl_invoice_id')
        
        if not ghl_invoice_id:
            return JsonResponse({
                "error": "ghl_invoice_id is required"
            }, status=400)
        
        # Fetch invoice by ghl_invoice_id
        try:
            invoice = Invoice.objects.get(ghl_invoice_id=ghl_invoice_id)
        except Invoice.DoesNotExist:
            return JsonResponse({
                "error": f"Invoice with ghl_invoice_id '{ghl_invoice_id}' not found"
            }, status=404)
        
        # Check if invoice is already paid
        if invoice.status == 'paid':
            return JsonResponse({
                "message": "Invoice is already marked as paid",
                "invoice_id": invoice.ghl_invoice_id,
                "invoice_number": invoice.invoice_number,
                "status": invoice.status
            }, status=200)
        
        # Mark invoice as paid
        invoice.status = 'paid'
        # Set amount_paid to total if not already set
        if invoice.amount_paid == 0:
            invoice.amount_paid = invoice.total
        invoice.amount_due = max(0, float(invoice.total) - float(invoice.amount_paid))
        invoice.save()
        
        print(f"Invoice {invoice.invoice_number} (ghl_invoice_id: {ghl_invoice_id}) marked as paid via webhook")
        
        # Add "invoice_paid" tag to GHL contact
        tag_result = add_invoice_paid_tag_to_contact(invoice.contact_id, invoice.location_id)
        if tag_result.get("success"):
            print(f"Successfully added invoice_paid tag to contact {invoice.contact_id}")
        else:
            print(f"Warning: Failed to add invoice_paid tag to contact {invoice.contact_id}: {tag_result.get('error')}")
        
        return JsonResponse({
            "message": "Invoice marked as paid successfully",
            "invoice_id": invoice.ghl_invoice_id,
            "invoice_number": invoice.invoice_number,
            "status": invoice.status,
            "amount_paid": str(invoice.amount_paid),
            "amount_due": str(invoice.amount_due),
            "tag_added": tag_result.get("success", False)
        }, status=200)
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        print(f"Error processing invoice paid webhook: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)