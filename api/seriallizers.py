from rest_framework.serializers import ModelSerializer

from .models import Service, Contact



class ServiceSerializer(ModelSerializer):
    class Meta:
        model = Service
        fields = '__all__'

class ContactSerializer(ModelSerializer):
    class Meta:
        model = Contact
        fields = '__all__'