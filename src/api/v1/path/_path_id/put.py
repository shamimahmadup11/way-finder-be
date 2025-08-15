from fastapi import HTTPException, Path as FastAPIPath, status
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
import time
import logging

from src.datamodel.database.domain.DigitalSignage import (
    Path,
    PathPoint,
    FloorSegment,
    NodeKind,
    Location,
    VerticalConnector,
    Floor,
    Building,
)
from src.datamodel.datavalidation.apiconfig import ApiConfig

logger = logging.getLogger(__name__)


def api_config():
    config = {
        "path": "",
        "status_code": 200,
        "tags": ["Path"],
        "summary": "Update Path",
        "response_model": dict,
        "description": "Update an existing navigation path.",
        "response_description": "Updated path data",
        "deprecated": False,
    }
    return ApiConfig(**config)


# -----------------------------
# Request/Response Models
# -----------------------------

class PathUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Human-friendly name for the path")
    building_id: Optional[str] = Field(None, description="Building this path belongs to")

    # Endpoints
    start_point_id: Optional[str] = Field(None, description="Starting point Id")
    end_point_id: Optional[str] = Field(None, description="End point Id")

    # Publication & behavior
    is_published: Optional[bool] = Field(None, description="Whether the path is published")

    # Geometry
    floor_segments: Optional[List[FloorSegment]] = Field(None, description="Per-floor segments forming the path (full replacement)")

    # Common metadata
    tags: Optional[List[str]] = Field(None, description="Search/filter tags (full replacement)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata (full replacement)")
    updated_by: Optional[str] = Field(None, description="User who last updated the path")

    @validator("floor_segments")
    def validate_segments(cls, v: Optional[List[FloorSegment]]):
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError("At least one floor segment is required when provided")
        for seg in v:
            if not seg.points or len(seg.points) < 2:
                raise ValueError("Each floor segment must have at least 2 points")
        return v


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


# -----------------------------
# Helper validations
# -----------------------------

async def _ensure_building_exists(building_id: str):
    building = await Building.find_one({"building_id": building_id, "status": "active"})
    if not building:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Building with ID '{building_id}' not found",
        )


async def _ensure_floors_exist(floor_ids: List[str]):
    if not floor_ids:
        return
    missing: List[str] = []
    for fid in set(floor_ids):
        f = await Floor.find_one({"floor_id": fid, "status": "active"})
        if not f:
            missing.append(fid)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Floor(s) not found: {', '.join(missing)}",
        )


async def _validate_and_enrich_points(seg: FloorSegment) -> FloorSegment:
    enriched_points: List[PathPoint] = []
    for p in seg.points:
        if p.kind == NodeKind.LOCATION:
            if not p.ref_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location point requires ref_id")
            loc = await Location.find_one({"location_id": p.ref_id, "status": "active"})
            if not loc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Location with ID '{p.ref_id}' not found",
                )
            if loc.floor_id != seg.floor_id:
                logger.warning(f"Location {loc.location_id} belongs to floor {loc.floor_id}, but used on segment floor {seg.floor_id}")

        elif p.kind == NodeKind.VERTICAL_CONNECTOR:
            if not p.ref_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vertical connector point requires ref_id")
            conn = await VerticalConnector.find_one({
                "connector_id": p.ref_id,
                "status": "active",
            })
            if not conn:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Vertical connector with ID '{p.ref_id}' not found",
                )
            if conn.floor_id != seg.floor_id:
                logger.warning(f"Vertical connector {conn.connector_id} belongs to floor {conn.floor_id}, used on floor {seg.floor_id}")
            if not p.shared_id:
                p.shared_id = conn.shared_id

        elif p.kind == NodeKind.WAYPOINT:
            if p.x is None or p.y is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Waypoint requires x and y coordinates")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported point kind: {p.kind}")
        enriched_points.append(p)

    seg.points = enriched_points
    return seg


# -----------------------------
# Endpoint
# -----------------------------

async def main(
    path_id: str = FastAPIPath(..., description="Path ID to update"),
    path_data: PathUpdateRequest = None,
):
    try:
        existing = await Path.find_one({"path_id": path_id, "status": "active"})
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Path with ID '{path_id}' not found",
            )

        # Keep original floors for membership updates
        existing.recompute_denorm()
        old_floors = set(existing.floors or [])

        # Optional building update
        if path_data and path_data.building_id is not None:
            await _ensure_building_exists(path_data.building_id)
            existing.building_id = path_data.building_id

        # Simple scalar fields
        if path_data and path_data.name is not None:
            existing.name = path_data.name
        if path_data and path_data.start_point_id is not None:
            existing.start_point_id = path_data.start_point_id
        if path_data and path_data.end_point_id is not None:
            existing.end_point_id = path_data.end_point_id
        if path_data and path_data.is_published is not None:
            existing.is_published = path_data.is_published
        if path_data and path_data.tags is not None:
            existing.tags = path_data.tags
        if path_data and path_data.metadata is not None:
            existing.metadata = path_data.metadata

        # Floor segments replacement
        if path_data and path_data.floor_segments is not None:
            await _ensure_floors_exist([s.floor_id for s in path_data.floor_segments])

            validated_segments: List[FloorSegment] = []
            for seg in sorted(path_data.floor_segments, key=lambda s: s.sequence):
                validated = await _validate_and_enrich_points(seg)
                validated_segments.append(validated)

            existing.floor_segments = validated_segments

        # Recompute denormalized helpers, timestamps, and updater
        existing.recompute_denorm()
        if path_data and path_data.updated_by is not None:
            existing.updated_by = path_data.updated_by
        existing.update_on = time.time()

        # Save path
        await existing.save()

        # Update floor membership if changed
        new_floors = set(existing.floors or [])
        to_add = new_floors - old_floors
        to_remove = old_floors - new_floors

        for fid in to_add:
            floor = await Floor.find_one({"floor_id": fid, "status": "active"})
            if floor:
                if existing.path_id not in (floor.paths or []):
                    floor.paths.append(existing.path_id)
                floor.update_on = time.time()
                await floor.save()

        for fid in to_remove:
            floor = await Floor.find_one({"floor_id": fid, "status": "active"})
            if floor and floor.paths:
                if existing.path_id in floor.paths:
                    floor.paths.remove(existing.path_id)
                floor.update_on = time.time()
                await floor.save()

        # Build response
        resp = PathDetail(
            path_id=existing.path_id,
            name=existing.name,
            building_id=existing.building_id,
            created_by=existing.created_by,
            start_point_id=existing.start_point_id,
            end_point_id=existing.end_point_id,
            is_published=existing.is_published,
            is_multifloor=existing.is_multifloor,
            floors=existing.floors or [],
            connector_shared_ids=existing.connector_shared_ids or [],
            floor_segments=[s.model_dump() for s in (existing.floor_segments or [])],
            tags=existing.tags or [],
            datetime=existing.datetime,
            status=existing.status,
        )

        return {
            "status": "success",
            "message": "Path updated successfully",
            "data": resp,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating path '{path_id}': {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update path: {str(e)}",
        )
