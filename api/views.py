from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.generics import ListAPIView
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db.models import Q


from .models import Service, Contact, Job, WebhookLog
from ghl_auth.models import GHLAuthCredentials, GHLUser, CommissionRule
from .seriallizers import ServiceSerializer, ContactSerializer, GHLUserSerializer, PayrollSerializer, GHLUserPercentageEditSerializer, CommissionRuleEditSerializer
from .utils import create_opportunity, create_invoice, add_followers
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
        handle_webhook_event.delay(data)
        return JsonResponse({"message":"Webhook received"}, status=200)
    except Exception as e:
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
        if serializer.is_valid():
            for item in serializer.validated_data:
                num_employees = item["num_other_employees"]
                percentage = item["commission_percentage"]

                rule, created = CommissionRule.objects.update_or_create(
                    ghl_user=user,
                    num_other_employees=num_employees,
                    defaults={"commission_percentage": percentage}
                )
            return Response({"message": "Commission rules updated", "data":serializer.data}, status=200)
        return Response(serializer.errors, status=400)
