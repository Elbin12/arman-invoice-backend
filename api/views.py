from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Service
# Create your views here.


class dataView(APIView):
    def get(self, request):
        services = Service.objects.using('external').all()[:10]
        print(services)
        return Response(status=200)