"""
Unit tests for Product Catalog Service and Media Dispatch in Chat & WhatsApp.
"""

import json
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.catalog.product_service import ProductCatalogService
from app.core.config import settings


@pytest.fixture
def temp_catalog_file(tmp_path):
    catalog_data = [
        {
            "id": "hikvision-ip-4k",
            "name": "Caméra IP Hikvision 4K AcuSense",
            "brand": "Hikvision",
            "category": "videosurveillance",
            "keywords": ["camera", "caméra", "hikvision", "surveillance", "4k"],
            "image_filename": "hikvision_4k.jpg",
            "caption": "Caméra IP 4K Hikvision AcuSense"
        },
        {
            "id": "unifi-6-pro",
            "name": "Point d'accès UniFi 6 Pro",
            "brand": "Ubiquiti",
            "category": "reseau",
            "keywords": ["borne", "wifi", "unifi", "ubiquiti", "u6"],
            "image_filename": "unifi_6_pro.jpg",
            "caption": "Point d'accès UniFi 6 Pro"
        }
    ]
    catalog_path = tmp_path / "products.json"
    catalog_path.write_text(json.dumps(catalog_data), encoding="utf-8")
    return str(catalog_path)


def test_product_catalog_load(temp_catalog_file):
    service = ProductCatalogService(catalog_path=temp_catalog_file)
    products = service.get_all_products()
    assert len(products) == 2
    assert products[0]["id"] == "hikvision-ip-4k"


def test_build_image_url(temp_catalog_file):
    service = ProductCatalogService(catalog_path=temp_catalog_file)
    url = service.build_image_url("hikvision_4k.jpg")
    expected = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/static/products/hikvision_4k.jpg"
    assert url == expected


def test_find_matching_products_by_brand(temp_catalog_file):
    service = ProductCatalogService(catalog_path=temp_catalog_file)
    matches = service.find_matching_products("Avez-vous des caméras de marque Hikvision ?")
    assert len(matches) >= 1
    assert matches[0]["id"] == "hikvision-ip-4k"
    assert matches[0]["image_url"].endswith("/static/products/hikvision_4k.jpg")


def test_find_matching_products_by_category_and_keywords(temp_catalog_file):
    service = ProductCatalogService(catalog_path=temp_catalog_file)
    matches = service.find_matching_products("Je voudrais installer du wifi avec une borne unifi")
    assert len(matches) >= 1
    assert matches[0]["id"] == "unifi-6-pro"
    assert matches[0]["image_url"].endswith("/static/products/unifi_6_pro.jpg")


def test_find_matching_products_no_match(temp_catalog_file):
    service = ProductCatalogService(catalog_path=temp_catalog_file)
    matches = service.find_matching_products("Quel temps fait-il à Dakar aujourd'hui ?")
    assert len(matches) == 0


def test_has_visual_intent(temp_catalog_file):
    service = ProductCatalogService(catalog_path=temp_catalog_file)
    assert service.has_visual_intent("Pouvez-vous me montrer une photo de la caméra ?") is True
    assert service.has_visual_intent("Quel est le prix ?") is False


@pytest.mark.asyncio
async def test_whatsapp_service_sends_product_images():
    """Verify that WhatsAppService iterates through response['media'] and calls send_image_message."""
    from app.services.whatsapp_service import WhatsAppService

    mock_chat_service = MagicMock()
    mock_chat_service.process_message = AsyncMock(return_value={
        "message": "Voici notre caméra Hikvision 4K.",
        "media": [
            {
                "type": "image",
                "product_id": "hikvision-ip-4k",
                "product_name": "Caméra IP Hikvision 4K",
                "url": "https://bai.sse.sn/static/products/hikvision_4k.jpg",
                "caption": "Caméra IP Hikvision 4K AcuSense"
            }
        ]
    })

    mock_session_repo = MagicMock()
    mock_session_repo.get_by_external_id = AsyncMock(return_value=None)
    service = WhatsAppService(
        chat_service=mock_chat_service,
        session_repository=mock_session_repo
    )
    service.send_text_message = AsyncMock()
    service.send_image_message = AsyncMock()
    service._input_validator = MagicMock()
    service._input_validator.detect_language = MagicMock(return_value="fr")
    service._input_validator.validate_chat_message = MagicMock(return_value=(True, "Je veux voir vos caméras Hikvision", {}))

    with patch("app.services.whatsapp_service.cache_service") as mock_cache:
        mock_cache.is_whatsapp_processed = AsyncMock(return_value=False)
        mock_cache.is_opted_out = AsyncMock(return_value=False)
        mock_cache.mark_whatsapp_processed = AsyncMock()

        from app.models.request.whatsapp import WhatsAppMessage, WhatsAppText

        fake_message = WhatsAppMessage(
            id="msg_12345",
            **{"from": "+221778126044"},
            type="text",
            text=WhatsAppText(body="Je veux voir vos caméras Hikvision"),
            timestamp="1700000000",
        )

        await service._process_incoming_message(
            message=fake_message,
            contact_name="Laurent"
        )

        # Verified that text message was sent
        service.send_text_message.assert_called_once_with(
            to_number="+221778126044",
            text="Voici notre caméra Hikvision 4K."
        )

        # Verified that image was sent with proper URL and caption
        service.send_image_message.assert_called_once_with(
            to_number="+221778126044",
            image_url="https://bai.sse.sn/static/products/hikvision_4k.jpg",
            caption="Caméra IP Hikvision 4K AcuSense"
        )


def test_product_catalog_crud_operations(temp_catalog_file):
    """Test adding, updating, and deleting products in catalog."""
    service = ProductCatalogService(catalog_path=temp_catalog_file)

    # 1. Add product
    new_prod = {
        "id": "ajax-motioncam",
        "name": "Détecteur Ajax MotionCam",
        "brand": "Ajax",
        "category": "alarme",
        "keywords": ["detecteur", "ajax", "motioncam"],
        "image_filename": "motioncam.jpg",
        "caption": "Détecteur de mouvement avec levée de doute photo"
    }
    added = service.add_product(new_prod)
    assert added["id"] == "ajax-motioncam"
    assert len(service.get_all_products()) == 3

    # 2. Duplicate ID rejection
    with pytest.raises(ValueError):
        service.add_product(new_prod)

    # 3. Update product
    updated = service.update_product("ajax-motioncam", {"name": "Détecteur Ajax MotionCam PhOD"})
    assert updated["name"] == "Détecteur Ajax MotionCam PhOD"

    # 4. Get by ID
    retrieved = service.get_product_by_id("ajax-motioncam")
    assert retrieved is not None
    assert retrieved["brand"] == "Ajax"

    # 5. Delete product
    deleted = service.delete_product("ajax-motioncam", delete_image_file=False)
    assert deleted is True
    assert service.get_product_by_id("ajax-motioncam") is None
    assert len(service.get_all_products()) == 2

