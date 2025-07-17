from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from .views import ServicesView, ContactsView, GHLUserSearchView, CreateJob, PayrollView, webhook_handler, user_create_webhook_handler, payroll_webhook_handler

urlpatterns = [
    path("webhook/", webhook_handler),
    path("webhook/user-create/", user_create_webhook_handler),
    path("webhook/payroll/", payroll_webhook_handler),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view()),
    path('services/', ServicesView.as_view()),
    path('contacts/', ContactsView.as_view()),
    path('users/', GHLUserSearchView.as_view()),
    path('create/job/', CreateJob.as_view()),
    path('payroll/', PayrollView.as_view()),
    path("payroll/<str:user_id>/", PayrollView.as_view(), name="percentage-update"),
]
