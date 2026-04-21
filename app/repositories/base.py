"""
Base repository abstract class for BARROW.AI.
Implements repository pattern with common CRUD operations.
Provides SOLID principles compliance with dependency inversion.
"""

from typing import TypeVar, Generic, Type, Optional, List, Dict, Any, Union, Protocol
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from pydantic import BaseModel

from app.core.database import Base
from app.core.logging import get_logger
from app.core.exceptions import NotFoundException, DatabaseError

logger = get_logger(__name__)

# Protocol for SQLAlchemy model constraint
class SQLAlchemyModel(Protocol):
    """Protocol for SQLAlchemy ORM model."""
    pass

# Type variable for SQLAlchemy model (using Protocol instead of Base)
ModelType = TypeVar('ModelType', bound=SQLAlchemyModel)
# Type variable for Pydantic create schema
CreateSchemaType = TypeVar('CreateSchemaType', bound=BaseModel)
# Type variable for Pydantic update schema
UpdateSchemaType = TypeVar('UpdateSchemaType', bound=BaseModel)


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    Abstract base repository with common CRUD operations.
    
    Implements repository pattern for clean separation of concerns.
    All database operations are centralized here.
    
    Type Parameters:
        ModelType: SQLAlchemy model class
        CreateSchemaType: Pydantic schema for creation
        UpdateSchemaType: Pydantic schema for updates
    """
    
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository with model and session.
        
        Args:
            model: SQLAlchemy model class
            session: Async database session
        """
        self.model = model
        self.session = session
    
    async def create(self, data: Union[CreateSchemaType, Dict[str, Any]]) -> ModelType:
        """
        Create a new record.
        
        Args:
            data: Creation data as Pydantic schema or dict
            
        Returns:
            Created model instance
            
        Raises:
            DatabaseError: If creation fails
        """
        try:
            if isinstance(data, BaseModel):
                create_data = data.model_dump(exclude_unset=True)
            else:
                create_data = data
            
            instance = self.model(**create_data)
            self.session.add(instance)
            await self.session.flush()
            await self.session.refresh(instance)
            
            logger.debug(
                f"created_{self.model.__tablename__}",
                id=str(instance.id)
            )
            
            return instance
            
        except Exception as e:
            logger.error(
                f"create_{self.model.__tablename__}_failed",
                error=str(e),
                exc_info=True
            )
            await self.session.rollback()
            raise DatabaseError(f"Failed to create {self.model.__name__}: {str(e)}", e)
    
    async def create_many(self, items: List[Union[CreateSchemaType, Dict[str, Any]]]) -> List[ModelType]:
        """
        Create multiple records in bulk.
        
        Args:
            items: List of creation data
            
        Returns:
            List of created model instances
        """
        try:
            instances = []
            for item in items:
                if isinstance(item, BaseModel):
                    create_data = item.model_dump(exclude_unset=True)
                else:
                    create_data = item
                instances.append(self.model(**create_data))
            
            self.session.add_all(instances)
            await self.session.flush()
            
            for instance in instances:
                await self.session.refresh(instance)
            
            logger.debug(
                f"created_many_{self.model.__tablename__}",
                count=len(instances)
            )
            
            return instances
            
        except Exception as e:
            logger.error(
                f"create_many_{self.model.__tablename__}_failed",
                error=str(e),
                exc_info=True
            )
            await self.session.rollback()
            raise DatabaseError(f"Failed to create multiple {self.model.__name__}: {str(e)}", e)
    
    async def get_by_id(self, id: Union[UUID, str]) -> Optional[ModelType]:
        """
        Get a record by ID.
        
        Args:
            id: Record ID (UUID or string)
            
        Returns:
            Model instance or None if not found
        """
        try:
            if isinstance(id, str):
                try:
                    id = UUID(id)
                except ValueError:
                    return None
            
            stmt = select(self.model).where(self.model.id == id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(
                f"get_by_id_{self.model.__tablename__}_failed",
                id=str(id),
                error=str(e)
            )
            raise DatabaseError(f"Failed to get {self.model.__name__} by ID: {str(e)}", e)
    
    async def get_by_id_or_raise(self, id: Union[UUID, str]) -> ModelType:
        """
        Get a record by ID or raise NotFoundException.
        
        Args:
            id: Record ID
            
        Returns:
            Model instance
            
        Raises:
            NotFoundException: If record not found
        """
        instance = await self.get_by_id(id)
        if not instance:
            raise NotFoundException(self.model.__name__, str(id))
        return instance
    
    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = True
    ) -> List[ModelType]:
        """
        Get all records with pagination.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            order_by: Field to order by
            order_desc: Order descending if True
            
        Returns:
            List of model instances
        """
        try:
            stmt = select(self.model)
            
            if order_by and hasattr(self.model, order_by):
                order_column = getattr(self.model, order_by)
                if order_desc:
                    stmt = stmt.order_by(order_column.desc())
                else:
                    stmt = stmt.order_by(order_column.asc())
            
            stmt = stmt.offset(skip).limit(limit)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
            
        except Exception as e:
            logger.error(
                f"get_all_{self.model.__tablename__}_failed",
                error=str(e)
            )
            raise DatabaseError(f"Failed to get all {self.model.__name__}: {str(e)}", e)
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count records matching filters.
        
        Args:
            filters: Optional filter conditions
            
        Returns:
            Total count
        """
        try:
            stmt = select(func.count()).select_from(self.model)
            
            if filters:
                for key, value in filters.items():
                    if hasattr(self.model, key):
                        stmt = stmt.where(getattr(self.model, key) == value)
            
            result = await self.session.execute(stmt)
            return result.scalar() or 0
            
        except Exception as e:
            logger.error(
                f"count_{self.model.__tablename__}_failed",
                error=str(e)
            )
            raise DatabaseError(f"Failed to count {self.model.__name__}: {str(e)}", e)
    
    async def update(
        self,
        id: Union[UUID, str],
        data: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> Optional[ModelType]:
        """
        Update a record by ID.
        
        Args:
            id: Record ID
            data: Update data
            
        Returns:
            Updated model instance or None if not found
        """
        try:
            if isinstance(id, str):
                try:
                    id = UUID(id)
                except ValueError:
                    return None
            
            if isinstance(data, BaseModel):
                update_data = data.model_dump(exclude_unset=True, exclude={'id'})
            else:
                update_data = data
            
            if not update_data:
                return await self.get_by_id(id)
            
            # Add updated_at if model has the field
            if hasattr(self.model, 'updated_at'):
                update_data['updated_at'] = datetime.utcnow()
            
            stmt = (
                update(self.model)
                .where(self.model.id == id)
                .values(**update_data)
                .returning(self.model)
            )
            
            result = await self.session.execute(stmt)
            await self.session.flush()
            
            instance = result.scalar_one_or_none()
            if instance:
                logger.debug(
                    f"updated_{self.model.__tablename__}",
                    id=str(id)
                )
            
            return instance
            
        except Exception as e:
            logger.error(
                f"update_{self.model.__tablename__}_failed",
                id=str(id),
                error=str(e)
            )
            await self.session.rollback()
            raise DatabaseError(f"Failed to update {self.model.__name__}: {str(e)}", e)
    
    async def update_or_raise(
        self,
        id: Union[UUID, str],
        data: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> ModelType:
        """
        Update a record or raise NotFoundException.
        
        Args:
            id: Record ID
            data: Update data
            
        Returns:
            Updated model instance
            
        Raises:
            NotFoundException: If record not found
        """
        instance = await self.update(id, data)
        if not instance:
            raise NotFoundException(self.model.__name__, str(id))
        return instance
    
    async def delete(self, id: Union[UUID, str]) -> bool:
        """
        Delete a record by ID.
        
        Args:
            id: Record ID
            
        Returns:
            True if deleted, False if not found
        """
        try:
            if isinstance(id, str):
                try:
                    id = UUID(id)
                except ValueError:
                    return False
            
            stmt = delete(self.model).where(self.model.id == id)
            result = await self.session.execute(stmt)
            await self.session.flush()
            
            deleted = result.rowcount > 0
            if deleted:
                logger.debug(
                    f"deleted_{self.model.__tablename__}",
                    id=str(id)
                )
            
            return deleted
            
        except Exception as e:
            logger.error(
                f"delete_{self.model.__tablename__}_failed",
                id=str(id),
                error=str(e)
            )
            await self.session.rollback()
            raise DatabaseError(f"Failed to delete {self.model.__name__}: {str(e)}", e)
    
    async def delete_or_raise(self, id: Union[UUID, str]) -> None:
        """
        Delete a record or raise NotFoundException.
        
        Args:
            id: Record ID
            
        Raises:
            NotFoundException: If record not found
        """
        deleted = await self.delete(id)
        if not deleted:
            raise NotFoundException(self.model.__name__, str(id))
    
    async def exists(self, id: Union[UUID, str]) -> bool:
        """
        Check if a record exists.
        
        Args:
            id: Record ID
            
        Returns:
            True if exists, False otherwise
        """
        try:
            if isinstance(id, str):
                try:
                    id = UUID(id)
                except ValueError:
                    return False
            
            stmt = select(self.model.id).where(self.model.id == id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none() is not None
            
        except Exception as e:
            logger.error(
                f"exists_{self.model.__tablename__}_failed",
                id=str(id),
                error=str(e)
            )
            return False
    
    async def find_one(self, **filters) -> Optional[ModelType]:
        """
        Find one record matching filters.
        
        Args:
            **filters: Field-value pairs to filter by
            
        Returns:
            Model instance or None
        """
        try:
            stmt = select(self.model)
            
            for key, value in filters.items():
                if hasattr(self.model, key):
                    stmt = stmt.where(getattr(self.model, key) == value)
            
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(
                f"find_one_{self.model.__tablename__}_failed",
                filters=str(filters),
                error=str(e)
            )
            raise DatabaseError(f"Failed to find {self.model.__name__}: {str(e)}", e)
    
    async def find_many(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = True,
        **filters
    ) -> List[ModelType]:
        """
        Find multiple records matching filters.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records
            order_by: Field to order by
            order_desc: Order descending if True
            **filters: Field-value pairs to filter by
            
        Returns:
            List of model instances
        """
        try:
            stmt = select(self.model)
            
            for key, value in filters.items():
                if hasattr(self.model, key):
                    stmt = stmt.where(getattr(self.model, key) == value)
            
            if order_by and hasattr(self.model, order_by):
                order_column = getattr(self.model, order_by)
                if order_desc:
                    stmt = stmt.order_by(order_column.desc())
                else:
                    stmt = stmt.order_by(order_column.asc())
            
            stmt = stmt.offset(skip).limit(limit)
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
            
        except Exception as e:
            logger.error(
                f"find_many_{self.model.__tablename__}_failed",
                filters=str(filters),
                error=str(e)
            )
            raise DatabaseError(f"Failed to find {self.model.__name__}: {str(e)}", e)
    
    def query(self) -> Select:
        """
        Get a base query builder for custom queries.
        
        Returns:
            SQLAlchemy Select statement
        """
        return select(self.model)
    
    async def execute_raw(self, stmt) -> Any:
        """
        Execute a raw SQLAlchemy statement.
        
        Args:
            stmt: SQLAlchemy statement
            
        Returns:
            Statement result
        """
        try:
            return await self.session.execute(stmt)
        except Exception as e:
            logger.error(
                f"execute_raw_{self.model.__tablename__}_failed",
                error=str(e)
            )
            raise DatabaseError(f"Failed to execute raw query: {str(e)}", e)