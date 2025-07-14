from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from .views import ServicesView, ContactsView, GHLUserSearchView ,webhook_handler

urlpatterns = [
    path("webhook",webhook_handler),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('services/', ServicesView.as_view()),
    path('contacts/', ContactsView.as_view()),
    path('contacts/', GHLUserSearchView.as_view())
]
