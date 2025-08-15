from fastapi import HTTPException, Path as FastAPIPath, Query, status
from typing import Optional
import time
import logging

from src.datamodel.database.domain.DigitalSignage import Path, Floor
from src.datamodel.datavalidation.apiconfig import ApiConfig

logger = logging.getLogger(__name__)


def api_config():
    config = {
        "path": "",
        "status_code": 200,
        "tags": ["Path"],
        "summary": "Delete Path",
        "response_model": dict,
        "description": "Delete a navigation path by marking it as inactive.",
        "response_description": "Deletion confirmation",
        "deprecated": False,
    }
    return ApiConfig(**config)


async def main(
    path_id: str = FastAPIPath(..., description="Path ID to delete"),
    updated_by: Optional[str] = Query(None, description="User performing the deletion"),
):
    try:
        # Find the path regardless of status to support idempotent deletes
        path = await Path.find_one({"path_id": path_id})
        if not path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Path with ID '{path_id}' not found",
            )

        # Preserve current floors to remove membership
        path.recompute_denorm()
        floors_to_update = set(path.floors or [])

        already_inactive = path.status != "active"

        # Soft delete: mark as inactive and update metadata
        path.status = "inactive"
        if updated_by is not None:
            path.updated_by = updated_by
        path.update_on = time.time()
        await path.save()

        # Remove path_id from related floors' paths arrays
        floors_updated = 0
        for fid in floors_to_update:
            floor = await Floor.find_one({"floor_id": fid, "status": "active"})
            if floor and floor.paths:
                if path.path_id in floor.paths:
                    floor.paths.remove(path.path_id)
                    floor.update_on = time.time()
                    await floor.save()
                    floors_updated += 1

        msg = "Path already inactive; memberships cleaned" if already_inactive else "Path deleted successfully"

        return {
            "status": "success",
            "message": msg,
            "data": {
                "path_id": path.path_id,
                "status": path.status,
                "floors_updated": floors_updated,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting path '{path_id}': {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete path: {str(e)}",
        )
