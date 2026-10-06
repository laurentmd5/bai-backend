"""
Admin product and catalog management endpoints for Company Bot.
Allows creating, listing, updating, and deleting products with their image media assets.
"""

import os
import re
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Form,
    Query,
)

from app.api.dependencies.auth import get_current_admin
from app.core.logging import get_logger
from app.services.catalog.product_service import product_catalog_service

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["Admin Product Catalog"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
PRODUCTS_IMAGES_DIR = os.path.join("data", "images", "products")


def _sanitize_slug(text: str) -> str:
    """Sanitize string to produce a valid URL/file-safe ID slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


async def _save_uploaded_image(file: UploadFile, custom_name: Optional[str] = None) -> str:
    """
    Validate, sanitize and save an uploaded image file to data/images/products/.
    Returns the saved filename.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image file has no name",
        )

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extension '{ext}' not allowed. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}",
        )

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content-type '{file.content_type}' not allowed. Must be JPEG, PNG, or WEBP.",
        )

    # Read and check size
    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too large ({len(content)} bytes). Max size is 5MB.",
        )

    # Build unique or custom safe filename
    base_name = custom_name or Path(file.filename).stem
    safe_base = _sanitize_slug(base_name) or str(uuid.uuid4())[:8]
    filename = f"{safe_base}_{uuid.uuid4().hex[:6]}{ext}"

    os.makedirs(PRODUCTS_IMAGES_DIR, exist_ok=True)
    target_path = os.path.join(PRODUCTS_IMAGES_DIR, filename)

    with open(target_path, "wb") as f:
        f.write(content)

    logger.info("product_image_uploaded_and_saved", filename=filename, size=len(content))
    return filename


@router.get("", response_model=List[Dict[str, Any]])
async def list_products(
    search: Optional[str] = Query(None, description="Search keyword in name, brand, or keywords"),
    category: Optional[str] = Query(None, description="Filter by category"),
    current_admin: dict = Depends(get_current_admin),
) -> List[Dict[str, Any]]:
    """List all products in the catalog."""
    products = product_catalog_service.get_all_products()

    if category:
        products = [p for p in products if p.get("category", "").lower() == category.lower()]

    if search:
        search_lower = search.lower()
        filtered = []
        for p in products:
            name = p.get("name", "").lower()
            brand = p.get("brand", "").lower()
            keywords = " ".join(p.get("keywords", [])).lower()
            if search_lower in name or search_lower in brand or search_lower in keywords:
                filtered.append(p)
        products = filtered

    return products


@router.get("/{product_id}")
async def get_product(
    product_id: str,
    current_admin: dict = Depends(get_current_admin),
) -> Dict[str, Any]:
    """Retrieve details for a single product."""
    product = product_catalog_service.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(
    name: str = Form(...),
    brand: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    keywords: str = Form(...),  # Comma-separated or space-separated
    caption: Optional[str] = Form(None),
    product_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_admin: dict = Depends(get_current_admin),
) -> Dict[str, Any]:
    """
    Create a new product with its image and metadata.
    """
    # Generate slug ID if not provided
    pid = _sanitize_slug(product_id) if product_id else _sanitize_slug(f"{brand}-{name}")
    if not pid:
        pid = f"prod-{uuid.uuid4().hex[:8]}"

    existing = product_catalog_service.get_product_by_id(pid)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A product with ID '{pid}' already exists.",
        )

    # Process image if uploaded
    image_filename = None
    if image and image.filename:
        image_filename = await _save_uploaded_image(image, custom_name=pid)

    # Clean keywords list
    kw_list = [k.strip().lower() for k in re.split(r"[,;]+", keywords) if k.strip()]

    # Default caption if not provided
    product_caption = caption.strip() if caption else f"📸 {name} — {brand}"

    product_data = {
        "id": pid,
        "name": name.strip(),
        "brand": brand.strip(),
        "category": category.strip().lower(),
        "description": description.strip(),
        "keywords": kw_list,
        "image_filename": image_filename,
        "caption": product_caption,
    }

    try:
        created = product_catalog_service.add_product(product_data)
        logger.info("product_created", product_id=pid, admin=current_admin.get("email"))
        return created
    except Exception as e:
        logger.error("failed_to_create_product", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{product_id}")
async def update_product(
    product_id: str,
    name: Optional[str] = Form(None),
    brand: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None),
    caption: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_admin: dict = Depends(get_current_admin),
) -> Dict[str, Any]:
    """
    Update an existing product's metadata and/or image.
    """
    existing = product_catalog_service.get_product_by_id(product_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    updated_fields: Dict[str, Any] = {}
    if name is not None:
        updated_fields["name"] = name.strip()
    if brand is not None:
        updated_fields["brand"] = brand.strip()
    if category is not None:
        updated_fields["category"] = category.strip().lower()
    if description is not None:
        updated_fields["description"] = description.strip()
    if caption is not None:
        updated_fields["caption"] = caption.strip()
    if keywords is not None:
        updated_fields["keywords"] = [k.strip().lower() for k in re.split(r"[,;]+", keywords) if k.strip()]

    # If new image uploaded
    if image and image.filename:
        new_filename = await _save_uploaded_image(image, custom_name=product_id)
        # Delete old image if it existed
        old_image = existing.get("image_filename")
        if old_image:
            old_path = os.path.join(PRODUCTS_IMAGES_DIR, old_image)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception as e:
                    logger.warning("failed_to_remove_replaced_image", error=str(e))
        updated_fields["image_filename"] = new_filename

    updated = product_catalog_service.update_product(product_id, updated_fields)
    logger.info("product_updated", product_id=product_id, admin=current_admin.get("email"))
    return updated


@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_admin: dict = Depends(get_current_admin),
) -> Dict[str, Any]:
    """
    Delete a product and remove its corresponding image file.
    """
    success = product_catalog_service.delete_product(product_id, delete_image_file=True)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    logger.info("product_deleted", product_id=product_id, admin=current_admin.get("email"))
    return {"status": "success", "message": f"Product '{product_id}' and image deleted successfully"}
