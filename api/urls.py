from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from . import views
urlpatterns = [
    path("webhook/", views.webhook_handler),
    path("webhook/user-create/", views.user_create_webhook_handler),
    path("webhook/payroll/", views.payroll_webhook_handler),
    path("webhook/invoice-paid/", views.invoice_paid_webhook_handler, name='invoice-paid-webhook'),
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
    path('invoice/<uuid:token>/', views.PublicInvoiceView.as_view(), name='public-invoice-view'),
    path('invoice/<uuid:token>/signature/', views.SaveInvoiceSignature.as_view(), name='save-invoice-signature'),
    path('invoice/<uuid:token>/verify-payment/', views.VerifyPaymentStatus.as_view(), name='verify-payment-status'),
    path('invoice/<uuid:token>/create-checkout-session/', views.CreateStripeCheckoutSession.as_view(), name='create-stripe-checkout'),
    path('stripe/webhook/', views.stripe_webhook_handler, name='stripe-webhook'),
]
