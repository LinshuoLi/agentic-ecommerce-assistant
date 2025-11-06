"""Scraping API endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.scraper import PartSelectScraper
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["scrape"])

scraper = PartSelectScraper()


class ScrapeRequest(BaseModel):
    """Scrape request model."""
    part_numbers: Optional[List[str]] = None
    category: Optional[str] = None  # 'refrigerator' or 'dishwasher'
    limit: Optional[int] = 50


class ScrapeResponse(BaseModel):
    """Scrape response model."""
    message: str
    documents_stored: int


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_content(request: ScrapeRequest):
    """Trigger scraping of PartSelect website."""
    try:
        documents = []
        metadatas = []
        
        # Scrape by part numbers
        if request.part_numbers:
            for part_number in request.part_numbers:
                product_data = await scraper.scrape_product_page(part_number)
                if product_data:
                    # Create documents
                    if product_data.get('description'):
                        documents.append({
                            'id': f"{part_number}_desc",
                            'text': f"Part {part_number} - {product_data.get('title', '')}\n{product_data.get('description', '')}"
                        })
                        metadatas.append({
                            'source': product_data.get('url', ''),
                            'part_number': part_number,
                            'type': 'product_description'
                        })
                    
                    if product_data.get('installation_guide'):
                        documents.append({
                            'id': f"{part_number}_install",
                            'text': f"Installation Guide for Part {part_number}:\n{product_data.get('installation_guide', '')}"
                        })
                        metadatas.append({
                            'source': product_data.get('url', ''),
                            'part_number': part_number,
                            'type': 'installation_guide'
                        })
        
        # Scrape by category - NOTE: scrape_category() was removed in simplified scraper
        # This endpoint now only supports scraping by part_numbers
        if request.category:
            logger.warning(f"Category scraping not supported in simplified scraper. Requested category: {request.category}")
            # Category scraping would require scraping multiple products, which is not supported
            # Users should provide specific part_numbers instead
        
        # Return scraped data
        if documents:
            return ScrapeResponse(
                message=f"Successfully scraped {len(documents)} documents",
                documents_stored=len(documents)
            )
        else:
            return ScrapeResponse(
                message="No documents were scraped. Please check part numbers or category.",
                documents_stored=0
            )
            
    except Exception as e:
        logger.error(f"Error in scrape endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

