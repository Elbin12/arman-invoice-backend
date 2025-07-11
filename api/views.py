from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import ListAPIView


from .models import Service, Contact
from .seriallizers import ServiceSerializer, ContactSerializer
# Create your views here.


class dataView(APIView):
    def get(self, request):
        services = Service.objects.using('external').all()[:10]
        print(services)
        return Response(status=200)
    
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
        first_name = self.request.query_params.get('first_name')
        email = self.request.query_params.get('email')
        phone = self.request.query_params.get('phone')

        queryset = Contact.objects.using('external').all()

        if first_name:
            queryset = queryset.filter(first_name__icontains=first_name)
        if email:
            queryset = queryset.filter(email__icontains=email)
        if phone:
            queryset = queryset.filter(phone__icontains=phone)

        return queryset