from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from api.helpers.auth import verify_api_key
from api.helpers.serializer import serialize
from ghunt.helpers.utils import get_httpx_client
from ghunt.helpers import auth as ghunt_auth, gmaps, playgames, calendar as gcalendar
from ghunt.helpers.knowledge import get_user_type_definition
from ghunt.apis.peoplepa import PeoplePaHttp
from ghunt.errors import GHuntInvalidSession

router = APIRouter(prefix="/email", tags=["Email"])


class EmailRequest(BaseModel):
    email: str


class EmailResponse(BaseModel):
    found: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@router.post(
    "",
    response_model=EmailResponse,
    summary="Hunt an email address",
    description=(
        "Retrieve OSINT information for a Google account by email address.\n\n"
        "Returns data from:\n"
        "- **Google Account** (profile photo, cover photo, Gaia ID, user types)\n"
        "- **Google Chat** (entity type, customer ID)\n"
        "- **Google Plus** (enterprise user status, activated services)\n"
        "- **Play Games** (username, player ID, avatar, game stats)\n"
        "- **Google Maps** (review/photo statistics)\n"
        "- **Google Calendar** (public calendar events)\n\n"
        "Requires a valid GHunt session."
    ),
)
async def hunt_email(request: EmailRequest, api_key: str = Depends(verify_api_key)):
    as_client = get_httpx_client()
    try:
        ghunt_creds = await ghunt_auth.load_and_auth(as_client)
    except GHuntInvalidSession as e:
        await as_client.aclose()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"GHunt session invalid: {str(e)}. Run ghunt login or POST /api/v1/session/setup",
        )

    try:
        people_pa = PeoplePaHttp(ghunt_creds)
        is_found, target = await people_pa.people_lookup(
            as_client, request.email, params_template="max_details"
        )
        if not is_found:
            await as_client.aclose()
            return EmailResponse(found=False, message="Target email not found on Google.")

        containers = target.sourceIds
        if "PROFILE" not in containers:
            await as_client.aclose()
            return EmailResponse(
                found=False,
                message="Email does not match a public Google Account.",
            )

        container = "PROFILE"

        # --- Profile ---
        profile_data: Dict[str, Any] = {
            "gaia_id": target.personId,
            "email": request.email,
            "profile_photo": None,
            "cover_photo": None,
            "last_profile_edit": None,
            "user_types": [],
            "containers": list(containers.keys()),
        }

        if container in target.profilePhotos:
            photo = target.profilePhotos[container]
            profile_data["profile_photo"] = {
                "is_default": photo.isDefault,
                "url": photo.url if not photo.isDefault else None,
            }

        if container in target.coverPhotos:
            cover = target.coverPhotos[container]
            profile_data["cover_photo"] = {
                "is_default": cover.isDefault,
                "url": cover.url if not cover.isDefault else None,
            }

        if target.sourceIds[container].lastUpdated:
            profile_data["last_profile_edit"] = target.sourceIds[container].lastUpdated.strftime(
                "%Y/%m/%d %H:%M:%S (UTC)"
            )

        if container in target.profileInfos:
            for user_type in target.profileInfos[container].userTypes:
                profile_data["user_types"].append({
                    "type": user_type,
                    "definition": get_user_type_definition(user_type),
                })

        # --- Google Chat ---
        chat_data = {
            "entity_type": target.extendedData.dynamiteData.entityType,
            "customer_id": target.extendedData.dynamiteData.customerId or None,
        }

        # --- Google Plus ---
        gplus_data = {
            "is_enterprise_user": target.extendedData.gplusData.isEntrepriseUser,
            "activated_services": [],
        }
        if container in target.inAppReachability:
            gplus_data["activated_services"] = list(
                target.inAppReachability[container].apps
            )

        # --- Play Games ---
        games_data = None
        player_results = await playgames.search_player(
            ghunt_creds, as_client, request.email
        )
        if player_results:
            candidate = player_results[0]
            _, player = await playgames.get_player(ghunt_creds, as_client, candidate.id)
            games_data = serialize(player)
            games_data["username"] = candidate.name
            games_data["player_id"] = candidate.id
            games_data["avatar_url"] = candidate.avatar_url

        # --- Maps ---
        maps_data = None
        err, stats = await gmaps.get_reviews(as_client, target.personId)
        if not err and stats:
            maps_data = serialize(stats)

        # --- Calendar ---
        calendar_data = None
        cal_found, calendar, calendar_events = await gcalendar.fetch_all(
            ghunt_creds, as_client, request.email
        )
        if cal_found:
            calendar_data = {
                "details": serialize(calendar),
                "events": serialize(calendar_events),
            }

        await as_client.aclose()
        return EmailResponse(
            found=True,
            message="Target found.",
            data={
                "google_account": profile_data,
                "google_chat": chat_data,
                "google_plus": gplus_data,
                "play_games": games_data,
                "maps": maps_data,
                "calendar": calendar_data,
            },
        )

    except Exception as e:
        await as_client.aclose()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during email hunt: {str(e)}",
        )
