import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


import africastalking

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


class SimpleSMSRequest(BaseModel):
    phoneNumber: str = Field(..., description="Phone number with country code +254712345678")
    message: Optional[str] = Field("Hello from VoicePact!", description="SMS message")


class FixedAfricasTalkingClient:
    """Fixed AT client using the working Flask pattern"""
    
    def __init__(self):
        # Use the working environment variable names
        from app.core.config import get_settings
        settings = get_settings()
        self.username = settings.at_username
        self.api_key = settings.get_secret_value('at_api_key')
        
        if not self.api_key:
            logger.warning("No API key found. Set AT_API_KEY environment variable.")
            self.sms_service = None
            return
            
        try:
            # Initialize exactly like the working Flask example
            africastalking.initialize(self.username, self.api_key)
            self.sms_service = africastalking.SMS
            logger.info(f"Fixed AT client initialized: {self.username}")
        except Exception as e:
            logger.error(f"Fixed AT client initialization failed: {e}")
            self.sms_service = None
    
    def send_sms_simple(self, phone_number: str, message: str = "Hello from VoicePact!") -> Dict[str, Any]:
        """Send SMS using the working Flask pattern (synchronous)"""
        if not self.sms_service:
            return {"status": "error", "message": "SMS service not available"}
            
        try:
            # Format phone number properly
            if not phone_number.startswith('+'):
                phone_number = f"+{phone_number}"
            formatted_number = '+' + ''.join(c for c in phone_number[1:] if c.isdigit())
            
            # Use exact Flask pattern with proper sender_id
            response = self.sms_service.send(
                message=message,
                recipients=[formatted_number],
            )
            
            logger.info(f"SMS sent to {formatted_number}")
            return {"status": "success", "data": response}
            
        except Exception as e:
            logger.error(f"SMS sending failed: {e}")
            return {"status": "error", "message": f"Failed to send SMS: {str(e)}", "error": str(e)}
    
    def send_sms_bulk(self, recipients: List[str], message: str) -> Dict[str, Any]:
        """Send bulk SMS using working pattern"""
        if not self.sms_service:
            return {"status": "error", "message": "SMS service not available"}
            
        try:
            # Format phone numbers
            formatted_recipients = []
            for phone in recipients:
                if not phone.startswith('+'):
                    phone = f"+{phone}"
                formatted_number = '+' + ''.join(c for c in phone[1:] if c.isdigit())
                formatted_recipients.append(formatted_number)
            
            response = self.sms_service.send(
                message=message,
                recipients=formatted_recipients,
            )
            
            logger.info(f"Bulk SMS sent to {len(formatted_recipients)} recipients")
            return {"status": "success", "data": response}
            
        except Exception as e:
            logger.error(f"Bulk SMS sending failed: {e}")
            return {"status": "error", "message": f"Failed to send bulk SMS: {str(e)}", "error": str(e)}
    
    def generate_contract_sms(self, contract_id: str, terms: Dict[str, Any]) -> str:
        """Generate contract SMS message"""
        product = terms.get('product', 'Product')
        quantity = terms.get('quantity', '')
        unit = terms.get('unit', '')
        total_amount = terms.get('total_amount', 0)
        currency = terms.get('currency', 'KES')
        
        quantity_str = f"({quantity} {unit})" if quantity and unit else ""
        
        return f"""VoicePact Contract:
ID: {contract_id}
Product: {product} {quantity_str}
Value: {currency} {total_amount:,.0f}

Reply YES-{contract_id} to confirm
Reply NO-{contract_id} to decline"""


# Global client instance
_fixed_client = None

def get_fixed_at_client() -> FixedAfricasTalkingClient:
    """Get the fixed AT client instance"""
    global _fixed_client
    if _fixed_client is None:
        _fixed_client = FixedAfricasTalkingClient()
    return _fixed_client


@router.post("/test")
async def test_sms_integration(phone_number: str = "+254733000000"):
    """Test SMS integration using fixed client"""
    try:
        message = f"VoicePact SMS Test - {datetime.now().strftime('%H:%M:%S')}"
        
        fixed_client = get_fixed_at_client()
        if not fixed_client.sms_service:
            return {
                "status": "error",
                "message": "SMS service not available. Check AT_API_KEY environment variable."
            }
        
        result = fixed_client.send_sms_simple(phone_number=phone_number, message=message)
        return result
        
    except Exception as e:
        logger.error(f"SMS test failed: {e}")
        return {"status": "error", "message": f"SMS test failed: {str(e)}"}


@router.post("/send")
async def send_sms_fixed(request: SimpleSMSRequest):
    """Send SMS using the fixed implementation"""
    try:
        client = get_fixed_at_client()
        
        if not client.sms_service:
            raise HTTPException(
                status_code=503, 
                detail="SMS service unavailable. Check AT_API_KEY."
            )
        
        result = client.send_sms_simple(
            phone_number=request.phoneNumber,
            message=request.message
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        raise HTTPException(status_code=500, detail=f"SMS send failed: {str(e)}")


@router.post("/send/bulk")
async def send_bulk_sms_fixed(request: Dict[str, Any]):
    """Send bulk SMS using fixed implementation"""
    try:
        client = get_fixed_at_client()
        
        if not client.sms_service:
            raise HTTPException(
                status_code=503, 
                detail="SMS service unavailable. Check AT_API_KEY."
            )
        
        recipients = request.get("recipients", [])
        message = request.get("message", "Hello from VoicePact!")
        
        result = client.send_sms_bulk(recipients=recipients, message=message)
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk SMS failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk SMS failed: {str(e)}")


@router.post("/send/contract")
async def send_contract_sms_fixed(request: Dict[str, Any]):
    """Send contract-related SMS using fixed implementation"""
    try:
        client = get_fixed_at_client()
        
        if not client.sms_service:
            raise HTTPException(
                status_code=503,
                detail="SMS service unavailable"
            )
        
        contract_id = request.get("contract_id", "AG-DEMO-001")
        recipients = request.get("recipients", [])
        terms = request.get("terms", {})
        
        # Generate contract message
        message = client.generate_contract_sms(contract_id, terms)
        
        result = client.send_sms_bulk(recipients=recipients, message=message)
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        
        return {
            "contract_id": contract_id,
            "recipients": recipients,
            "message": message,
            "sms_result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Contract SMS failed: {e}")
        raise HTTPException(status_code=500, detail=f"Contract SMS failed: {str(e)}")


@router.get("/status")
async def sms_service_status():
    """Check SMS service status"""
    try:
        fixed_client = get_fixed_at_client()
        
        status = {
            "service": "SMS",
            "username": fixed_client.username,
            "api_key_set": bool(fixed_client.api_key and len(fixed_client.api_key) > 10),
            "service_available": bool(fixed_client.sms_service),
            "timestamp": datetime.now().isoformat()
        }
        
        if fixed_client.sms_service:
            status["message"] = "SMS service ready"
        else:
            status["message"] = "SMS service unavailable - check API credentials"
        
        return status
        
    except Exception as e:
        return {
            "service": "SMS",
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.post("/webhook")
async def sms_webhook(request: Request):
    """Handle SMS delivery reports and responses"""
    try:
        form_data = await request.form()
        
        # Log webhook data
        webhook_data = dict(form_data)
        logger.info(f"SMS webhook received: {webhook_data}")
        
        # Basic webhook processing
        phone_number = webhook_data.get("from")
        message = webhook_data.get("text", "").upper().strip()
        
        response = {"status": "webhook_received"}
        
        # Handle contract confirmations
        if message.startswith("YES-") or message.startswith("NO-"):
            contract_id = message.split("-", 1)[1] if "-" in message else "unknown"
            action = "confirm" if message.startswith("YES-") else "reject"
            
            logger.info(f"Contract {action}: {contract_id} from {phone_number}")
            
            response.update({
                "action": action,
                "contract_id": contract_id,
                "phone_number": phone_number
            })
        
        return response
        
    except Exception as e:
        logger.error(f"SMS webhook error: {e}")
        return {"status": "webhook_error", "error": str(e)}