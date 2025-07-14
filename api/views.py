from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import ListAPIView
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db.models import Q


from .models import Service, Contact, Job, WebhookLog
from ghl_auth.models import GHLAuthCredentials, GHLUser
from .seriallizers import ServiceSerializer, ContactSerializer, GHLUserSerializer
from .utils import create_opportunity, create_invoice
from .tasks import handle_webhook_event

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
        event_type = data.get("type")
        handle_webhook_event.delay(data, event_type)
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
        credentials = GHLAuthCredentials.objects.first()
        if not credentials:
            return Response({"error": "No GHL credentials configured."}, status=500)

        # You need to fetch service info from DB or pass it in request
        services = request.data.get("services")  # Expects a list of dicts

        # Step 1: Create Invoice
        invoice_response = create_invoice(
            name=name,
            contact_id=contact_id,
            services=services,
            credentials=credentials
        )

        invoice_id = invoice_response.get("id")
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
            assigned_to=assigned_to
        )

        if ghl_response.get("id"):
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