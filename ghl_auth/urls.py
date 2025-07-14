from django.urls import path
from .views import *

urlpatterns = [
    path("connect/", auth_connect, name="oauth_connect"),
    path("tokens/", tokens, name="oauth_tokens"),
    path("callback/", callback, name="oauth_callback"),
]