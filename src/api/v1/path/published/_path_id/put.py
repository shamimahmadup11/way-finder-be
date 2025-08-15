from fastapi import HTTPException, Path as FastAPIPath, Query, status
from typing import Optional
import time
import logging

from src.datamodel.database.domain.DigitalSignage import Path
from src.datamodel.datavalidation.apiconfig import ApiConfig

logger = logging.getLogger(__name__)


def api_config():
    config = {
        "path": "",
        "status_code": 200,
        "tags": ["Path"],
        "summary": "Toggle Path Publish Status",
        "response_model": dict,
        "description": "Toggle the publish status of a path. If published, it will be unpublished and vice versa.",
        "response_description": "Updated path publish status",
        "deprecated": False,
    }
    return ApiConfig(**config)


async def main(
    path_id: str = FastAPIPath(..., description="Path ID to toggle publish status"),
    updated_by: Optional[str] = Query(None, description="User performing the action"),
):
    try:
        path = await Path.find_one({"path_id": path_id, "status": "active"})
        if not path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Path with ID '{path_id}' not found",
            )

        previous = path.is_published
        path.is_published = not bool(path.is_published)
        if updated_by is not None:
            path.updated_by = updated_by
        path.update_on = time.time()

        await path.save()

        return {
            "status": "success",
            "message": "Path publish status toggled",
            "data": {
                "path_id": path.path_id,
                "previous_is_published": previous,
                "is_published": path.is_published,
                "updated_on": path.update_on,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error toggling publish status for path '{path_id}': {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle publish status: {str(e)}",
        )
