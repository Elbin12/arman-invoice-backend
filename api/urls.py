from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from .views import dataView, ServicesView, ContactsView

urlpatterns = [
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('data/', dataView.as_view()),
    path('services/', ServicesView.as_view()),
    path('contacts/', ContactsView.as_view())
]
