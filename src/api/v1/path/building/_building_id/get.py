from fastapi import HTTPException, Path as FastAPIPath, Query, status
from pydantic import BaseModel
from typing import Optional, List
import logging

from src.datamodel.database.domain.DigitalSignage import Path, Building, Location, FloorSegment
from src.datamodel.datavalidation.apiconfig import ApiConfig

logger = logging.getLogger(__name__)


def api_config():
    config = {
        "path": "",
        "status_code": 200,
        "tags": ["Path"],
        "summary": "Get Paths by Building ID",
        "response_model": dict,
        "description": "Get all navigation paths for a given building with optional filters for is_multifloor and is_published.",
        "response_description": "List of paths in the building",
        "deprecated": False,
    }
    return ApiConfig(**config)


class PathListItem(BaseModel):
    path_id: str
    name: Optional[str] = None
    building_id: str
    created_by: Optional[str] = None

    start_point_id: str
    end_point_id: str
    start_point_name: Optional[str] = None
    end_point_name: Optional[str] = None

    is_published: bool
    is_multifloor: bool
    floors: List[str] = []
    connector_shared_ids: List[str] = []
    floor_segments: List[FloorSegment] = []

    tags: List[str] = []
    datetime: float
    status: str


async def main(
    building_id: str = FastAPIPath(..., description="Building ID to get paths for"),
    is_multifloor: Optional[bool] = Query(None, description="True for multi-floor paths, False for single-floor"),
    is_published: Optional[bool] = Query(None, description="Filter by published status"),
):
    try:
        # Validate building existence
        building = await Building.find_one({"building_id": building_id, "status": "active"})
        if not building:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Building with ID '{building_id}' not found",
            )

        # Build filters
        filter_query = {
            "status": "active",
            "building_id": building_id,
        }
        if is_multifloor is not None:
            filter_query["is_multifloor"] = is_multifloor
        if is_published is not None:
            filter_query["is_published"] = is_published

        paths = await Path.find(filter_query).to_list()

        # Prefetch start/end location names for endpoints
        location_ids = {p.start_point_id for p in paths if getattr(p, "start_point_id", None)} | {p.end_point_id for p in paths if getattr(p, "end_point_id", None)}
        location_names = {}
        if location_ids:
            locations = await Location.find({"location_id": {"$in": list(location_ids)}, "status": "active"}).to_list()
            location_names = {loc.location_id: loc.name for loc in locations}

        items: List[PathListItem] = []
        for p in paths:
            items.append(
                PathListItem(
                    path_id=p.path_id,
                    name=p.name,
                    building_id=p.building_id,
                    created_by=p.created_by,
                    start_point_id=p.start_point_id,
                    end_point_id=p.end_point_id,
                    start_point_name=location_names.get(p.start_point_id),
                    end_point_name=location_names.get(p.end_point_id),
                    is_published=p.is_published,
                    is_multifloor=p.is_multifloor,
                    floors=p.floors or [],
                    connector_shared_ids=p.connector_shared_ids or [],
                    floor_segments=p.floor_segments or [],
                    tags=p.tags or [],
                    datetime=p.datetime,
                    status=p.status,
                )
            )

        return {
            "status": "success",
            "message": f"Retrieved {len(items)} paths for building {building_id}",
            "data": {
                "paths": items,
                "count": len(items),
                "filters_applied": {
                    "building_id": building_id,
                    "is_multifloor": is_multifloor,
                    "is_published": is_published,
                },
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving building paths for '{building_id}': {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve building paths: {str(e)}",
        )
