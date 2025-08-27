import hashlib
import logging
import secrets
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fpdf import FPDF
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.voice_processor import ContractTerms

logger = logging.getLogger(__name__)
settings = get_settings()


class ContractData(BaseModel):
    contract_id: str
    transcript: str
    terms: Dict[str, Any]
    parties: List[Dict[str, str]]
    contract_hash: str
    created_at: datetime
    expires_at: Optional[datetime] = None


class ContractGenerationError(Exception):
    pass


class ContractGenerator:
    def __init__(self):
        self.contract_templates = {
            "agricultural_supply": self._agricultural_template,
            "service_agreement": self._service_template,
            "goods_purchase": self._goods_template,
        }

    # Generate unique contract ID
    def generate_contract_id(self, contract_type: str = "general") -> str:
        timestamp = datetime.utcnow().strftime("%y%m%d")
        type_prefix = {
            "agricultural_supply": "AG",
            "service_agreement": "SV", 
            "goods_purchase": "GP",
            "logistics": "LG"
        }.get(contract_type, "VC")
        
        random_suffix = secrets.token_hex(3).upper()
        return f"{type_prefix}-{timestamp}-{random_suffix}"

    # Generate contract hash
    def generate_contract_hash(self, transcript: str, terms: Dict[str, Any]) -> str:
        content = f"{transcript}:{str(sorted(terms.items()))}"
        
        if settings.contract_hash_algorithm == "blake2b":
            return hashlib.blake2b(content.encode()).hexdigest()
        else:
            return hashlib.sha256(content.encode()).hexdigest()

    def create_contract(
        self,
        transcript: str,
        terms: ContractTerms,
        parties: List[Dict[str, str]],
        contract_type: str = "agricultural_supply"
    ) -> ContractData:
        
        contract_id = self.generate_contract_id(contract_type)
        terms_dict = terms.dict()
        contract_hash = self.generate_contract_hash(transcript, terms_dict)
        
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(seconds=settings.contract_confirmation_timeout)
        
        return ContractData(
            contract_id=contract_id,
            transcript=transcript,
            terms=terms_dict,
            parties=parties,
            contract_hash=contract_hash,
            created_at=created_at,
            expires_at=expires_at
        )

    def generate_contract_text(
        self,
        contract_data: ContractData,
        contract_type: str = "agricultural_supply"
    ) -> str:
        
        template_func = self.contract_templates.get(
            contract_type, 
            self._agricultural_template
        )
        
        return template_func(contract_data)

    # This is for agricultural supply contracts
    def _agricultural_template(self, contract_data: ContractData) -> str:
        terms = contract_data.terms
        parties = contract_data.parties
        
        buyer = next((p for p in parties if p.get("role") == "buyer"), {})
        seller = next((p for p in parties if p.get("role") == "seller"), {})
        
        buyer_name = buyer.get("name", buyer.get("phone", "Buyer"))
        seller_name = seller.get("name", seller.get("phone", "Seller"))
        
        product = terms.get("product", "Agricultural Product")
        quantity = terms.get("quantity", "")
        unit = terms.get("unit", "units")
        unit_price = terms.get("unit_price", 0)
        total_amount = terms.get("total_amount", 0)
        currency = terms.get("currency", "KES")
        
        delivery_location = terms.get("delivery_location", "To be determined")
        delivery_deadline = terms.get("delivery_deadline", "To be agreed")
        quality_requirements = terms.get("quality_requirements", "As per industry standards")
        upfront_payment = terms.get("upfront_payment", 0)
        payment_terms = terms.get("payment_terms", "Upon delivery")
        
        contract_text = f"""
AGRICULTURAL SUPPLY CONTRACT

Contract ID: {contract_data.contract_id}
Date: {contract_data.created_at.strftime('%B %d, %Y')}

PARTIES:
Seller: {seller_name}
Phone: {seller.get('phone', 'N/A')}

Buyer: {buyer_name}
Phone: {buyer.get('phone', 'N/A')}

PRODUCT DETAILS:
Product: {product}
Quantity: {quantity} {unit}
Unit Price: {currency} {unit_price:,.2f} per {unit.rstrip('s') if unit.endswith('s') else unit}
Total Value: {currency} {total_amount:,.2f}

DELIVERY TERMS:
Location: {delivery_location}
Deadline: {delivery_deadline}
Quality: {quality_requirements}

PAYMENT TERMS:
Total Amount: {currency} {total_amount:,.2f}
Upfront Payment: {currency} {upfront_payment:,.2f}
Balance: {currency} {(total_amount - upfront_payment):,.2f}
Payment Schedule: {payment_terms}

TERMS AND CONDITIONS:
1. The seller agrees to deliver the specified product in the agreed quantity and quality.
2. The buyer agrees to make payment according to the schedule outlined above.
3. Quality inspection will be conducted upon delivery.
4. Any disputes will be resolved through mediation.
5. This contract is legally binding upon confirmation by both parties.

CONTRACT INTEGRITY:
Hash: {contract_data.contract_hash}
Valid Until: {contract_data.expires_at.strftime('%B %d, %Y at %I:%M %p') if contract_data.expires_at else 'N/A'}

VOICE RECORD:
This contract is based on voice agreement recorded on {contract_data.created_at.strftime('%B %d, %Y')}.
Transcript available upon request.

_____________________     _____________________
Seller Signature          Buyer Signature

Date: ___________          Date: ___________
        """.strip()
        
        return contract_text

    def _service_template(self, contract_data: ContractData) -> str:
        terms = contract_data.terms
        parties = contract_data.parties
        
        provider = next((p for p in parties if p.get("role") == "seller"), {})
        client = next((p for p in parties if p.get("role") == "buyer"), {})
        
        return f"""
SERVICE AGREEMENT CONTRACT

Contract ID: {contract_data.contract_id}
Date: {contract_data.created_at.strftime('%B %d, %Y')}

Service Provider: {provider.get('name', provider.get('phone', 'Provider'))}
Client: {client.get('name', client.get('phone', 'Client'))}

Service Description: {terms.get('product', 'Professional Services')}
Total Value: {terms.get('currency', 'KES')} {terms.get('total_amount', 0):,.2f}
Payment Terms: {terms.get('payment_terms', 'As agreed')}

This contract confirms the agreement for services as recorded in voice conversation.

Contract Hash: {contract_data.contract_hash}
        """.strip()

    def _goods_template(self, contract_data: ContractData) -> str:
        terms = contract_data.terms
        
        return f"""
GOODS PURCHASE CONTRACT

Contract ID: {contract_data.contract_id}
Date: {contract_data.created_at.strftime('%B %d, %Y')}

Product: {terms.get('product', 'Goods')}
Quantity: {terms.get('quantity', '')} {terms.get('unit', 'units')}
Total Value: {terms.get('currency', 'KES')} {terms.get('total_amount', 0):,.2f}

Delivery: {terms.get('delivery_location', 'TBD')}
Deadline: {terms.get('delivery_deadline', 'TBD')}

Contract Hash: {contract_data.contract_hash}
        """.strip()

    def generate_pdf(self, contract_text: str, contract_id: str) -> str:
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font('Arial', 'B', 16)
            
            pdf.cell(0, 10, 'VOICEPACT CONTRACT', ln=True, align='C')
            pdf.ln(5)
            
            pdf.set_font('Arial', '', 10)
            
            lines = contract_text.split('\n')
            for line in lines:
                if line.strip():
                    if line.isupper() and not line.startswith(' '):
                        pdf.set_font('Arial', 'B', 11)
                    elif ':' in line and not line.startswith(' '):
                        pdf.set_font('Arial', 'B', 10)
                    else:
                        pdf.set_font('Arial', '', 10)
                    
                    if len(line) > 80:
                        words = line.split(' ')
                        current_line = ""
                        for word in words:
                            if len(current_line + word) < 80:
                                current_line += word + " "
                            else:
                                pdf.cell(0, 5, current_line.strip(), ln=True)
                                current_line = word + " "
                        if current_line:
                            pdf.cell(0, 5, current_line.strip(), ln=True)
                    else:
                        pdf.cell(0, 5, line, ln=True)
                else:
                    pdf.ln(3)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_path = temp_file.name
            
            pdf.output(temp_path)
            return temp_path
            
        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            raise ContractGenerationError(f"PDF generation failed: {e}")

    # Create a summary of the contract
    def create_summary(self, contract_data: ContractData) -> str:
        terms = contract_data.terms
        parties = contract_data.parties
        
        product = terms.get("product", "Product")
        quantity = terms.get("quantity", "")
        unit = terms.get("unit", "")
        total_amount = terms.get("total_amount", 0)
        currency = terms.get("currency", "KES")
        delivery_deadline = terms.get("delivery_deadline", "")
        
        quantity_text = f"({quantity} {unit})" if quantity and unit else ""
        deadline_text = f", Due: {delivery_deadline}" if delivery_deadline else ""
        
        buyer = next((p for p in parties if p.get("role") == "buyer"), {})
        seller = next((p for p in parties if p.get("role") == "seller"), {})
        
        return (
            f"Contract {contract_data.contract_id}: "
            f"{product} {quantity_text} - "
            f"{currency} {total_amount:,.2f}{deadline_text}. "
            f"Between {seller.get('phone', 'Seller')} and {buyer.get('phone', 'Buyer')}."
        )

    # Validate contract data
    def validate_contract_data(self, contract_data: ContractData) -> List[str]:
        errors = []
        
        if not contract_data.contract_id:
            errors.append("Contract ID is required")
        
        if not contract_data.transcript:
            errors.append("Voice transcript is required")
        
        if not contract_data.parties:
            errors.append("Contract parties are required")
        
        terms = contract_data.terms
        if not terms.get("product"):
            errors.append("Product/service description is missing")
        
        if not terms.get("total_amount") and not terms.get("unit_price"):
            errors.append("Contract value is missing")
        
        return errors

    # Calculate completeness score
    def calculate_contract_completeness(self, terms: Dict[str, Any]) -> float:
        required_fields = [
            "product", "quantity", "unit", "total_amount", 
            "currency", "delivery_location", "delivery_deadline"
        ]
        
        filled_fields = sum(1 for field in required_fields if terms.get(field))
        return filled_fields / len(required_fields)

    async def process_voice_to_contract(
        self,
        transcript: str,
        terms: ContractTerms,
        parties: List[Dict[str, str]],
        contract_type: str = "agricultural_supply",
        generate_pdf: bool = True
    ) -> Dict[str, Any]:
        
        try:
            contract_data = self.create_contract(transcript, terms, parties, contract_type)
            
            validation_errors = self.validate_contract_data(contract_data)
            if validation_errors:
                logger.warning(f"Contract validation warnings: {validation_errors}")
            
            contract_text = self.generate_contract_text(contract_data, contract_type)
            contract_summary = self.create_summary(contract_data)
            completeness_score = self.calculate_contract_completeness(contract_data.terms)
            
            result = {
                "contract_id": contract_data.contract_id,
                "contract_hash": contract_data.contract_hash,
                "contract_text": contract_text,
                "contract_summary": contract_summary,
                "created_at": contract_data.created_at.isoformat(),
                "expires_at": contract_data.expires_at.isoformat() if contract_data.expires_at else None,
                "completeness_score": completeness_score,
                "validation_errors": validation_errors,
                "pdf_path": None
            }
            
            if generate_pdf:
                try:
                    pdf_path = self.generate_pdf(contract_text, contract_data.contract_id)
                    result["pdf_path"] = pdf_path
                except Exception as e:
                    logger.error(f"PDF generation failed but continuing: {e}")
                    result["pdf_error"] = str(e)
            
            return result
            
        except Exception as e:
            logger.error(f"Contract generation failed: {e}")
            raise ContractGenerationError(f"Contract generation failed: {e}")


_generator_instance = None


def get_contract_generator() -> ContractGenerator:
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ContractGenerator()
    return _generator_instance