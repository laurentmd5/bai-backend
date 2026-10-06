"""
Product Catalog Service.
Loads structured product data and matches user queries to products with their media assets.
"""

import json
import os
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ProductCatalogService:
    """Service responsible for loading product catalog and finding relevant products/images."""

    DEFAULT_CATALOG_PATH = os.path.join("data", "products_catalog.json")

    # Intent keywords suggesting the user wants to see visual representations of products
    VISUAL_INTENT_KEYWORDS = {
        "photo", "photos", "image", "images", "voir", "regarder", "montre", "montrer",
        "catalogue", "modele", "modèle", "modèles", "aspect", "visuel", "a quoi ressemble",
        "à quoi ressemble", "brochure", "fiche", "proposez", "proposer", "quels sont vos"
    }

    def __init__(self, catalog_path: Optional[str] = None):
        self.catalog_path = catalog_path or self.DEFAULT_CATALOG_PATH
        self._products: List[Dict[str, Any]] = []
        self._load_catalog()

    def _load_catalog(self) -> None:
        """Load catalog from JSON file."""
        if not os.path.exists(self.catalog_path):
            logger.warning("product_catalog_file_not_found", path=self.catalog_path)
            self._products = []
            return

        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                self._products = json.load(f)
            logger.info("product_catalog_loaded", total_products=len(self._products))
        except Exception as e:
            logger.error("failed_to_load_product_catalog", error=str(e), path=self.catalog_path)
            self._products = []

    def reload(self) -> None:
        """Hot-reload catalog from disk."""
        self._load_catalog()

    def save_catalog(self) -> None:
        """Save current products to JSON file."""
        os.makedirs(os.path.dirname(self.catalog_path), exist_ok=True)
        with open(self.catalog_path, "w", encoding="utf-8") as f:
            json.dump(self._products, f, ensure_ascii=False, indent=2)
        logger.info("product_catalog_saved", total_products=len(self._products))

    def get_all_products(self) -> List[Dict[str, Any]]:
        """Return all catalog products with enriched image_url."""
        result = []
        for p in self._products:
            prod_copy = dict(p)
            image_filename = p.get("image_filename")
            if image_filename:
                prod_copy["image_url"] = self.build_image_url(image_filename)
            result.append(prod_copy)
        return result

    def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Find a single product by ID."""
        for p in self._products:
            if p.get("id") == product_id:
                prod_copy = dict(p)
                image_filename = p.get("image_filename")
                if image_filename:
                    prod_copy["image_url"] = self.build_image_url(image_filename)
                return prod_copy
        return None

    def add_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new product to the catalog."""
        product_id = product_data.get("id")
        if any(p.get("id") == product_id for p in self._products):
            raise ValueError(f"Product with ID '{product_id}' already exists")
        
        self._products.append(product_data)
        self.save_catalog()
        return self.get_product_by_id(product_id)

    def update_product(self, product_id: str, updated_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing product."""
        for idx, p in enumerate(self._products):
            if p.get("id") == product_id:
                old_filename = p.get("image_filename")
                # Merge fields
                self._products[idx].update(updated_data)
                # Keep original ID intact
                self._products[idx]["id"] = product_id
                self.save_catalog()

                # If image filename changed and old one exists, optionally caller can clean it
                return self.get_product_by_id(product_id)
        return None

    def delete_product(self, product_id: str, delete_image_file: bool = True) -> bool:
        """Delete product from catalog and optionally remove its image file."""
        target_idx = None
        target_image = None
        for idx, p in enumerate(self._products):
            if p.get("id") == product_id:
                target_idx = idx
                target_image = p.get("image_filename")
                break

        if target_idx is None:
            return False

        self._products.pop(target_idx)
        self.save_catalog()

        # Delete image file from disk
        if delete_image_file and target_image:
            image_path = os.path.join("data", "images", "products", target_image)
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.info("product_image_file_deleted", filename=target_image)
                except Exception as e:
                    logger.warning("failed_to_delete_product_image_file", filename=target_image, error=str(e))

        return True

    def build_image_url(self, image_filename: str) -> str:
        """
        Build public URL for a product image.
        Example: https://bai.sse.sn/static/products/hikvision_ip_4k_acusense.jpg
        """
        base = settings.PUBLIC_BASE_URL.rstrip("/")
        return f"{base}/static/products/{image_filename}"

    def has_visual_intent(self, query: str) -> bool:
        """
        Check if the query expresses an explicit or implicit desire to see products.
        e.g., 'Avez-vous des photos de vos caméras ?', 'Montre-moi les caméras Hikvision'.
        """
        tokens = set(re.findall(r"\b\w+\b", query.lower()))
        return bool(tokens.intersection(self.VISUAL_INTENT_KEYWORDS))

    def find_matching_products(
        self,
        query: str,
        max_results: int = 2,
        require_visual_intent: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Find matching products from query based on brand, category, and keywords.
        Returns a list of product dicts enriched with full public image URLs.
        
        Args:
            query: The user query string.
            max_results: Maximum number of products to return (default 2 to avoid flooding).
            require_visual_intent: If True, only returns images if user asked to see/view/show.
        """
        if not self._products:
            return []

        query_clean = query.lower()
        query_words = set(re.findall(r"\b\w+\b", query_clean))

        if require_visual_intent and not self.has_visual_intent(query):
            return []

        scored_products = []

        for p in self._products:
            score = 0
            brand = p.get("brand", "").lower()
            name = p.get("name", "").lower()
            category = p.get("category", "").lower()
            keywords = [kw.lower() for kw in p.get("keywords", [])]

            # Strong match: Brand explicitly mentioned (e.g. "Hikvision", "UniFi", "Ajax")
            if brand and brand in query_clean:
                score += 5

            # Name tokens match
            for name_token in re.findall(r"\b\w+\b", name):
                if len(name_token) > 3 and name_token in query_words:
                    score += 2

            # Category match
            if category and category in query_clean:
                score += 2

            # Keywords match
            for kw in keywords:
                if " " in kw:
                    if kw in query_clean:
                        score += 3
                else:
                    if kw in query_words:
                        score += 1.5

            if score >= 3:  # Minimum relevance score to avoid false positives
                scored_products.append((score, p))

        # Sort by relevance descending
        scored_products.sort(key=lambda x: x[0], reverse=True)

        matched = []
        for score, prod in scored_products[:max_results]:
            prod_copy = dict(prod)
            image_filename = prod.get("image_filename")
            if image_filename:
                prod_copy["image_url"] = self.build_image_url(image_filename)
            matched.append(prod_copy)

        return matched


# Global singleton instance
product_catalog_service = ProductCatalogService()
