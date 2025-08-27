import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any
from decimal import Decimal

import whisper
import httpx
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ContractTerms(BaseModel):
    product: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    currency: str = "KES"
    delivery_location: Optional[str] = None
    delivery_deadline: Optional[str] = None
    quality_requirements: Optional[str] = None
    upfront_payment: Optional[Decimal] = None
    payment_terms: Optional[str] = None


class VoiceProcessingError(Exception):
    pass


class VoiceProcessor:
    def __init__(self):
        self.model = None
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self._initialize_model()

    def _initialize_model(self):
        try:
            model_size = settings.whisper_model_size
            logger.info(f"Loading Whisper model: {model_size}")
            self.model = whisper.load_model(model_size)
            logger.info(f"Whisper model {model_size} loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise VoiceProcessingError(f"Model initialization failed: {e}")

    async def close(self):
        await self.http_client.aclose()

    def validate_audio_file(self, file_path: str) -> bool:
        if not os.path.exists(file_path):
            return False
        
        file_size = os.path.getsize(file_path)
        if file_size > settings.max_audio_file_size:
            return False
        
        file_ext = Path(file_path).suffix.lower().lstrip('.')
        return file_ext in settings.supported_audio_formats

    async def download_audio(self, audio_url: str) -> str:
        try:
            response = await self.http_client.get(audio_url)
            response.raise_for_status()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                temp_file.write(response.content)
                return temp_file.name
        except Exception as e:
            logger.error(f"Failed to download audio: {e}")
            raise VoiceProcessingError(f"Audio download failed: {e}")

    async def transcribe_audio(self, audio_path: str) -> str:
        if not self.validate_audio_file(audio_path):
            raise VoiceProcessingError("Invalid audio file")

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                audio_path
            )
            return result["text"].strip()
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise VoiceProcessingError(f"Transcription failed: {e}")

    def _transcribe_sync(self, audio_path: str) -> Dict[str, Any]:
        return self.model.transcribe(audio_path, language="en")

    async def transcribe_from_url(self, audio_url: str) -> str:
        temp_path = None
        try:
            temp_path = await self.download_audio(audio_url)
            return await self.transcribe_audio(temp_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def extract_contract_terms(self, transcript: str) -> ContractTerms:
        terms = ContractTerms()
        text = transcript.lower()

        terms.product = self._extract_product(text)
        terms.quantity = self._extract_quantity(text)
        terms.unit = self._extract_unit(text)
        terms.unit_price = self._extract_unit_price(text)
        terms.total_amount = self._extract_total_amount(text)
        terms.currency = self._extract_currency(text)
        terms.delivery_location = self._extract_location(text)
        terms.delivery_deadline = self._extract_deadline(text)
        terms.quality_requirements = self._extract_quality(text)
        terms.upfront_payment = self._extract_upfront_payment(text)
        terms.payment_terms = self._extract_payment_terms(text)

        return terms

    def _extract_product(self, text: str) -> Optional[str]:
        patterns = [
            r"(\w+\s*)?(?:bags?|sacks?)\s+(?:of\s+)?(\w+)",
            r"(\d+)\s+(\w+)\s+(?:bags?|sacks?)",
            r"selling\s+(\w+(?:\s+\w+)?)",
            r"(?:grade\s+\w+\s+)?(\w+)(?:\s+grain)?",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                product = match.group(2) if len(match.groups()) > 1 else match.group(1)
                if product and len(product) > 2:
                    return product.title()
        
        return None

    def _extract_quantity(self, text: str) -> Optional[str]:
        patterns = [
            r"(\d+(?:,\d{3})*)\s+(?:bags?|sacks?|units?)",
            r"(\d+(?:\.\d+)?)\s+(?:tons?|kg|kilos?)",
            r"quantity.*?(\d+(?:,\d{3})*)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).replace(',', '')
        
        return None

    def _extract_unit(self, text: str) -> Optional[str]:
        units = ["bags", "sacks", "tons", "kg", "kilos", "units", "pieces"]
        
        for unit in units:
            if unit in text or f"{unit[:-1]}" in text:
                return unit if unit.endswith('s') else f"{unit}s"
        
        return None

    def _extract_unit_price(self, text: str) -> Optional[Decimal]:
        patterns = [
            r"(?:kes|ksh)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:per\s+bag|each)",
            r"(\d+(?:,\d{3})*)\s*(?:per\s+bag|each)",
            r"price.*?(\d+(?:,\d{3})*(?:\.\d{2})?)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    price_str = match.group(1).replace(',', '')
                    return Decimal(price_str)
                except:
                    continue
        
        return None

    def _extract_total_amount(self, text: str) -> Optional[Decimal]:
        patterns = [
            r"total.*?(?:kes|ksh)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
            r"(?:kes|ksh)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*total",
            r"that'?s\s+(?:kes|ksh)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    amount_str = match.group(1).replace(',', '')
                    return Decimal(amount_str)
                except:
                    continue
        
        return None

    def _extract_currency(self, text: str) -> str:
        if "kes" in text or "ksh" in text or "shilling" in text:
            return "KES"
        elif "usd" in text or "dollar" in text:
            return "USD"
        elif "eur" in text or "euro" in text:
            return "EUR"
        
        return "KES"

    def _extract_location(self, text: str) -> Optional[str]:
        patterns = [
            r"deliver(?:y|ed)?\s+(?:to|at)\s+([^,.]+)",
            r"(?:warehouse|store|farm)\s+(?:at|in)\s+([^,.]+)",
            r"location.*?([A-Za-z\s]+(?:road|street|avenue))",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                location = match.group(1).strip()
                if len(location) > 3:
                    return location.title()
        
        return None

    def _extract_deadline(self, text: str) -> Optional[str]:
        patterns = [
            r"(?:by|before)\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?",
            r"(?:by|before)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)",
            r"deadline.*?(\w+\s+\d{1,2})",
            r"deliver.*?(\w+\s+\d{1,2})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) == 2:
                    month, day = match.groups()
                    return f"{month.title()} {day}"
                else:
                    return match.group(1).title()
        
        return None

    def _extract_quality(self, text: str) -> Optional[str]:
        patterns = [
            r"(?:grade\s+(\w+))",
            r"quality.*?([\w\s]+(?:test|standard|grade))",
            r"(?:moisture|dry|clean).*?([\w\s]{5,20})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                quality = match.group(1).strip()
                if len(quality) > 2:
                    return quality.title()
        
        return None

    def _extract_upfront_payment(self, text: str) -> Optional[Decimal]:
        patterns = [
            r"(?:upfront|advance).*?(?:kes|ksh)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
            r"(\d+)%\s+(?:upfront|advance|deposit)",
            r"pay.*?(\d+(?:,\d{3})*)\s*(?:upfront|advance)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    amount_str = match.group(1).replace(',', '')
                    amount = Decimal(amount_str)
                    
                    if "%" in match.group(0):
                        total = self._extract_total_amount(text)
                        if total:
                            return (amount / 100) * total
                    
                    return amount
                except:
                    continue
        
        return None

    def _extract_payment_terms(self, text: str) -> Optional[str]:
        patterns = [
            r"pay(?:ment)?\s+(?:within\s+)?(\d+\s+(?:days?|hours?))",
            r"(?:balance|remaining).*?(\d+\s+(?:days?|hours?))",
            r"(?:on|upon)\s+(delivery|completion|inspection)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).title()
        
        return None

    async def process_voice_to_contract(
        self, 
        audio_source: str,
        is_url: bool = True
    ) -> Dict[str, Any]:
        try:
            if is_url:
                transcript = await self.transcribe_from_url(audio_source)
            else:
                transcript = await self.transcribe_audio(audio_source)
            
            terms = self.extract_contract_terms(transcript)
            
            return {
                "transcript": transcript,
                "terms": terms.dict(),
                "processing_status": "completed",
                "word_count": len(transcript.split()),
                "confidence_score": self._calculate_confidence(terms)
            }
        except Exception as e:
            logger.error(f"Voice to contract processing failed: {e}")
            return {
                "transcript": "",
                "terms": {},
                "processing_status": "failed",
                "error": str(e)
            }

    def _calculate_confidence(self, terms: ContractTerms) -> float:
        score = 0.0
        max_score = 8.0
        
        if terms.product:
            score += 1.0
        if terms.quantity:
            score += 1.0
        if terms.unit_price or terms.total_amount:
            score += 1.5
        if terms.currency:
            score += 0.5
        if terms.delivery_location:
            score += 1.0
        if terms.delivery_deadline:
            score += 1.0
        if terms.quality_requirements:
            score += 1.0
        if terms.payment_terms or terms.upfront_payment:
            score += 1.0
        
        return min(score / max_score, 1.0)


_processor_instance = None


async def get_voice_processor() -> VoiceProcessor:
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = VoiceProcessor()
    return _processor_instance


async def close_voice_processor():
    global _processor_instance
    if _processor_instance:
        await _processor_instance.close()
        _processor_instance = None