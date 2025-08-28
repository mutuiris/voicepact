import logging
from typing import Dict, List, Optional
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.services.africastalking_client import get_africastalking_client, AfricasTalkingClient
from app.models.contract import Contract, Payment, PaymentStatus

logger = logging.getLogger(__name__)
router = APIRouter()


class PaymentRequest(BaseModel):
    contract_id: str
    amount: float = Field(..., gt=0)
    currency: str = Field(default="KES")
    phone_number: str
    payment_type: str = Field(default="escrow")


class PaymentResponse(BaseModel):
    payment_id: int
    transaction_id: Optional[str]
    status: str
    amount: float
    currency: str
    created_at: str


@router.post("/checkout", response_model=PaymentResponse)
async def mobile_checkout(
    request: PaymentRequest,
    at_client: AfricasTalkingClient = Depends(get_africastalking_client),
    db: AsyncSession = Depends(get_db)
):
    """Initiate mobile money checkout"""
    try:
        # Verify contract exists
        result = await db.execute(
            select(Contract).where(Contract.id == request.contract_id)
        )
        contract = result.scalar_one_or_none()
        
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        
        # Create payment record
        payment = Payment(
            contract_id=request.contract_id,
            payer_phone=request.phone_number,
            amount=Decimal(str(request.amount)),
            currency=request.currency,
            payment_type=request.payment_type,
            status=PaymentStatus.PENDING
        )
        
        db.add(payment)
        await db.commit()
        await db.refresh(payment)
        
        # Initiate AT mobile checkout
        response = await at_client.mobile_checkout(
            phone_number=request.phone_number,
            amount=request.amount,
            currency_code=request.currency,
            metadata={"contract_id": request.contract_id, "payment_id": payment.id}
        )
        
        # Update payment with transaction ID
        if response.get('transactionId'):
            payment.external_transaction_id = response['transactionId']
            await db.commit()
        
        return PaymentResponse(
            payment_id=payment.id,
            transaction_id=payment.external_transaction_id,
            status=payment.status.value,
            amount=float(payment.amount),
            currency=payment.currency,
            created_at=payment.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mobile checkout failed: {e}")
        raise HTTPException(status_code=500, detail=f"Mobile checkout failed: {str(e)}")


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    at_client: AfricasTalkingClient = Depends(get_africastalking_client),
    db: AsyncSession = Depends(get_db)
):
    """Handle payment webhook from Africa's Talking"""
    try:
        form_data = await request.form()
        
        transaction_id = form_data.get("transactionId")
        status = form_data.get("status", "failed")
        phone_number = form_data.get("phoneNumber")
        amount = form_data.get("amount")
        
        logger.info(f"Payment webhook received: {transaction_id}, {status}")
        
        if transaction_id:
            # Find payment by transaction ID
            result = await db.execute(
                select(Payment).where(Payment.external_transaction_id == transaction_id)
            )
            payment = result.scalar_one_or_none()
            
            if payment:
                # Update payment status
                if status.lower() == "success":
                    payment.status = PaymentStatus.LOCKED
                    payment.confirmed_at = datetime.utcnow()
                else:
                    payment.status = PaymentStatus.FAILED
                    payment.failure_reason = form_data.get("description", "Payment failed")
                
                await db.commit()
                logger.info(f"Payment {payment.id} updated: {payment.status.value}")
        
        return {"status": "webhook_processed", "transaction_id": transaction_id}
        
    except Exception as e:
        logger.error(f"Payment webhook processing failed: {e}")
        return {"status": "webhook_error", "error": str(e)}


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get payment by ID"""
    try:
        result = await db.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        
        return PaymentResponse(
            payment_id=payment.id,
            transaction_id=payment.external_transaction_id,
            status=payment.status.value,
            amount=float(payment.amount),
            currency=payment.currency,
            created_at=payment.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve payment")


@router.get("/contract/{contract_id}")
async def get_contract_payments(
    contract_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all payments for a contract"""
    try:
        result = await db.execute(
            select(Payment)
            .where(Payment.contract_id == contract_id)
            .order_by(Payment.created_at.desc())
        )
        payments = result.scalars().all()
        
        payment_list = [
            PaymentResponse(
                payment_id=payment.id,
                transaction_id=payment.external_transaction_id,
                status=payment.status.value,
                amount=float(payment.amount),
                currency=payment.currency,
                created_at=payment.created_at.isoformat()
            )
            for payment in payments
        ]
        
        return {"contract_id": contract_id, "payments": payment_list}
        
    except Exception as e:
        logger.error(f"Contract payments query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve contract payments")


@router.post("/test/checkout")
async def test_payment(
    phone_number: str,
    amount: float = 100.0,
    at_client: AfricasTalkingClient = Depends(get_africastalking_client)
):
    """Test payment integration"""
    try:
        response = await at_client.mobile_checkout(
            phone_number=phone_number,
            amount=amount,
            currency_code="KES",
            metadata={"test": "true"}
        )
        
        return {
            "status": "test_initiated",
            "phone_number": phone_number,
            "amount": amount,
            "response": response
        }
        
    except Exception as e:
        logger.error(f"Payment test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Payment test failed: {str(e)}")


@router.get("/wallet/balance")
async def get_wallet_balance(
    at_client: AfricasTalkingClient = Depends(get_africastalking_client)
):
    """Get Africa's Talking wallet balance"""
    try:
        response = await at_client.get_wallet_balance()
        return {"wallet_balance": response}
        
    except Exception as e:
        logger.error(f"Wallet balance query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get wallet balance")