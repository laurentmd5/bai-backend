#!/usr/bin/env python3
"""
Initialize Qdrant collection with NPP documents.
Run once during first deployment.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.rag_service import RAGService
from app.core.logging import get_logger

logger = get_logger(__name__)


async def main():
    logger.info("Starting Qdrant initialization...")
    
    rag = RAGService()
    await rag.initialize()
    
    # Document : Digital Transformation
    digital_content = """
ICT & DIGITAL TRANSFORMATION
Connecting Every Gambian to the Future

ACHIEVEMENTS (2022-2026)
Digital transformation became a central tool for better government, stronger business, and wider opportunity.

1. Modern Digital Governance and National ICT Policy Reform
The NPP administration delivered the most comprehensive digital policy transformation in national history - introducing more than 25 major ICT strategies, policies and legal frameworks.

2. Expanding Connectivity, Infrastructure & Sector Restructuring
- Increased mobile penetration to 113%, one of the highest in the region.
- Initiation of the GAMTEL PPP Backbone Upgrade from 40G to 800G - capable of serving 400,000 additional users.
- Launch of the US$25 million Second Submarine Cable Project under WARDIP to enhance redundancy and reliability.
- Completion of 100% digital addressing in Banjul and Kanifing, with more than 194,000 properties mapped in West Coast Region.
- Full nationalization of the National Switch, strengthening financial inclusion and lowering transaction costs.

3. E-Government & Citizen-Centered Service Delivery
- Digitization of tax administration through the new Integrated Tax Administration System (ITAS).
- Integration of the MYGOV platform (births, ID, passport, licensing, business registration) ready for launch.
- Deployment of the Government Information Portal and App (gambia.gov.gm) integrating information from 20 ministries.
- Digital systems transforming revenue administration, customs, and tax compliance through ASYCUDA World, National Single Window, digital tax stamps, and e-invoicing.

4. A Growing Digital Economy
- Establishment of the Ministry of Communication and Digital Economy (MoCDE).
- Licensing of new ISPs and fixed-line operators including NU Voice, YCELL, B-SAT, and DK Telecom.

THE WAY FORWARD (2027-2031)
1. Digital Nation Infrastructure
- Expand the national fibre backbone to all regions.
- Secure a second international submarine cable for redundancy.
- Introduce phased 5G rollout in high-demand urban zones.
- Reduce data costs and expand rural mobile broadband.
- Provide public Wi-Fi in schools, hospitals, government offices and community centres.
- Complete 50% national digital addressing rollout by 2031.

2. Digitalizing Government Services (MYGOV+)
- Fully digitalize 80% of high-volume government services by 2031.
- Launch the National Digital ID as the main identity verification platform.
- Digitize Health (national health information system, digital medical records, telemedicine).
- Digitize Education (nationwide e-learning and digital school management systems).

3. Innovation, Entrepreneurship & Youth Empowerment
- Establish a National ICT Tech Park and three Regional Innovation Hubs.
- Integrate coding, robotics and digital literacy across the national curriculum.
- Expand large-scale digital skills programmes for youth, civil servants and citizens.
"""

    # Split into chunks by paragraphs
    chunks = [c.strip() for c in digital_content.split("\n\n") if c.strip() and len(c.strip()) > 30]
    
    indexed = await rag.index_document_chunks(
        chunks=chunks,
        document_name="Digital.docx",
        section="ICT & Digital Transformation",
        language="en",
    )
    
    logger.info(f"Indexed {indexed} chunks from Digital.docx")
    
    # Verify collection
    stats = await rag.get_collection_stats()
    logger.info(f"Collection stats: {stats}")
    logger.info("Qdrant initialization complete!")


if __name__ == "__main__":
    asyncio.run(main())