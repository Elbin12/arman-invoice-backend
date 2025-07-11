from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication


from .models import Service, Contact
from .seriallizers import ServiceSerializer, ContactSerializer
# Create your views here.


class dataView(APIView):
    def get(self, request):
        services = Service.objects.using('external').all()[:10]
        print(services)
        return Response(status=200)
    
class ServicesView(APIView):
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        name = request.data.get('name')
        try:
            queryset = Service.objects.using('external').all()
            print(queryset)
            if name:
                queryset = queryset.filter(name=name)
            serializer = ServiceSerializer(queryset, many=True)
            return Response(serializer.data, status=200)
        except Exception as e:
            print(e,)
            return Response({'error':'Something went wrong.'},status=500)
        
class ContactsView(APIView):
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        first_name = request.query_params.get('first_name')
        email = request.query_params.get('email')
        phone = request.query_params.get('phone')

        try:
            queryset = Contact.objects.using('external').all()

            if first_name:
                queryset = queryset.filter(first_name__icontains=first_name)
            if email:
                queryset = queryset.filter(email__icontains=email)
            if phone:
                queryset = queryset.filter(phone__icontains=phone)

            serializer = ContactSerializer(queryset, many=True)
            return Response(serializer.data, status=200)
        except Exception as e:
            print(e,)
            return Response({'error':'Something went wrong.'},status=500)