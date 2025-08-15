from fastapi import HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
import time
import logging

from src.datamodel.database.domain.DigitalSignage import (
    Path,
    Floor,
    Building,
    Location,
    VerticalConnector,
    PathPoint,
    FloorSegment,
    NodeKind,
)
from src.datamodel.datavalidation.apiconfig import ApiConfig

logger = logging.getLogger(__name__)


def api_config():
    config = {
        "path": "",
        "status_code": 201,
        "tags": ["Path"],
        "summary": "Create Path (Single or Multi-Floor)",
        "response_model": dict,
        "description": "Create a navigation path between locations. Supports both single-floor and multi-floor paths with vertical connectors.",
        "response_description": "Created path data",
        "deprecated": False,
    }
    return ApiConfig(**config)


# -----------------------------
# Request/Response Models
# -----------------------------

class PathCreateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Human-friendly name for the path")
    building_id: str = Field(..., description="Building this path belongs to")
    created_by: Optional[str] = Field(None, description="User who created the path")

    # Endpoints
    start_point_id: str = Field(..., description="Starting point Id (Location/Connector/Waypoint synthetic id)")
    end_point_id: str = Field(..., description="End point Id (Location/Connector/Waypoint synthetic id)")

    # Publication & behavior
    is_published: bool = Field(False, description="Whether the path is published")

    # Geometry
    floor_segments: List[FloorSegment] = Field(..., description="Per-floor segments forming the path")

    # Common metadata
    tags: List[str] = Field(default_factory=list, description="Search/filter tags")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    @validator("floor_segments")
    def validate_segments(cls, v: List[FloorSegment]):
        if not v or len(v) == 0:
            raise ValueError("At least one floor segment is required")
        for seg in v:
            if not seg.points or len(seg.points) < 2:
                raise ValueError("Each floor segment must have at least 2 points")
        return v


class PathResponse(BaseModel):
    path_id: str
    name: Optional[str]
    building_id: str
    created_by: Optional[str]

    start_point_id: str
    end_point_id: str

    is_published: bool
    floor_segments: List[dict]

    floors: List[str]
    connector_shared_ids: List[str]
    is_multifloor: bool
    tags: List[str]
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
    """Validate referenced entities for a segment's points. Enrich vertical connectors' shared_id if missing."""
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
            # Optionally validate the location's floor matches segment floor
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
            # Best-effort: ensure it's present on this floor
            if conn.floor_id != seg.floor_id:
                logger.warning(f"Vertical connector {conn.connector_id} belongs to floor {conn.floor_id}, used on floor {seg.floor_id}")
            # Enrich shared_id if not provided
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

async def main(path_data: PathCreateRequest):
    try:
        # Validate building and floors
        await _ensure_building_exists(path_data.building_id)
        await _ensure_floors_exist([s.floor_id for s in path_data.floor_segments])

        # Validate and enrich points per segment
        validated_segments: List[FloorSegment] = []
        for seg in sorted(path_data.floor_segments, key=lambda s: s.sequence):
            validated = await _validate_and_enrich_points(seg)
            validated_segments.append(validated)

        # Create the Path document
        new_path = Path(
            name=path_data.name,
            building_id=path_data.building_id,
            created_by=path_data.created_by,
            start_point_id=path_data.start_point_id,
            end_point_id=path_data.end_point_id,
            is_published=path_data.is_published,
            floor_segments=validated_segments,
            tags=path_data.tags or [],
            metadata=path_data.metadata or {},
            datetime=time.time(),
            status="active",
        )

        # Compute denormalized helpers
        new_path.recompute_denorm()

        # Save to database
        await new_path.insert()

        # Update each floor's paths list
        unique_floors = set(new_path.floors)
        for fid in unique_floors:
            floor = await Floor.find_one({"floor_id": fid, "status": "active"})
            if floor:
                if new_path.path_id not in (floor.paths or []):
                    floor.paths.append(new_path.path_id)
                floor.update_on = time.time()
                await floor.save()

        logger.info(f"Path created successfully: {new_path.path_id} | multi-floor={new_path.is_multifloor}")

        # Prepare response
        response = PathResponse(
            path_id=new_path.path_id,
            name=new_path.name,
            building_id=new_path.building_id,
            created_by=new_path.created_by,
            start_point_id=new_path.start_point_id,
            end_point_id=new_path.end_point_id,
            is_published=new_path.is_published,
            floor_segments=[s.model_dump() for s in new_path.floor_segments],
            floors=new_path.floors,
            connector_shared_ids=new_path.connector_shared_ids,
            is_multifloor=new_path.is_multifloor,
            tags=new_path.tags or [],
            datetime=new_path.datetime,
            status=new_path.status,
        )

        return {
            "status": "success",
            "message": "Path created successfully",
            "data": response,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating path: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create path: {str(e)}",
        )
