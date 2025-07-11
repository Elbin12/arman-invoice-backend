from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication


from .models import Service
from .seriallizers import ServiceSerializer
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