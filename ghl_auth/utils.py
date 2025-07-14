from .models import GHLAuthCredentials, GHLUser

import requests


def pull_users(locationId):
    token = GHLAuthCredentials.objects.get(location_id=locationId)
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token.access_token}',
        'Content-Type': 'application/json',
        'Version': '2021-07-28'  # or '2021-04-15' for calendars endpoint
    }

    # Step 2: Fetch users and save/update GHLUser entries
    user_response = requests.get(
        f"https://services.leadconnectorhq.com/users/?locationId={locationId}",
        headers=headers
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
                "location_id": locationId,            }
        )