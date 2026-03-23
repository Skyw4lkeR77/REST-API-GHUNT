import inspect
from typing import Any, Dict, List, Optional

import httpx
import humanize
import inflection
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.helpers.auth import verify_api_key
from api.helpers.serializer import serialize
from ghunt.helpers.utils import get_httpx_client
from ghunt.helpers import auth as ghunt_auth
from ghunt.helpers.drive import get_comments_from_file, get_users_from_file
from ghunt.apis.drive import DriveHttp
from ghunt.apis.clientauthconfig import ClientAuthConfigHttp
from ghunt.knowledge import drive as drive_knowledge
from ghunt.errors import GHuntInvalidSession

router = APIRouter(prefix="/drive", tags=["Drive"])


class DriveRequest(BaseModel):
    file_id: str


class DriveResponse(BaseModel):
    found: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@router.post(
    "",
    response_model=DriveResponse,
    summary="Hunt a Drive file or folder",
    description=(
        "Retrieve OSINT information for a Google Drive file or folder by its ID.\n\n"
        "The file ID can be found in the Drive URL:\n"
        "`https://drive.google.com/file/d/**FILE_ID**/view`\n\n"
        "Returns:\n"
        "- **Properties** (title, type, size, dates, checksum)\n"
        "- **Source application** (app name, home page)\n"
        "- **Image/Video metadata** (dimensions, rotation, duration)\n"
        "- **Parents** (parent folder IDs)\n"
        "- **Folder items** (item count if folder)\n"
        "- **Users** (owner, writers, readers, commenters)\n"
        "- **Comments** (top authors and comment counts)\n"
        "- **Capabilities** (your access permissions)\n\n"
        "Requires a valid GHunt session."
    ),
)
async def hunt_drive(request: DriveRequest, api_key: str = Depends(verify_api_key)):
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
        drive = DriveHttp(ghunt_creds)
        file_found, file = await drive.get_file(as_client, request.file_id)
        if not file_found:
            await as_client.aclose()
            return DriveResponse(found=False, message="Drive file/folder not found.")

        is_folder = file.mime_type == "application/vnd.google-apps.folder"
        file_type = drive_knowledge.mime_types.get(file.mime_type)

        # --- Properties ---
        properties: Dict[str, Any] = {
            "title": file.title,
            "id": file.id,
            "type": "folder" if is_folder else "file",
            "mime_type": file.mime_type,
            "friendly_type": file_type,
            "md5_checksum": file.md5_checksum or None,
            "file_size": humanize.naturalsize(file.file_size) if file.file_size else None,
            "link": file.alternate_link,
            "created_date": file.created_date.strftime("%Y/%m/%d %H:%M:%S (UTC)") if file.created_date else None,
            "modified_date": file.modified_date.strftime("%Y/%m/%d %H:%M:%S (UTC)") if file.modified_date else None,
            "sharing_with_link": None,
        }
        for perm in file.permissions:
            if perm.id == "anyoneWithLink":
                giving_roles = [perm.role.upper()] + [
                    x.upper() for x in perm.additional_roles if x != perm.role
                ]
                properties["sharing_with_link"] = giving_roles

        # --- Source app ---
        source_app: Optional[Dict[str, Any]] = None
        if file.source_app_id:
            source_app = {"app_id": file.source_app_id, "name": None, "home_page": None}
            cac = ClientAuthConfigHttp(ghunt_creds)
            brand_found, brand = await cac.get_brand(as_client, file.source_app_id)
            if brand_found:
                source_app["name"] = brand.display_name
                source_app["home_page"] = brand.home_page_url or None

        # --- Image metadata ---
        image_meta: Optional[Dict[str, Any]] = None
        if file.image_media_metadata.height and file.image_media_metadata.width:
            image_meta = {
                "height": file.image_media_metadata.height,
                "width": file.image_media_metadata.width,
                "rotation": file.image_media_metadata.rotation if isinstance(file.image_media_metadata.rotation, int) else None,
            }

        # --- Video metadata ---
        video_meta: Optional[Dict[str, Any]] = None
        if file.video_media_metadata.height and file.video_media_metadata.width:
            from datetime import timedelta
            video_meta = {
                "height": file.video_media_metadata.height,
                "width": file.video_media_metadata.width,
            }
            if file.video_media_metadata.duration_millis:
                duration = timedelta(milliseconds=int(file.video_media_metadata.duration_millis))
                video_meta["duration"] = humanize.precisedelta(duration)
                video_meta["duration_ms"] = int(file.video_media_metadata.duration_millis)

        # --- Parents ---
        parents: List[Dict[str, Any]] = []
        for parent in file.parents:
            parents.append({"id": parent.id, "is_root": parent.is_root})

        # --- Folder items count ---
        items_count: Optional[int] = None
        if is_folder:
            found, _, drive_childs = await drive.get_childs(as_client, request.file_id)
            if found and drive_childs.items:
                items_count = len(drive_childs.items)

        # --- Users ---
        users = get_users_from_file(file)
        users_data: Dict[str, List] = {
            "owners": [],
            "writers": [],
            "commenters": [],
            "readers": [],
            "others": [],
        }
        for user in users:
            user_dict = {
                "name": user.name or None,
                "email": user.email_address,
                "gaia_id": user.gaia_id or None,
                "is_last_modifier": user.is_last_modifying_user,
            }
            role_key = {
                "owner": "owners",
                "writer": "writers",
                "commenter": "commenters",
                "reader": "readers",
            }.get(user.role, "others")
            users_data[role_key].append(user_dict)

        # --- Comments ---
        comments_data: List[Dict[str, Any]] = []
        comments_found, _, drive_comments = await drive.get_comments(as_client, request.file_id)
        if comments_found and drive_comments.items:
            authors = get_comments_from_file(drive_comments)
            for _, author in authors[:20]:
                comments_data.append({
                    "name": author["name"],
                    "count": author["count"],
                })

        # --- Capabilities ---
        raw_caps = sorted([k for k, v in inspect.getmembers(file.capabilities) if v and not k.startswith("_")])
        default_caps = drive_knowledge.default_folder_capabilities if is_folder else drive_knowledge.default_file_capabilities
        capabilities_data = {
            "has_special_permissions": raw_caps != default_caps,
            "capabilities": [inflection.humanize(c) for c in raw_caps],
        }

        await as_client.aclose()
        return DriveResponse(
            found=True,
            message="File/folder found.",
            data={
                "properties": properties,
                "source_app": source_app,
                "image_metadata": image_meta,
                "video_metadata": video_meta,
                "parents": parents,
                "items_count": items_count,
                "users": users_data,
                "comments": comments_data,
                "capabilities": capabilities_data,
            },
        )

    except Exception as e:
        await as_client.aclose()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during Drive hunt: {str(e)}",
        )
