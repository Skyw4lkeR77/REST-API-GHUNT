import asyncio
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.helpers.auth import verify_api_key
from api.helpers.serializer import serialize
from ghunt.helpers.utils import get_httpx_client
from ghunt.objects.base import GHuntCreds
from ghunt.apis.digitalassetslinks import DigitalAssetsLinksHttp
from ghunt.helpers.playstore import app_exists
from ghunt.modules.spiderdal import Asset, analyze_single, identify_public_pkgs

router = APIRouter(prefix="/spiderdal", tags=["SpiderDAL"])


class SpiderDALRequest(BaseModel):
    url: Optional[str] = None
    package: Optional[str] = None
    fingerprint: Optional[str] = None
    strict: bool = False


class SpiderDALResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@router.post(
    "",
    response_model=SpiderDALResponse,
    summary="Spider Digital Assets Links",
    description=(
        "Find linked web sites and Android apps using Google's Digital Asset Links API.\n\n"
        "Provide at least one of:\n"
        "- `url`: A web URL or domain. Example: `https://cash.app`\n"
        "- `package` + `fingerprint`: Android package name + SHA256 fingerprint. "
          "Example: `com.squareup.cash` + `21:A7:46:...`\n\n"
        "Optional:\n"
        "- `strict`: If `true`, don't try www subdomain or http variant (default: `false`)\n\n"
        "Returns:\n"
        "- **Sites**: linked web domains with their origin\n"
        "- **Packages**: linked Android packages, whether public (Play Store) or private, with fingerprints"
    ),
)
async def spider_dal(request: SpiderDALRequest, api_key: str = Depends(verify_api_key)):
    if not request.url and not (request.package and request.fingerprint):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide 'url', or both 'package' and 'fingerprint'.",
        )
    if bool(request.package) != bool(request.fingerprint):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must provide both 'package' and 'fingerprint' together.",
        )

    # SpiderDAL doesn't need GHunt auth for the DAL API
    ghunt_creds = GHuntCreds()
    ghunt_creds.load_creds()

    as_client = get_httpx_client()
    digitalassetslink = DigitalAssetsLinksHttp(ghunt_creds)

    sites: dict = {}
    pkgs: dict = {}
    visited = set()
    limiter = asyncio.Semaphore(10)
    current_targets: List[Asset] = []

    try:
        # Build initial targets from url
        if request.url:
            url = request.url
            http = url.startswith("http")
            domain = url.split("//")[1] if url.startswith(("http://", "https://")) else url

            temp_targets = [f"https://{domain}"]
            if http:
                temp_targets.append(f"http://{domain}")
            if not request.strict:
                temp_targets.append(f"https://www.{domain}")
                if http:
                    temp_targets.append(f"http://www.{domain}")

            for target in temp_targets:
                current_targets.append(Asset(site=target, package_name=None, certificate=None))

        if request.package and request.fingerprint:
            current_targets.append(
                Asset(site=None, package_name=request.package, certificate=request.fingerprint)
            )

        # Spider loop
        while current_targets:
            await asyncio.gather(
                *[
                    analyze_single(as_client, digitalassetslink, target, sites, pkgs, visited, limiter)
                    for target in current_targets
                ]
            )
            next_sites = [site["asset"] for name, site in sites.items() if name not in visited]
            next_pkgs = [pkg["asset"] for name, pkg in pkgs.items() if name not in visited]
            current_targets = next_sites + next_pkgs

        # Identify which packages are in Play Store
        pkgs_names = {x: None for x in set([x["asset"].package_name for x in pkgs.values()])}
        await asyncio.gather(
            *[
                identify_public_pkgs(as_client, pkg_name, pkgs_names, limiter)
                for pkg_name in pkgs_names
            ]
        )

        await as_client.aclose()

        # Build response
        sites_out: List[Dict[str, Any]] = []
        for site_url, site in sites.items():
            origin = None
            if site["first_origin"]:
                origin = (
                    site["first_origin"].site
                    if site["first_origin"].site
                    else site["first_origin"].package_name
                )
            sites_out.append({"url": site_url, "leaked_by": origin})

        packages_out: List[Dict[str, Any]] = []
        for pkg_name, state in pkgs_names.items():
            fingerprints = []
            for pkg in pkgs.values():
                if pkg["asset"].package_name == pkg_name:
                    fp = pkg["asset"].certificate
                    if fp not in fingerprints:
                        origin = (
                            pkg["first_origin"].site
                            if pkg["first_origin"].site
                            else pkg["first_origin"].package_name
                        )
                        fingerprints.append({"fingerprint": fp, "leaked_by": origin})
            packages_out.append({
                "package_name": pkg_name,
                "is_public": state == "public",
                "fingerprints": fingerprints,
            })

        return SpiderDALResponse(
            success=True,
            message=f"Scan complete. {len(sites_out)} site(s), {len(packages_out)} package(s) found.",
            data={
                "sites": sites_out,
                "packages": packages_out,
            },
        )

    except Exception as e:
        await as_client.aclose()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during SpiderDAL: {str(e)}",
        )
