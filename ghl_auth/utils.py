from .models import GHLAuthCredentials, GHLUser
from ghl_auth.token_service import ghl_request


def pull_users(locationId):
    credentials = GHLAuthCredentials.objects.get(location_id=locationId)

    # Step 2: Fetch users and save/update GHLUser entries
    user_response = ghl_request(
        "GET",
        f"https://services.leadconnectorhq.com/users/?locationId={locationId}",
        credentials=credentials,
    )

    if user_response.status_code != 200:
        print(f"Error fetching users: {user_response.status_code} - {user_response.text}")
        return

    users_data = user_response.json().get("users", [])

    for user in users_data:
        user_id = user["id"]
        GHLUser.objects.update_or_create(
            user_id=user_id,
            defaults={
                "first_name": user.get("firstName", ""),
                "last_name": user.get("lastName", ""),
                "name": user.get("name", ""),
                "email": user.get("email", ""),
                "phone": user.get("phone", ""),
                "location_id": locationId,
            },
        )