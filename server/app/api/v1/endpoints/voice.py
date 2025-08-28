import asyncio
import logging
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.africastalking_client import get_africastalking_client, AfricasTalkingClient
from app.services.voice_processor import get_voice_processor, VoiceProcessor, ContractTerms
from app.services.contract_generator import get_contract_generator, ContractGenerator
from app.services.crypto_service import get_crypto_service, CryptoService
from app.models.contract import Contract, VoiceRecording, ContractParty, ContractStatus, PartyRole

logger = logging.getLogger(__name__)
router = APIRouter()


class VoiceConferenceRequest(BaseModel):
    parties: List[str] = Field(..., min_items=2, description="Phone numbers of contract parties")
    contract_type: str = Field(default="agricultural_supply", description="Type of contract")
    expected_duration: Optional[int] = Field(default=600, description="Expected call duration in seconds")


class VoiceConferenceResponse(BaseModel):
    conference_id: str
    recording_url: Optional[str]
    status: str
    webhook_url: Optional[str]
    parties: List[str]


class VoiceProcessingRequest(BaseModel):
    audio_url: Optional[str] = None
    parties: List[Dict[str, str]] = Field(..., min_items=2)
    contract_type: str = Field(default="agricultural_supply")


class VoiceProcessingResponse(BaseModel):
    contract_id: str
    transcript: str
    terms: Dict[str, Any]
    contract_hash: str
    contract_summary: str
    processing_status: str
    confidence_score: float
    created_at: str


class WebhookPayload(BaseModel):
    sessionId: Optional[str] = None
    phoneNumber: Optional[str] = None
    recordingUrl: Optional[str] = None
    duration: Optional[int] = None
    status: Optional[str] = None


@router.post("/conference/create", response_model=VoiceConferenceResponse)
async def create_voice_conference(
    request: VoiceConferenceRequest,
    background_tasks: BackgroundTasks,
    at_client: AfricasTalkingClient = Depends(get_africastalking_client),
    db: AsyncSession = Depends(get_db)
):
    try:
        response = await at_client.make_voice_call(
            recipients=request.parties,
            from_number=None
        )
        
        recording = VoiceRecording(
            recording_id=response.get("sessionId", "unknown"),
            participants=request.parties,
            processing_status="recording"
        )
        
        db.add(recording)
        await db.commit()
        
        webhook_url = f"/api/v1/voice/webhook"
        
        return VoiceConferenceResponse(
            conference_id=recording.recording_id,
            recording_url=response.get("recordingUrl"),
            status="active",
            webhook_url=webhook_url,
            parties=request.parties
        )
        
    except Exception as e:
        logger.error(f"Voice conference creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create voice conference: {str(e)}")


@router.post("/process", response_model=VoiceProcessingResponse)
async def process_voice_recording(
    request: VoiceProcessingRequest,
    background_tasks: BackgroundTasks,
    voice_processor: VoiceProcessor = Depends(get_voice_processor),
    contract_generator: ContractGenerator = Depends(get_contract_generator),
    crypto_service: CryptoService = Depends(get_crypto_service),
    db: AsyncSession = Depends(get_db)
):
    try:
        if not request.audio_url:
            raise HTTPException(status_code=400, detail="Audio URL is required")
        
        result = await voice_processor.process_voice_to_contract(
            audio_source=request.audio_url,
            is_url=True
        )
        
        if result["processing_status"] != "completed":
            raise HTTPException(status_code=400, detail=f"Voice processing failed: {result.get('error')}")
        
        transcript = result["transcript"]
        terms_dict = result["terms"]
        terms = ContractTerms(**terms_dict)
        
        contract_result = await contract_generator.process_voice_to_contract(
            transcript=transcript,
            terms=terms,
            parties=request.parties,
            contract_type=request.contract_type,
            generate_pdf=False
        )
        
        contract = Contract(
            id=contract_result["contract_id"],
            audio_url=request.audio_url,
            transcript=transcript,
            terms=terms_dict,
            contract_hash=contract_result["contract_hash"],
            total_amount=terms.total_amount,
            currency=terms.currency,
            delivery_location=terms.delivery_location,
            quality_requirements=terms.quality_requirements,
            status=ContractStatus.PENDING
        )
        
        db.add(contract)
        
        for party_data in request.parties:
            party = ContractParty(
                contract_id=contract.id,
                phone_number=party_data["phone"],
                role=PartyRole(party_data.get("role", "buyer")),
                name=party_data.get("name")
            )
            db.add(party)
        
        await db.commit()
        
        background_tasks.add_task(
            send_contract_confirmations,
            contract.id,
            request.parties,
            contract_result["contract_summary"]
        )
        
        return VoiceProcessingResponse(
            contract_id=contract.id,
            transcript=transcript,
            terms=terms_dict,
            contract_hash=contract.contract_hash,
            contract_summary=contract_result["contract_summary"],
            processing_status="completed",
            confidence_score=result.get("confidence_score", 0.0),
            created_at=contract.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Voice processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Voice processing failed: {str(e)}")


@router.post("/upload")
async def upload_voice_file(
    file: UploadFile = File(...),
    parties: str = None,
    contract_type: str = "agricultural_supply",
    voice_processor: VoiceProcessor = Depends(get_voice_processor),
    db: AsyncSession = Depends(get_db)
):
    try:
        if not file.filename.lower().endswith(('.wav', '.mp3', '.m4a', '.ogg')):
            raise HTTPException(status_code=400, detail="Unsupported audio format")
        
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name
        
        try:
            result = await voice_processor.process_voice_to_contract(
                audio_source=temp_path,
                is_url=False
            )
            
            return {
                "transcript": result["transcript"],
                "terms": result["terms"],
                "processing_status": result["processing_status"],
                "confidence_score": result.get("confidence_score", 0.0)
            }
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"File processing failed: {str(e)}")


@router.post("/webhook")
async def voice_webhook(
    request: Request,
    at_client: AfricasTalkingClient = Depends(get_africastalking_client),
    db: AsyncSession = Depends(get_db)
):
    try:
        body = await request.body()
        form_data = await request.form()
        
        session_id = form_data.get("sessionId")
        phone_number = form_data.get("phoneNumber")
        recording_url = form_data.get("recordingUrl")
        duration = form_data.get("duration")
        status = form_data.get("status", "completed")
        
        if session_id:
            from sqlalchemy import select
            result = await db.execute(
                select(VoiceRecording).where(VoiceRecording.recording_id == session_id)
            )
            recording = result.scalar_one_or_none()
            
            if recording:
                recording.recording_url = recording_url
                recording.duration = int(duration) if duration else None
                recording.processing_status = status
                await db.commit()
                
                logger.info(f"Updated voice recording {session_id} with status {status}")
        
        return {"status": "webhook_processed", "session_id": session_id}
        
    except Exception as e:
        logger.error(f"Voice webhook processing failed: {e}")
        return {"status": "webhook_error", "error": str(e)}


@router.get("/recordings/{recording_id}")
async def get_recording_status(
    recording_id: str,
    db: AsyncSession = Depends(get_db)
):
    try:
        from sqlalchemy import select
        result = await db.execute(
            select(VoiceRecording).where(VoiceRecording.recording_id == recording_id)
        )
        recording = result.scalar_one_or_none()
        
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        return {
            "recording_id": recording.recording_id,
            "status": recording.processing_status,
            "duration": recording.duration,
            "recording_url": recording.recording_url,
            "created_at": recording.created_at.isoformat(),
            "processed_at": recording.processed_at.isoformat() if recording.processed_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Recording status query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to query recording status")


async def send_contract_confirmations(
    contract_id: str,
    parties: List[Dict[str, str]], 
    contract_summary: str
):
    try:
        at_client = await get_africastalking_client()
        
        for party in parties:
            phone = party["phone"]
            message = f"VoicePact Contract Created:\n{contract_summary}\nReply YES-{contract_id} to confirm"
            
            await at_client.send_sms(
                message=message,
                recipients=[phone]
            )
            
        logger.info(f"Sent contract confirmations for {contract_id} to {len(parties)} parties")
        
    except Exception as e:
        logger.error(f"Failed to send contract confirmations: {e}")