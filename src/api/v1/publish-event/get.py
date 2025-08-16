from fastapi import HTTPException, Request, status
from typing import List
from src.datamodel.database.domain.DigitalSignage import Event
import logging
from src.datamodel.datavalidation.apiconfig import ApiConfig  
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, Depends, File, Form
import  logging
from src.datamodel.database.userauth.AuthenticationTables import User
from src.datamodel.database.domain.DigitalSignage import Event
from src.core.authentication.authentication import get_current_user, get_token_payload
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


async def get_all_events():
    try:
        # Fetch all events from DB
        events: List[Event] = await Event.find({}).to_list()

        # Convert to JSON-serializable format
        event_list = []
        for event in events:
            event_list.append({
                "event_id": event.event_id,
                "name": event.name,
                "event_type": getattr(event, "event_type", None),  # if you store type
                "start_date": event.start_date,
                "end_date": event.end_date,
                "image_url": event.image_url,
                "description": event.description,
                "is_published": event.is_published,
                "metadata": event.metadata,
                "created_by": event.created_by,
                "updated_by": event.updated_by,
            })

        return {"events": event_list, "count": len(event_list)}

    except Exception as e:
        logger.error(f"Error fetching events: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")



async def main():
    return await get_all_events()

