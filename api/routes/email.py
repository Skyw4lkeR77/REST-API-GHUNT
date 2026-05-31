from collections import Counter
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

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
        "- **Google Account** (name, profile photo, cover photo, Gaia ID, profile URL, user types)\n"
        "- **Google Chat** (entity type, customer ID)\n"
        "- **Google Plus** (enterprise user status, activated services)\n"
        "- **Play Games** (username, avatar, games list, achievements)\n"
        "- **Google Maps** (stats + direct profile URL)\n"
        "- **Google Calendar** (public calendar + events)\n\n"
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
            "name": None,
            "profile_url": f"https://plus.google.com/{target.personId}",
            "profile_photo": None,
            "cover_photo": None,
            "last_profile_edit": None,
            "user_types": [],
            "containers": list(containers.keys()),
        }

        # Full name
        if container in target.names:
            profile_data["name"] = target.names[container].fullname

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
            profile_visible = bool(
                player.profile and player.profile.profile_settings.profile_visible
            )
            games_data = {
                "username": candidate.name,
                "player_id": candidate.id,
                "avatar_url": candidate.avatar_url,
                "profile_visible": profile_visible,
                "played_games_count": len(player.played_games) if player.played_games else 0,
                "achievements_count": len(player.achievements) if player.achievements else 0,
                "last_played_game": None,
                "top_achievement_game": None,
                "played_games": [],
                "achievements": [],
            }
            if profile_visible and player.played_games:
                if player.profile.last_played_app:
                    games_data["last_played_game"] = {
                        "name": player.profile.last_played_app.app_name,
                        "timestamp": str(player.profile.last_played_app.timestamp_millis),
                    }
                games_data["played_games"] = [
                    {"id": g.game_data.id, "name": g.game_data.name}
                    for g in player.played_games[:10]
                ]
                if player.achievements:
                    games_data["achievements"] = [
                        {
                            "id": a.id,
                            "name": a.definition.name if a.definition else None,
                            "description": a.definition.description if a.definition else None,
                            "app_id": a.app_id,
                            "unlocked": a.achievement_state == "UNLOCKED",
                            "achievement_state": a.achievement_state,
                            "xp": a.xp,
                        }
                        for a in player.achievements[:10]
                    ]
                    app_count = Counter(a.app_id for a in player.achievements)
                    top_app_id = app_count.most_common(1)[0][0]
                    top_game = next(
                        (g for g in player.played_games if g.game_data.id == top_app_id), None
                    )
                    if top_game:
                        games_data["top_achievement_game"] = {
                            "name": top_game.game_data.name,
                            "achievement_count": app_count[top_app_id],
                        }

        # --- Maps ---
        maps_data: Dict[str, Any] = {
            "profile_url": f"https://www.google.com/maps/contrib/{target.personId}/reviews",
            "photos_url": f"https://www.google.com/maps/contrib/{target.personId}/photos",
            "stats": None,
            "error": None,
        }
        err, stats = await gmaps.get_reviews(as_client, target.personId)
        if err == "failed":
            maps_data["error"] = "IP blocked by Google. Try again later."
        elif err == "empty" or not stats:
            maps_data["error"] = "No reviews, ratings or photos found."
        else:
            maps_data["stats"] = stats

        # --- Calendar ---
        calendar_data: Dict[str, Any] = {"found": False, "events": []}
        cal_found, calendar, calendar_events = await gcalendar.fetch_all(
            ghunt_creds, as_client, request.email
        )
        if cal_found:
            calendar_data = {
                "found": True,
                "summary": getattr(calendar, "summary", None),
                "description": getattr(calendar, "description", None),
                "timezone": getattr(calendar, "timeZone", None),
                "events": [],
            }
            if calendar_events.items:
                for event in calendar_events.items[:20]:
                    calendar_data["events"].append({
                        "id": getattr(event, "id", None),
                        "summary": getattr(event, "summary", None),
                        "description": getattr(event, "description", None),
                        "location": getattr(event, "location", None),
                        "start": str(getattr(event, "start", None)),
                        "end": str(getattr(event, "end", None)),
                        "status": getattr(event, "status", None),
                        "creator": serialize(getattr(event, "creator", None)),
                        "organizer": serialize(getattr(event, "organizer", None)),
                    })

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
