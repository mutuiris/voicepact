import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.services.contract_generator import get_contract_generator, ContractGenerator
from app.services.crypto_service import get_crypto_service, CryptoService
from app.services.africastalking_client import get_africastalking_client, AfricasTalkingClient
from app.models.contract import (
    Contract, ContractParty, ContractSignature, ContractStatus, 
    PartyRole, SignatureStatus, ContractType
)

logger = logging.getLogger(__name__)
router = APIRouter()


class ContractCreateRequest(BaseModel):
    transcript: str = Field(..., description="Voice transcript or manual contract description")
    parties: List[Dict[str, str]] = Field(..., min_items=2, description="Contract parties")
    contract_type: str = Field(default="agricultural_supply", description="Type of contract")
    terms: Dict[str, Any] = Field(default={}, description="Contract terms")


class ContractResponse(BaseModel):
    contract_id: str
    status: str
    created_at: str
    expires_at: Optional[str]
    total_amount: Optional[float]
    currency: str
    parties: List[Dict[str, Any]]
    contract_hash: str


class ContractUpdateRequest(BaseModel):
    status: Optional[str] = None
    terms: Optional[Dict[str, Any]] = None


class ManualContractRequest(BaseModel):
    """Create contract without voice processing"""
    product: str = Field(..., description="Product or service")
    quantity: Optional[str] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_amount: float = Field(..., description="Total contract amount")
    currency: str = Field(default="KES")
    delivery_location: Optional[str] = None
    delivery_deadline: Optional[str] = None
    quality_requirements: Optional[str] = None
    parties: List[Dict[str, str]] = Field(..., min_items=2)
    contract_type: str = Field(default="agricultural_supply")


@router.post("/create", response_model=ContractResponse)
async def create_contract(
    request: ContractCreateRequest,
    background_tasks: BackgroundTasks,
    contract_generator: ContractGenerator = Depends(get_contract_generator),
    crypto_service: CryptoService = Depends(get_crypto_service),
    at_client: AfricasTalkingClient = Depends(get_africastalking_client),
    db: AsyncSession = Depends(get_db)
):
    """Create a new contract from transcript and terms"""
    try:
        # Generate contract hash
        contract_hash = crypto_service.generate_contract_hash(
            f"{request.transcript}:{str(sorted(request.terms.items()))}"
        )
        
        # Generate contract ID
        contract_id = contract_generator.generate_contract_id(request.contract_type)
        
        # Create contract
        contract = Contract(
            id=contract_id,
            transcript=request.transcript,
            contract_type=ContractType(request.contract_type),
            terms=request.terms,
            contract_hash=contract_hash,
            total_amount=request.terms.get('total_amount'),
            currency=request.terms.get('currency', 'KES'),
            delivery_location=request.terms.get('delivery_location'),
            quality_requirements=request.terms.get('quality_requirements'),
            status=ContractStatus.PENDING
        )
        
        db.add(contract)
        
        # Add parties
        for party_data in request.parties:
            party = ContractParty(
                contract_id=contract_id,
                phone_number=party_data.get('phone'),
                role=PartyRole(party_data.get('role', 'buyer')),
                name=party_data.get('name')
            )
            db.add(party)
            
            # Create signature record
            signature = ContractSignature(
                contract_id=contract_id,
                signer_phone=party_data.get('phone'),
                signature_method="sms_confirmation",
                status=SignatureStatus.PENDING
            )
            db.add(signature)
        
        await db.commit()
        
        # Send SMS confirmations
        background_tasks.add_task(
            send_contract_confirmations,
            contract_id,
            request.parties,
            contract.terms,
            at_client
        )
        
        return await get_contract_response(contract, db)
        
    except Exception as e:
        logger.error(f"Contract creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Contract creation failed: {str(e)}")


@router.post("/create/manual", response_model=ContractResponse)
async def create_manual_contract(
    request: ManualContractRequest,
    background_tasks: BackgroundTasks,
    contract_generator: ContractGenerator = Depends(get_contract_generator),
    crypto_service: CryptoService = Depends(get_crypto_service),
    at_client: AfricasTalkingClient = Depends(get_africastalking_client),
    db: AsyncSession = Depends(get_db)
):
    """Create contract manually without voice processing"""
    try:
        # Build terms from request
        terms = {
            "product": request.product,
            "quantity": request.quantity,
            "unit": request.unit,
            "unit_price": request.unit_price,
            "total_amount": request.total_amount,
            "currency": request.currency,
            "delivery_location": request.delivery_location,
            "delivery_deadline": request.delivery_deadline,
            "quality_requirements": request.quality_requirements
        }
        
        # Create transcript
        transcript = f"Manual contract creation: {request.product}"
        if request.quantity and request.unit:
            transcript += f" - {request.quantity} {request.unit}"
        transcript += f" for {request.currency} {request.total_amount}"
        
        # Use the main create_contract logic
        create_request = ContractCreateRequest(
            transcript=transcript,
            parties=request.parties,
            contract_type=request.contract_type,
            terms=terms
        )
        
        return await create_contract(
            create_request,
            background_tasks,
            contract_generator,
            crypto_service,
            at_client,
            db
        )
        
    except Exception as e:
        logger.error(f"Manual contract creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Manual contract creation failed: {str(e)}")


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get contract by ID"""
    try:
        result = await db.execute(
            select(Contract).where(Contract.id == contract_id)
        )
        contract = result.scalar_one_or_none()
        
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        return await get_contract_response(contract, db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Contract retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve contract")


@router.get("/")
async def list_contracts(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    phone_number: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List contracts with optional filtering"""
    try:
        query = select(Contract).order_by(Contract.created_at.desc())
        
        if status:
            query = query.where(Contract.status == ContractStatus(status))
        
        if phone_number:
            # Filter by party phone number
            query = query.join(ContractParty).where(ContractParty.phone_number == phone_number)
        
        query = query.limit(limit).offset(offset)
        result = await db.execute(query)
        contracts = result.scalars().all()
        
        contract_list = []
        for contract in contracts:
            contract_response = await get_contract_response(contract, db)
            contract_list.append(contract_response)
        
        return {
            "contracts": contract_list,
            "limit": limit,
            "offset": offset,
            "total": len(contract_list)
        }
        
    except Exception as e:
        logger.error(f"Contract listing failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to list contracts")


@router.put("/{contract_id}")
async def update_contract(
    contract_id: str,
    request: ContractUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update contract status or terms"""
    try:
        result = await db.execute(
            select(Contract).where(Contract.id == contract_id)
        )
        contract = result.scalar_one_or_none()
        
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        if request.status:
            contract.status = ContractStatus(request.status)
            if request.status == "confirmed":
                contract.confirmed_at = datetime.utcnow()
            elif request.status == "completed":
                contract.completed_at = datetime.utcnow()
        
        if request.terms:
            contract.terms.update(request.terms)
        
        await db.commit()
        
        return {"status": "updated", "contract_id": contract_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Contract update failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to update contract")


@router.post("/{contract_id}/confirm")
async def confirm_contract(
    contract_id: str,
    phone_number: str,
    db: AsyncSession = Depends(get_db)
):
    """Confirm contract by phone number"""
    try:
        # Find signature record
        result = await db.execute(
            select(ContractSignature).where(
                and_(
                    ContractSignature.contract_id == contract_id,
                    ContractSignature.signer_phone == phone_number
                )
            )
        )
        signature = result.scalar_one_or_none()
        
        if not signature:
            raise HTTPException(status_code=404, detail="Signature record not found")
        
        # Update signature
        signature.status = SignatureStatus.SIGNED
        signature.signed_at = datetime.utcnow()
        
        # Check if all parties have signed
        all_signatures_result = await db.execute(
            select(ContractSignature).where(ContractSignature.contract_id == contract_id)
        )
        all_signatures = all_signatures_result.scalars().all()
        
        signed_count = sum(1 for sig in all_signatures if sig.status == SignatureStatus.SIGNED)
        
        if signed_count == len(all_signatures):
            # Update contract status
            contract_result = await db.execute(
                select(Contract).where(Contract.id == contract_id)
            )
            contract = contract_result.scalar_one()
            contract.status = ContractStatus.CONFIRMED
            contract.confirmed_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "status": "confirmed",
            "contract_id": contract_id,
            "signed_by": phone_number,
            "all_signed": signed_count == len(all_signatures)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Contract confirmation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to confirm contract")


@router.get("/{contract_id}/status")
async def get_contract_status(
    contract_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get contract status and signature progress"""
    try:
        # Get contract
        contract_result = await db.execute(
            select(Contract).where(Contract.id == contract_id)
        )
        contract = contract_result.scalar_one_or_none()
        
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        # Get signatures
        signatures_result = await db.execute(
            select(ContractSignature).where(ContractSignature.contract_id == contract_id)
        )
        signatures = signatures_result.scalars().all()
        
        signature_status = [
            {
                "phone_number": sig.signer_phone,
                "status": sig.status.value,
                "signed_at": sig.signed_at.isoformat() if sig.signed_at else None
            }
            for sig in signatures
        ]
        
        return {
            "contract_id": contract_id,
            "status": contract.status.value,
            "created_at": contract.created_at.isoformat(),
            "confirmed_at": contract.confirmed_at.isoformat() if contract.confirmed_at else None,
            "signatures": signature_status,
            "progress": {
                "signed": sum(1 for sig in signatures if sig.status == SignatureStatus.SIGNED),
                "total": len(signatures),
                "complete": contract.status in [ContractStatus.CONFIRMED, ContractStatus.ACTIVE, ContractStatus.COMPLETED]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Contract status query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get contract status")


# Helper functions

async def get_contract_response(contract: Contract, db: AsyncSession) -> ContractResponse:
    """Convert contract model to response format"""
    # Get parties
    parties_result = await db.execute(
        select(ContractParty).where(ContractParty.contract_id == contract.id)
    )
    parties = parties_result.scalars().all()
    
    parties_data = [
        {
            "phone_number": party.phone_number,
            "role": party.role.value,
            "name": party.name
        }
        for party in parties
    ]
    
    return ContractResponse(
        contract_id=contract.id,
        status=contract.status.value,
        created_at=contract.created_at.isoformat(),
        expires_at=contract.expires_at.isoformat() if contract.expires_at else None,
        total_amount=float(contract.total_amount) if contract.total_amount else None,
        currency=contract.currency,
        parties=parties_data,
        contract_hash=contract.contract_hash
    )


async def send_contract_confirmations(
    contract_id: str,
    parties: List[Dict[str, str]],
    terms: Dict[str, Any],
    at_client: AfricasTalkingClient
):
    """Send SMS confirmations to all parties"""
    try:
        message = at_client.generate_contract_sms(contract_id, terms)
        recipients = [party["phone"] for party in parties]
        
        await at_client.send_sms(
            message=message,
            recipients=recipients
        )
        
        logger.info(f"Contract confirmations sent for {contract_id}")
        
    except Exception as e:
        logger.error(f"Failed to send contract confirmations: {e}")