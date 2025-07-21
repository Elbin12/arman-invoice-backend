from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from . import views
urlpatterns = [
    path("webhook/", views.webhook_handler),
    path("webhook/user-create/", views.user_create_webhook_handler),
    path("webhook/payroll/", views.payroll_webhook_handler),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view()),
    path('services/', views.ServicesView.as_view()),
    path('contacts/', views.ContactsView.as_view()),
    path('users/', views.GHLUserSearchView.as_view()),
    path('create/job/', views.CreateJob.as_view()),
    path('create/job/validations/', views.CreateJobValidations.as_view()),
    path('payroll/', views.PayrollView.as_view()),
    path("payroll/<str:user_id>/", views.PayrollView.as_view(), name="percentage-update"),
    path("payroll/commission/<str:user_id>/", views.CommissionRuleUpdateView.as_view()),
    path('commissions/<str:user_id>/<int:commission_id>/', views.CommissionRuleUpdateView.as_view()),
]
