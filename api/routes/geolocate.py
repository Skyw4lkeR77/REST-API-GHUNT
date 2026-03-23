import json
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from geopy.geocoders import Nominatim
from pydantic import BaseModel

from api.helpers.auth import verify_api_key
from ghunt.helpers.utils import get_httpx_client
from ghunt.helpers import auth as ghunt_auth
from ghunt.apis.geolocation import GeolocationHttp
from ghunt.errors import GHuntInvalidSession

router = APIRouter(prefix="/geolocate", tags=["Geolocate"])


class GeolocateRequest(BaseModel):
    bssid: Optional[str] = None
    body: Optional[Dict[str, Any]] = None


class GeolocateResponse(BaseModel):
    found: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@router.post(
    "",
    response_model=GeolocateResponse,
    summary="Geolocate a BSSID (WiFi MAC address)",
    description=(
        "Geolocate a WiFi access point by its BSSID (MAC address) using Google's Geolocation API.\n\n"
        "Provide **one** of:\n"
        "- `bssid`: A single BSSID. Example: `30:86:2d:c4:29:d0`\n"
        "- `body`: A raw JSON body for multi-BSSID geolocation "
        "([see format](https://developers.google.com/maps/documentation/geolocation/requests-geolocation#sample-requests))\n\n"
        "Returns:\n"
        "- Latitude, longitude, accuracy\n"
        "- Estimated address (via reverse geocoding)\n"
        "- Google Maps link\n\n"
        "Requires a valid GHunt session."
    ),
)
async def geolocate(request: GeolocateRequest, api_key: str = Depends(verify_api_key)):
    if not request.bssid and not request.body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either 'bssid' or 'body'.",
        )

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
        geo_api = GeolocationHttp(ghunt_creds)
        found, resp = await geo_api.geolocate(
            as_client,
            bssid=request.bssid,
            body=request.body,
        )
        if not found:
            await as_client.aclose()
            return GeolocateResponse(found=False, message="Location not found for given BSSID.")

        lat = resp.location.latitude
        lon = resp.location.longitude
        accuracy = resp.accuracy

        # Reverse geocoding
        geolocator = Nominatim(user_agent="ghunt-api")
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        raw_address = location.raw.get("address", {}) if location else {}
        pretty_address = location.address if location else None

        await as_client.aclose()
        return GeolocateResponse(
            found=True,
            message="Location found.",
            data={
                "latitude": lat,
                "longitude": lon,
                "accuracy_meters": accuracy,
                "address": raw_address,
                "pretty_address": pretty_address,
                "google_maps_url": f"https://www.google.com/maps/search/?q={lat},{lon}",
            },
        )

    except Exception as e:
        await as_client.aclose()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during geolocation: {str(e)}",
        )
