"""
Common request models for pagination, filtering, and sorting.
"""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class PaginationParams(BaseModel):
    """
    Pagination parameters for list endpoints.
    """
    
    page: int = Field(
        default=1,
        ge=1,
        description="Page number (1-indexed)"
    )
    
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page"
    )
    
    @property
    def offset(self) -> int:
        """Calculate offset for SQL queries."""
        return (self.page - 1) * self.page_size
    
    @property
    def limit(self) -> int:
        """Get limit for SQL queries."""
        return self.page_size
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "page": 1,
                "page_size": 20
            }
        }
    }


class DateRangeParams(BaseModel):
    """
    Date range filter parameters.
    """
    
    start_date: Optional[datetime] = Field(
        None,
        description="Start date (ISO 8601)"
    )
    
    end_date: Optional[datetime] = Field(
        None,
        description="End date (ISO 8601)"
    )
    
    @field_validator('end_date', mode='after')
    @classmethod
    def validate_date_range(cls, value: Optional[datetime], info) -> Optional[datetime]:
        """Ensure end_date is after start_date."""
        if value and 'start_date' in info.data and info.data['start_date']:
            if value < info.data['start_date']:
                raise ValueError("end_date must be after start_date")
        return value
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "start_date": "2026-04-01T00:00:00Z",
                "end_date": "2026-04-30T23:59:59Z"
            }
        }
    }


class SortParams(BaseModel):
    """
    Sorting parameters.
    """
    
    sort_by: str = Field(
        default="created_at",
        description="Field to sort by"
    )
    
    sort_order: str = Field(
        default="desc",
        description="Sort order",
        pattern="^(asc|desc)$"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "sort_by": "created_at",
                "sort_order": "desc"
            }
        }
    }


class FilterParams(BaseModel):
    """
    Generic filter parameters.
    """
    
    channel: Optional[str] = Field(
        None,
        description="Filter by channel",
        pattern="^(web|whatsapp)$"
    )
    
    language: Optional[str] = Field(
        None,
        description="Filter by language",
        pattern="^(en|fr|mandinka|wolof)$"
    )
    
    feedback: Optional[int] = Field(
        None,
        ge=-1,
        le=1,
        description="Filter by feedback (-1, 0 for none, 1)"
    )
    
    cache_hit: Optional[bool] = Field(
        None,
        description="Filter by cache hit status"
    )
    
    fallback_triggered: Optional[bool] = Field(
        None,
        description="Filter by fallback status"
    )
    
    min_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score"
    )
    
    max_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Maximum confidence score"
    )