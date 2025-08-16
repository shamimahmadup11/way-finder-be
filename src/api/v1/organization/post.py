


from fastapi import HTTPException, Depends, Request, status
from pydantic import BaseModel, Field, conint
from typing import List, Optional, Dict, Literal
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import logging
from uuid import uuid4
from src.datamodel.database.userauth.AuthenticationTables import Entity, Address, User, Role, UserEntityRoleMap
from src.core.authentication.authentication import get_current_user
from sqlalchemy.exc import IntegrityError
from src.datamodel.datavalidation.apiconfig import ApiConfig  
from src.core.database.dbs.getdb import postresql as db
from src.services.permit.permit_service import PermitService
from sqlalchemy import select


logger = logging.getLogger(__name__)
permit_service = PermitService()


class EntityCreate(BaseModel):
    entity_type: str  # "parent" or "entity"
    name: str
    description: Optional[str] = None  # Used for organizations
    headcount: Optional[int] = None  # Used for parents
    domain: Optional[str] = None  # Used for parents
    parent_uuid: Optional[str] = None  # Reference to parent entity
    address_id: int  # Foreign key reference
    created_by: Optional[str] = None
    updated_by: Optional[str] = None  

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

async def create_entity(entity_data: EntityCreate, db: AsyncSession, current_user: User):
    try:
        # Check if the current user has the "superadmin" role
        role_query = select(Role).where(Role.role_id == current_user.role_id)
        role_result = await db.execute(role_query)
        user_role = role_result.scalar_one_or_none()

        if not user_role or user_role.role_id not in [1, 4]:
            raise HTTPException(status_code=403, detail="Permission denied: Only Super Admin can create an entity")
        
        # Checking for address_id
        address_query = select(Address).where(Address.address_id == entity_data.address_id)
        address_result = await db.execute(address_query)
        address = address_result.scalar_one_or_none()
        
        if not address:
            address_id = None
        else:
            address_id = entity_data.address_id
            
        # Check if entity with same name already exists
        entity_query = select(Entity).where(Entity.name == entity_data.name)
        entity_result = await db.execute(entity_query)
        existing_entity = entity_result.scalar_one_or_none()
        
        if existing_entity:
            raise HTTPException(status_code=409, detail=f"Entity with name '{entity_data.name}' already exists")
        
        # create organization in permit.io
        new_tenant = await permit_service.create_org_only(entity_data.name, entity_data.description)
        
        # Create the new entity
        new_entity = Entity(
            entity_uuid=str(new_tenant.id),
            entity_key=new_tenant.key,
            entity_type=entity_data.entity_type,
            name=entity_data.name,
            description=entity_data.description,
            headcount=entity_data.headcount,
            domain=entity_data.domain,
            is_active=True,
            parent_uuid=entity_data.parent_uuid,
            address_id=address_id,
            created_by=current_user.user_uuid, 
            updated_by=current_user.user_uuid,
            created_on=datetime.utcnow(),
            updated_on=datetime.utcnow(),
        )
        db.add(new_entity)
        await db.commit()
        await db.refresh(new_entity)

        # Fetch the role
        admin_role_query = select(Role).where(Role.role_id == user_role.role_id)
        admin_role_result = await db.execute(admin_role_query)
        admin_role = admin_role_result.scalar_one_or_none()
        
        if not admin_role:
            raise HTTPException(status_code=400, detail="Role does not exist")

        # Check if a mapping already exists to avoid duplicate
        mapping_query = select(UserEntityRoleMap).where(
            UserEntityRoleMap.user_uuid == current_user.user_uuid,
            UserEntityRoleMap.entity_uuid == new_entity.entity_uuid,
            UserEntityRoleMap.role_id == user_role.role_id
        )
        mapping_result = await db.execute(mapping_query)
        existing_mapping = mapping_result.scalar_one_or_none()
        
        # Only create the mapping if it doesn't already exist
        if not existing_mapping:
            # Create a mapping in UserEntityRoleMap
            role_mapping = UserEntityRoleMap(
                user_uuid=current_user.user_uuid,  # The user creating the entity
                role_id=user_role.role_id,        # The user's role
                entity_uuid=new_entity.entity_uuid, # The newly created entity
                created_on=datetime.utcnow(),
                updated_on=datetime.utcnow()
            )
            db.add(role_mapping)
            try:
                await db.commit()
            except IntegrityError as e:
                await db.rollback()
                # If we still get an integrity error, it might be a race condition
                # Just log it and continue since the entity was created successfully
                logger.warning(f"Could not create role mapping: {str(e)}")

        response = {
            "message": "Entity created successfully and role mapped",
            "entity_uuid": new_entity.entity_uuid,
            "name": new_entity.name,
        }
            
        return response
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Integrity error: {str(e)}")
        # Check if this is a duplicate entity name error
        if "duplicate key" in str(e) and "entity_name_key" in str(e):
            raise HTTPException(status_code=409, detail=f"Entity with name '{entity_data.name}' already exists")
        # Check if this is a duplicate role mapping error
        elif "duplicate key" in str(e) and "user_enitity_role_map_pkey" in str(e):
            # The entity was created but the role mapping failed
            # We can return success with a warning
            return {
                "message": "Entity created successfully but role mapping already exists",
                "entity_uuid": new_entity.entity_uuid if 'new_entity' in locals() else None,
                "name": entity_data.name,
                "warning": "Role mapping already exists"
            }
        else:
            raise HTTPException(status_code=400, detail=f"Database integrity error: {str(e)}")
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating entity: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


async def main(
    entity_data: EntityCreate, 
    db: AsyncSession = Depends(db), 
    current_user: User = Depends(get_current_user)  # Get the current user
):
    return await create_entity(entity_data, db, current_user)
