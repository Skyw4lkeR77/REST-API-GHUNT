from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.helpers.auth import verify_api_key
from api.helpers.serializer import serialize
from ghunt.helpers.utils import get_httpx_client
from ghunt.helpers import auth as ghunt_auth, gmaps
from ghunt.helpers.knowledge import get_user_type_definition
from ghunt.apis.peoplepa import PeoplePaHttp
from ghunt.errors import GHuntInvalidSession

router = APIRouter(prefix="/gaia", tags=["Gaia"])


class GaiaRequest(BaseModel):
    gaia_id: str


class GaiaResponse(BaseModel):
    found: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@router.post(
    "",
    response_model=GaiaResponse,
    summary="Hunt a Gaia ID",
    description=(
        "Retrieve OSINT information for a Google account by Gaia ID.\n\n"
        "Returns data from:\n"
        "- **Google Account** (name, profile photo, cover photo, profile URL, user types)\n"
        "- **Google Chat** (entity type, customer ID)\n"
        "- **Google Plus** (enterprise user status, activated services)\n"
        "- **Google Maps** (stats + direct profile URL)\n\n"
        "Requires a valid GHunt session."
    ),
)
async def hunt_gaia(request: GaiaRequest, api_key: str = Depends(verify_api_key)):
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
        is_found, target = await people_pa.people(
            as_client, request.gaia_id, params_template="max_details"
        )
        if not is_found:
            await as_client.aclose()
            return GaiaResponse(found=False, message="Target Gaia ID was not found.")

        containers = target.sourceIds
        if "PROFILE" not in containers:
            await as_client.aclose()
            return GaiaResponse(
                found=False,
                message="Gaia ID does not match a public Google Account.",
            )

        container = "PROFILE"

        # --- Profile ---
        profile_data: Dict[str, Any] = {
            "gaia_id": target.personId,
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

        # --- Maps ---
        maps_data: Dict[str, Any] = {
            "profile_url": f"https://www.google.com/maps/contrib/{request.gaia_id}/reviews",
            "photos_url": f"https://www.google.com/maps/contrib/{request.gaia_id}/photos",
            "stats": None,
            "error": None,
        }
        err, stats = await gmaps.get_reviews(as_client, request.gaia_id)
        if err == "failed":
            maps_data["error"] = "IP blocked by Google. Try again later."
        elif err == "empty" or not stats:
            maps_data["error"] = "No reviews, ratings or photos found."
        else:
            maps_data["stats"] = stats

        await as_client.aclose()
        return GaiaResponse(
            found=True,
            message="Target found.",
            data={
                "google_account": profile_data,
                "google_chat": chat_data,
                "google_plus": gplus_data,
                "maps": maps_data,
            },
        )

    except Exception as e:
        await as_client.aclose()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during Gaia hunt: {str(e)}",
        )
