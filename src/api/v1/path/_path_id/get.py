from fastapi import HTTPException, Path as FastAPIPath, status
from pydantic import BaseModel
from typing import Optional, List
import logging

from src.datamodel.database.domain.DigitalSignage import Path
from src.datamodel.datavalidation.apiconfig import ApiConfig

logger = logging.getLogger(__name__)


def api_config():
    config = {
        "path": "",
        "status_code": 200,
        "tags": ["Path"],
        "summary": "Get Path by ID",
        "response_model": dict,
        "description": "Get a specific navigation path by its ID.",
        "response_description": "Path details",
        "deprecated": False,
    }
    return ApiConfig(**config)


class PathDetail(BaseModel):
    path_id: str
    name: Optional[str] = None
    building_id: str
    created_by: Optional[str] = None

    start_point_id: str
    end_point_id: str

    is_published: bool
    is_multifloor: bool
    floors: List[str] = []
    connector_shared_ids: List[str] = []

    floor_segments: List[dict]

    tags: List[str] = []
    datetime: float
    status: str


async def main(
    path_id: str = FastAPIPath(..., description="Path ID to retrieve"),
):
    try:
        path = await Path.find_one({"path_id": path_id, "status": "active"})
        if not path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Path with ID '{path_id}' not found",
            )

        item = PathDetail(
            path_id=path.path_id,
            name=path.name,
            building_id=path.building_id,
            created_by=path.created_by,
            start_point_id=path.start_point_id,
            end_point_id=path.end_point_id,
            is_published=path.is_published,
            is_multifloor=path.is_multifloor,
            floors=path.floors or [],
            connector_shared_ids=path.connector_shared_ids or [],
            floor_segments=[s.model_dump() for s in (path.floor_segments or [])],
            tags=path.tags or [],
            datetime=path.datetime,
            status=path.status,
        )

        return {
            "status": "success",
            "message": "Path retrieved successfully",
            "data": item,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving path '{path_id}': {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve path: {str(e)}",
        )
