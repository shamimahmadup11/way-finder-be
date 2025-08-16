from fastapi import HTTPException, Path as FastAPIPath, status
from pydantic import BaseModel
from typing import Optional, List
import logging

from src.datamodel.database.domain.DigitalSignage import Path, Location, VerticalConnector, Floor, NodeKind
from src.datamodel.datavalidation.apiconfig import ApiConfig

logger = logging.getLogger(__name__)


def _dump_without_object_id(doc):
    """Return a plain dict for a Beanie Document without the internal 'id' (PydanticObjectId)."""
    if not doc:
        return None
    try:
        # Exclude 'id' which is PydanticObjectId
        return doc.model_dump(exclude={"id"})
    except Exception:
        d = doc.model_dump()
        d.pop("id", None)
        return d


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
    start_point: Optional[dict] = None
    end_point: Optional[dict] = None

    is_published: bool
    is_multifloor: bool
    floors: List[str] = []
    connector_shared_ids: List[str] = []
    floors_details: List[dict] = []
    vertical_connectors: List[dict] = []

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

        # Collect detailed entities for response
        floor_ids = {seg.floor_id for seg in (path.floor_segments or [])}
        # Start/End location details (based on Location schema)
        start_location = await Location.find_one({"location_id": path.start_point_id, "status": "active"})
        end_location = await Location.find_one({"location_id": path.end_point_id, "status": "active"})

        # Vertical connectors used to shift between floors (transitions only)
        vertical_connectors = []
        if path.is_multifloor:
            segments = sorted((path.floor_segments or []), key=lambda s: getattr(s, "sequence", 0))
            transition_shared_ids = set()
            transition_floor_ids = set()
            transition_connector_ids = set()

            def is_vc_point(pt):
                kind_val = getattr(pt, "kind", None)
                return kind_val == NodeKind.VERTICAL_CONNECTOR or str(kind_val) == "vertical_connector"

            for i in range(len(segments) - 1):
                seg_a = segments[i]
                seg_b = segments[i + 1]
                if seg_a.floor_id == seg_b.floor_id:
                    continue
                # gather VC shared_ids/ref_ids from both segments
                a_shared = {p.shared_id for p in (seg_a.points or []) if is_vc_point(p) and getattr(p, "shared_id", None)}
                b_shared = {p.shared_id for p in (seg_b.points or []) if is_vc_point(p) and getattr(p, "shared_id", None)}
                common_shared = a_shared & b_shared
                if common_shared:
                    transition_shared_ids.update(common_shared)
                else:
                    transition_shared_ids.update(a_shared or b_shared)

                a_ref_ids = {p.ref_id for p in (seg_a.points or []) if is_vc_point(p) and getattr(p, "ref_id", None)}
                b_ref_ids = {p.ref_id for p in (seg_b.points or []) if is_vc_point(p) and getattr(p, "ref_id", None)}
                transition_connector_ids.update(a_ref_ids)
                transition_connector_ids.update(b_ref_ids)

                transition_floor_ids.add(seg_a.floor_id)
                transition_floor_ids.add(seg_b.floor_id)

            if transition_shared_ids or transition_connector_ids:
                vc_query = {"status": "active"}
                or_clauses = []
                if transition_connector_ids:
                    or_clauses.append({"connector_id": {"$in": list(transition_connector_ids)}})
                if transition_shared_ids:
                    or_clauses.append({"shared_id": {"$in": list(transition_shared_ids)}})
                if or_clauses:
                    vc_query["$or"] = or_clauses
                if transition_floor_ids:
                    vc_query["floor_id"] = {"$in": list(transition_floor_ids)}
                vcs = await VerticalConnector.find(vc_query).to_list()
                # Deduplicate by connector_id
                seen = set()
                for vc in vcs:
                    if vc.connector_id not in seen:
                        vertical_connectors.append(_dump_without_object_id(vc))
                        seen.add(vc.connector_id)

        # Floors details for floors referenced in the path
        floors_details = []
        if floor_ids:
            floors_docs = await Floor.find({"floor_id": {"$in": list(floor_ids)}, "status": "active"}).to_list()
            floors_details = [_dump_without_object_id(f) for f in floors_docs]

        item = PathDetail(
            path_id=path.path_id,
            name=path.name,
            building_id=path.building_id,
            created_by=path.created_by,
            start_point_id=path.start_point_id,
            end_point_id=path.end_point_id,
            start_point=_dump_without_object_id(start_location),
            end_point=_dump_without_object_id(end_location),
            is_published=path.is_published,
            is_multifloor=path.is_multifloor,
            floors=path.floors or [],
            connector_shared_ids=path.connector_shared_ids or [],
            floors_details=floors_details,
            vertical_connectors=vertical_connectors,
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
