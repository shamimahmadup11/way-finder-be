

from fastapi import HTTPException, Depends, UploadFile, File, Form, Request
from typing import Optional, Dict, Any
import uuid, base64, logging, json
from src.datamodel.database.userauth.AuthenticationTables import User
from src.datamodel.database.domain.DigitalSignage import Event
from src.core.authentication.authentication import get_current_user
from b2sdk.v2 import InMemoryAccountInfo, B2Api
import os
from src.datamodel.datavalidation.apiconfig import ApiConfig  
from src.core.database.dbs.getdb import postresql as db
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)


def api_config():
    config = {
        "path": "",
        "status_code": 201,
        "tags": ["Organization"],
        "summary": "Create and save Entity data",
        "response_model": dict,
        "description": "This API endpoint creates a new entity and saves it in the database.",
        "response_description": "Details of the created entity.",
        "deprecated": False,
    }
    return ApiConfig(**config)


# Upload image to Backblaze B2
import base64
import os
from b2sdk.v2 import InMemoryAccountInfo, B2Api

def upload_image_to_b2(file_data: dict, base64_image: str) -> dict:
    """
    Uploads an image to Backblaze B2 and returns metadata for MongoDB.

    Args:
        file_data (dict): File metadata (name, size, type).
            Example: { "name": "20250712172424_ccc80a85.png", "size": 206601, "type": "image/png" }
        base64_image (str): Base64 string of the image. Must be "data:image/png;base64,...."

    Returns:
        dict: Metadata including B2 URL, name, size, type.
    """
    if not base64_image:
        raise ValueError("No image data provided")

    # Environment variables
    B2_ACCOUNT_ID = os.getenv("B2_KEY_ID")
    B2_APPLICATION_KEY = os.getenv("B2_APP_KEY")
    B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")

    # Ensure correct base64 format
    if "," in base64_image:
        _, encoded = base64_image.split(",", 1)
    else:
        encoded = base64_image

    # Fix base64 padding (must be multiple of 4)
    missing_padding = len(encoded) % 4
    if missing_padding:
        encoded += "=" * (4 - missing_padding)

    try:
        file_bytes = base64.b64decode(encoded)
    except Exception as e:
        raise ValueError(f"Invalid base64 data: {str(e)}")

    # Connect to Backblaze
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account("production", B2_ACCOUNT_ID, B2_APPLICATION_KEY)
    bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)

    # Upload using the original file name
    headers = {
    "Content-Type": file_data.content_type or "image/png"
}
    bucket.upload_bytes(
       file_bytes,
       file_data.filename,
       content_type=headers["Content-Type"]
    )

    # Create public URL
    url = f"https://{B2_BUCKET_NAME}.s3.eu-central-003.backblazeb2.com/{file_data.filename}"

    # Return object to store in MongoDB
    return {
        "name": file_data.filename,
        "size": file_data.size,
        "type": file_data.content_type,
        "url": url
    }

# Core DB creation
async def create_event_in_db(
    name: str,
    start_date: str,
    end_date: str,
    description: Optional[str],
    is_published: bool,
    metadata: Dict[str, Any],
    image_base64,
    current_user: User
):
    try:
        event_id = str(uuid.uuid4())
        image_url = image_base64["url"]

        new_event = Event(
            event_id=event_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            image_url=image_url,
            description=description,
            is_published=is_published in ["true", "True", True],
            created_by=current_user,
            updated_by=current_user,
            metadata=metadata
        )

        await new_event.insert()
        return {"message": "Event created successfully", "event_id": event_id, "title": name}

    except Exception as e:
        logger.error(f"Error creating event: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

# Main API endpoint
async def main(
    request: Request,
    name: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    description: Optional[str] = Form(None),
    is_published: Optional[str] = Form("true"),
    metadata: Optional[str] = Form("{}"),
    image_file: Optional[UploadFile] = File(None),
):
    # Parse metadata
    try:
        metadata_dict = json.loads(metadata) if metadata else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")
    content = await image_file.read()
    # Convert image file to Base64
    base64_image = f"data:{image_file.content_type};base64,{base64.b64encode(content).decode()}"
    if(image_file):
        image_base64=upload_image_to_b2(image_file , base64_image)
    
    return await create_event_in_db(
        name=name,
        start_date=start_date,
        end_date=end_date,
        description=description,
        is_published=is_published,
        metadata=metadata_dict,
        image_base64=image_base64,
       current_user="shamimahmadupup1"
    )

