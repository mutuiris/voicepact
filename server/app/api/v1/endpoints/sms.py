import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.services.africastalking_client import get_africastalking_client, AfricasTalkingClient
from app.models.contract import Contract, ContractParty, ContractSignature, SMSLog, ContractStatus, SignatureStatus

logger = logging.getLogger(__name__)
router = APIRouter()


class SMSRequest(BaseModel):
    recipients: List[str] = Field(..., min_items=1, description="Phone numbers to send SMS to")
    message: str = Field(..., min_length=1, max_length=160, description="SMS message content")
    sender_id: Optional[str] = Field(None, description="Sender ID")


class SMSResponse(BaseModel):
    message_ids: List[str]
    recipients: List[str]
    status: str
    cost_estimate: Optional[float] = None


class ContractSMSRequest(BaseModel):
    contract_id: str
    message_type: str = Field(default="confirmation", description="Type: confirmation, payment, delivery, dispute")


class SMSConfirmationRequest(BaseModel):
    phone_number: str
    message: str
    contract_id: Optional[str] = None


class BulkSMSRequest(BaseModel):
    messages: List[Dict[str, Any]] = Field(..., min_items=1, description="List of message objects")


@router.post("/send", response_model=SMSResponse)
async def send_sms(
    request: SMSRequest,
    background_tasks: BackgroundTasks,
    at_client: AfricasTalkingClient = Depends(get_africastalking_client),
    db: AsyncSession = Depends(get_db)
):
    """Send SMS to one or more recipients"""
    try:
        response = await at_client.send_sms(
            message=request.message,
            recipients=request.recipients,
            sender_id=request.sender_id
        )
        
        # Log SMS sending
        background_tasks.add_task(
            log_sms_batch,
            db,
            request.recipients,
            request.message,
            response
        )
        
        return SMSResponse(
            message_ids=[response.get('messageId', 'unknown')],
            recipients=request.recipients,
            status="sent"
        )
        
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        raise HTTPException(status_code=500, detail=f"SMS send failed: {str(e)}")


@router.post("/send/contract", response_model=SMSResponse)
async def send_contract_sms(
    request: ContractSMSRequest,
    background_tasks: BackgroundTasks,
    at_client: AfricasTalkingClient = Depends(get_africastalking_client),
    db: AsyncSession = Depends(get_db)
):
    """Send contract-related SMS"""
    try:
        # Get contract details
        result = await db.execute(
            select(Contract).where(Contract.id == request.contract_id)
        )
        contract = result.scalar_one_or_none()
        
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        # Get contract parties
        parties_result = await db.execute(
            select(ContractParty).where(ContractParty.contract_id == request.contract_id)
        )
        parties = parties_result.scalars().all()
        
        recipients = [party.phone_number for party in parties]
        
        # Generate appropriate message based on type
        if request.message_type == "confirmation":
            message = at_client.generate_contract_sms(request.contract_id, contract.terms)
        elif request.message_type == "payment":
            message = at_client.generate_payment_sms(
                request.contract_id,
                float(contract.total_amount or 0),
                contract.currency
            )
        elif request.message_type == "delivery":
            message = at_client.generate_delivery_sms(request.contract_id)
        else:
            message = f"VoicePact Contract Update: {request.contract_id}"
        
        response = await at_client.send_sms(
            message=message,
            recipients=recipients
        )
        
        # Log SMS
        background_tasks.add_task(
            log_contract_sms,
            db,
            recipients,
            message,
            request.contract_id,
            request.message_type,
            response
        )
        
        return SMSResponse(
            message_ids=[response.get('messageId', 'unknown')],
            recipients=recipients,
            status="sent"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Contract SMS send failed: {e}")
        raise HTTPException(status_code=500, detail=f"Contract SMS send failed: {str(e)}")


@router.post("/webhook")
async def sms_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle SMS webhook (delivery reports, etc.)"""
    try:
        form_data = await request.form()
        
        message_id = form_data.get("id")
        phone_number = form_data.get("phoneNumber")
        status = form_data.get("status", "delivered")
        failure_reason = form_data.get("failureReason")
        cost = form_data.get("cost")
        
        if message_id:
            # Update SMS log
            result = await db.execute(
                select(SMSLog).where(SMSLog.message_id == message_id)
            )
            sms_log = result.scalar_one_or_none()
            
            if sms_log:
                sms_log.status = status
                sms_log.delivered_at = datetime.utcnow()
                if failure_reason:
                    sms_log.failure_reason = failure_reason
                if cost:
                    sms_log.cost = float(cost)
                
                await db.commit()
                logger.info(f"SMS status updated: {message_id} -> {status}")
        
        return {"status": "webhook_processed", "message_id": message_id}
        
    except Exception as e:
        logger.error(f"SMS webhook processing failed: {e}")
        return {"status": "webhook_error", "error": str(e)}


@router.post("/confirm")
async def process_sms_confirmation(
    request: SMSConfirmationRequest,
    db: AsyncSession = Depends(get_db)
):
    """Process SMS confirmation responses (YES-CONTRACT_ID, NO-CONTRACT_ID, etc.)"""
    try:
        message = request.message.upper().strip()
        phone_number = request.phone_number
        
        # Parse confirmation message
        if message.startswith("YES-"):
            contract_id = message.replace("YES-", "")
            action = "confirm"
        elif message.startswith("NO-"):
            contract_id = message.replace("NO-", "")
            action = "reject"
        elif message.startswith("ACCEPT-"):
            contract_id = message.replace("ACCEPT-", "")
            action = "accept_delivery"
        elif message.startswith("DISPUTE-"):
            contract_id = message.replace("DISPUTE-", "")
            action = "dispute"
        else:
            return {"status": "unknown_command", "message": "Unknown SMS command"}
        
        # Find contract
        result = await db.execute(
            select(Contract).where(Contract.id == contract_id)
        )
        contract = result.scalar_one_or_none()
        
        if not contract:
            return {"status": "contract_not_found", "contract_id": contract_id}
        
        # Process the action
        if action in ["confirm", "reject"]:
            # Handle contract confirmation/rejection
            signature_result = await db.execute(
                select(ContractSignature).where(
                    ContractSignature.contract_id == contract_id,
                    ContractSignature.signer_phone == phone_number
                )
            )
            signature = signature_result.scalar_one_or_none()
            
            if not signature:
                # Create new signature record
                signature = ContractSignature(
                    contract_id=contract_id,
                    signer_phone=phone_number,
                    signature_method="sms_confirmation"
                )
                db.add(signature)
            
            if action == "confirm":
                signature.status = SignatureStatus.SIGNED
                signature.signed_at = datetime.utcnow()
                response_message = f"Contract {contract_id} confirmed successfully"
            else:
                signature.status = SignatureStatus.REJECTED
                response_message = f"Contract {contract_id} rejected"
            
            await db.commit()
            
            # Check if all parties have signed
            all_signatures_result = await db.execute(
                select(ContractSignature).where(ContractSignature.contract_id == contract_id)
            )
            all_signatures = all_signatures_result.scalars().all()
            
            signed_count = sum(1 for sig in all_signatures if sig.status == SignatureStatus.SIGNED)
            total_parties = len(all_signatures)
            
            if signed_count == total_parties and total_parties > 0:
                contract.status = ContractStatus.CONFIRMED
                contract.confirmed_at = datetime.utcnow()
                await db.commit()
                
                logger.info(f"Contract {contract_id} fully confirmed by all parties")
            
        elif action == "accept_delivery":
            contract.status = ContractStatus.COMPLETED
            contract.completed_at = datetime.utcnow()
            await db.commit()
            response_message = f"Delivery accepted for contract {contract_id}"
            
        elif action == "dispute":
            contract.status = ContractStatus.DISPUTED
            await db.commit()
            response_message = f"Dispute raised for contract {contract_id}. Mediation will be initiated."
        
        return {
            "status": "processed",
            "action": action,
            "contract_id": contract_id,
            "response_message": response_message
        }
        
    except Exception as e:
        logger.error(f"SMS confirmation processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"SMS confirmation processing failed: {str(e)}")


@router.get("/logs")
async def get_sms_logs(
    limit: int = 50,
    offset: int = 0,
    phone_number: Optional[str] = None,
    contract_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get SMS logs with optional filtering"""
    try:
        query = select(SMSLog).order_by(SMSLog.sent_at.desc())
        
        if phone_number:
            query = query.where(SMSLog.recipient == phone_number)
        
        if contract_id:
            query = query.where(SMSLog.contract_id == contract_id)
        
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        return {
            "logs": [
                {
                    "id": log.id,
                    "recipient": log.recipient,
                    "message": log.message,
                    "status": log.status,
                    "sent_at": log.sent_at.isoformat(),
                    "delivered_at": log.delivered_at.isoformat() if log.delivered_at else None,
                    "contract_id": log.contract_id,
                    "cost": float(log.cost) if log.cost else None
                }
                for log in logs
            ],
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"SMS logs query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch SMS logs")


@router.post("/test")
async def test_sms_integration(
    phone_number: str,
    at_client: AfricasTalkingClient = Depends(get_africastalking_client)
):
    """Test SMS integration with a simple message"""
    try:
        message = f"VoicePact SMS Test - {datetime.now().strftime('%H:%M:%S')}"
        
        response = await at_client.send_sms(
            message=message,
            recipients=[phone_number]
        )
        
        return {
            "status": "success",
            "message": "Test SMS sent successfully",
            "response": response,
            "recipient": phone_number
        }
        
    except Exception as e:
        logger.error(f"SMS test failed: {e}")
        raise HTTPException(status_code=500, detail=f"SMS test failed: {str(e)}")


# Helper functions for background tasks

async def log_sms_batch(
    db: AsyncSession,
    recipients: List[str],
    message: str,
    response: Dict[str, Any]
):
    """Log SMS batch sending"""
    try:
        for recipient in recipients:
            sms_log = SMSLog(
                message_id=response.get('messageId'),
                recipient=recipient,
                message=message,
                status='sent',
                message_type='notification'
            )
            db.add(sms_log)
        
        await db.commit()
        logger.info(f"SMS batch logged: {len(recipients)} recipients")
        
    except Exception as e:
        logger.error(f"SMS batch logging failed: {e}")


async def log_contract_sms(
    db: AsyncSession,
    recipients: List[str],
    message: str,
    contract_id: str,
    message_type: str,
    response: Dict[str, Any]
):
    """Log contract-related SMS"""
    try:
        for recipient in recipients:
            sms_log = SMSLog(
                message_id=response.get('messageId'),
                recipient=recipient,
                message=message,
                status='sent',
                message_type=message_type,
                contract_id=contract_id
            )
            db.add(sms_log)
        
        await db.commit()
        logger.info(f"Contract SMS logged: {contract_id} -> {len(recipients)} recipients")
        
    except Exception as e:
        logger.error(f"Contract SMS logging failed: {e}")