from django.shortcuts import render
import requests
from django.http import JsonResponse
from django.shortcuts import redirect, render
from urllib.parse import urlencode
from django.conf import settings

from .models import GHLAuthCredentials
from ghl_auth.utils import pull_users
from ghl_auth.models import GHLUser

# Create your views here.

GHL_CLIENT_ID = settings.GHL_CLIENT_ID
GHL_CLIENT_SECRET = settings.GHL_CLIENT_SECRET
GHL_REDIRECTED_URI = settings.GHL_REDIRECTED_URI
FRONTEND_URL = settings.FRONTEND_URL
TOKEN_URL = "https://services.leadconnectorhq.com/oauth/token"
SCOPE = settings.SCOPE
BASE_URI = settings.BASE_URI


def auth_connect(request):
    auth_url = ("https://marketplace.gohighlevel.com/oauth/chooselocation?response_type=code&"
                f"redirect_uri={GHL_REDIRECTED_URI}&"
                f"client_id={GHL_CLIENT_ID}&"
                f"scope={SCOPE}"
                )
    return redirect(auth_url)



def callback(request):
    
    code = request.GET.get('code')

    if not code:
        return JsonResponse({"error": "Authorization code not received from OAuth"}, status=400)

    return redirect(f'{BASE_URI}/auth/tokens?code={code}')


def tokens(request):
    authorization_code = request.GET.get("code")

    if not authorization_code:
        return JsonResponse({"error": "Authorization code not found"}, status=400)

    data = {
        "grant_type": "authorization_code",
        "client_id": GHL_CLIENT_ID,
        "client_secret": GHL_CLIENT_SECRET,
        "redirect_uri": GHL_REDIRECTED_URI,
        "code": authorization_code,
    }

    response = requests.post(TOKEN_URL, data=data)

    try:
        response_data = response.json()
        if not response_data:
            return
        print("response.data: ", response_data)
        if not response_data.get('access_token'):
            return render(request, 'onboard.html', context={
                "message": "Invalid JSON response from API",
                "status_code": response.status_code,
                "response_text": response.text[:400]
            }, status=400)        

        obj, created = GHLAuthCredentials.objects.update_or_create(
            location_id= response_data.get("locationId"),
            defaults={
                "access_token": response_data.get("access_token"),
                "refresh_token": response_data.get("refresh_token"),
                "expires_in": response_data.get("expires_in"),
                "scope": response_data.get("scope"),
                "user_type": response_data.get("userType"),
                "company_id": response_data.get("companyId"),
                "user_id":response_data.get("userId"),
            }
        )

        pull_users(locationId=response_data.get("locationId"))
        
        return JsonResponse({'message':'Onboarding successfull'})
        
    except requests.exceptions.JSONDecodeError:
        frontend_url = "http://localhost:3000/admin/error-onboard"
        return redirect(frontend_url)