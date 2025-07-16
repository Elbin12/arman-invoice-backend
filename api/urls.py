from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from .views import ServicesView, ContactsView, GHLUserSearchView, CreateJob, PayrollView, UserPercentageDetailUpdateView, UserPercentageListView, webhook_handler

urlpatterns = [
    path("webhook/",webhook_handler),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('services/', ServicesView.as_view()),
    path('contacts/', ContactsView.as_view()),
    path('users/', GHLUserSearchView.as_view()),
    path('create/job/', CreateJob.as_view()),
    path('payroll/', PayrollView.as_view()),
    path("percentages/", UserPercentageListView.as_view(), name="percentage-list"),
    path("percentages/<str:user_id>/", UserPercentageDetailUpdateView.as_view(), name="percentage-detail"),
]
