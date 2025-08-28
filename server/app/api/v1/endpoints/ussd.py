import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.services.africastalking_client import get_africastalking_client, AfricasTalkingClient
from app.models.contract import (
    Contract, ContractParty, USSDSession, ContractStatus
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/")
async def ussd_handler(
    request: Request,
    sessionId: str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text: str = Form(""),
    at_client: AfricasTalkingClient = Depends(get_africastalking_client),
    db: AsyncSession = Depends(get_db)
):
    """Main USSD handler for VoicePact"""
    try:
        # Get or create session
        session = await get_or_create_session(sessionId, phoneNumber, db)
        
        # Parse user input
        user_input = text.split('*')[-1] if text else ""
        
        # Determine current menu based on session and input
        if not text:  # First request
            response = main_menu()
            session.current_menu = "main"
        else:
            response = await handle_menu_navigation(
                session, user_input, phoneNumber, at_client, db
            )
        
        # Update session
        session.last_input = user_input
        session.last_response = response
        session.updated_at = datetime.utcnow()
        session.expires_at = datetime.utcnow() + timedelta(minutes=5)
        
        await db.commit()
        
        return response
        
    except Exception as e:
        logger.error(f"USSD handler error: {e}")
        return at_client.build_ussd_response(
            "Service temporarily unavailable. Please try again later.",
            end_session=True
        )


async def handle_menu_navigation(
    session: USSDSession,
    user_input: str,
    phone_number: str,
    at_client: AfricasTalkingClient,
    db: AsyncSession
) -> str:
    """Handle navigation between USSD menus"""
    
    current_menu = session.current_menu
    
    if current_menu == "main":
        return await handle_main_menu(session, user_input, phone_number, at_client, db)
    elif current_menu == "contracts":
        return await handle_contracts_menu(session, user_input, phone_number, at_client, db)
    elif current_menu == "contract_detail":
        return await handle_contract_detail(session, user_input, phone_number, at_client, db)
    elif current_menu == "delivery":
        return await handle_delivery_menu(session, user_input, phone_number, at_client, db)
    else:
        # Default fallback
        session.current_menu = "main"
        return main_menu()


async def handle_main_menu(
    session: USSDSession,
    user_input: str,
    phone_number: str,
    at_client: AfricasTalkingClient,
    db: AsyncSession
) -> str:
    """Handle main menu selections"""
    
    if user_input == "1":
        # View Active Contracts
        contracts = await get_user_contracts(phone_number, db)
        if not contracts:
            return at_client.build_ussd_response(
                "No active contracts found.\n0. Back to Main Menu",
                end_session=False
            )
        
        session.current_menu = "contracts"
        session.context_data = {"contracts": [c.id for c in contracts]}
        
        menu_text = "📋 Your Contracts:\n"
        for i, contract in enumerate(contracts[:5], 1):  # Limit to 5
            status_emoji = get_status_emoji(contract.status)
            menu_text += f"{i}. {status_emoji} {contract.id[:12]}... ({contract.status.value})\n"
        
        menu_text += "\n0. Back to Main Menu"
        return at_client.build_ussd_response(menu_text, end_session=False)
    
    elif user_input == "2":
        # Quick delivery confirmation
        return at_client.build_ussd_response(
            "Quick Delivery\nEnter Contract ID:",
            end_session=False
        )
    
    elif user_input == "3":
        # Check payments
        return at_client.build_ussd_response(
            "💰 Payment Status\nFeature coming soon.\n0. Back to Main Menu",
            end_session=False
        )
    
    elif user_input == "4":
        # Help
        return at_client.build_ussd_response(
            "VoicePact Help\n"
            "Call 0700123456 for support\n"
            "SMS 'HELP' to 40404\n"
            "0. Back to Main Menu",
            end_session=False
        )
    
    elif user_input == "0":
        return at_client.build_ussd_response("Thank you for using VoicePact!", end_session=True)
    
    else:
        return at_client.build_ussd_response(
            "Invalid selection. Please try again.\n" + main_menu(),
            end_session=False
        )


async def handle_contracts_menu(
    session: USSDSession,
    user_input: str,
    phone_number: str,
    at_client: AfricasTalkingClient,
    db: AsyncSession
) -> str:
    """Handle contract list menu"""
    
    if user_input == "0":
        session.current_menu = "main"
        return main_menu()
    
    try:
        contract_index = int(user_input) - 1
        contract_ids = session.context_data.get("contracts", [])
        
        if 0 <= contract_index < len(contract_ids):
            contract_id = contract_ids[contract_index]
            
            # Get contract details
            result = await db.execute(
                select(Contract).where(Contract.id == contract_id)
            )
            contract = result.scalar_one_or_none()
            
            if contract:
                session.current_menu = "contract_detail"
                session.context_data["selected_contract"] = contract_id
                
                return contract_detail_menu(contract, at_client)
        
        return at_client.build_ussd_response(
            "Invalid selection. Please choose a valid contract number.\n0. Back to Main Menu",
            end_session=False
        )
        
    except ValueError:
        return at_client.build_ussd_response(
            "Invalid input. Please enter a number.\n0. Back to Main Menu",
            end_session=False
        )


async def handle_contract_detail(
    session: USSDSession,
    user_input: str,
    phone_number: str,
    at_client: AfricasTalkingClient,
    db: AsyncSession
) -> str:
    """Handle contract detail menu"""
    
    contract_id = session.context_data.get("selected_contract")
    
    if user_input == "1":
        # Confirm delivery
        session.current_menu = "delivery"
        return at_client.build_ussd_response(
            f"Confirm Delivery\n"
            f"Contract: {contract_id[:12]}...\n"
            f"1. Full Delivery\n"
            f"2. Partial Delivery\n"
            f"3. Report Issue\n"
            f"0. Back",
            end_session=False
        )
    
    elif user_input == "2":
        # Report issue
        return at_client.build_ussd_response(
            "Issue reported successfully.\n"
            "Support team will contact you.\n"
            "0. Back to Main Menu",
            end_session=False
        )
    
    elif user_input == "0":
        session.current_menu = "contracts"
        return at_client.build_ussd_response(
            "Back to contracts list...\n0. Main Menu",
            end_session=False
        )
    
    else:
        contract_result = await db.execute(
            select(Contract).where(Contract.id == contract_id)
        )
        contract = contract_result.scalar_one_or_none()
        
        if contract:
            return contract_detail_menu(contract, at_client)
        else:
            return at_client.build_ussd_response(
                "Contract not found.\n0. Main Menu",
                end_session=False
            )


async def handle_delivery_menu(
    session: USSDSession,
    user_input: str,
    phone_number: str,
    at_client: AfricasTalkingClient,
    db: AsyncSession
) -> str:
    """Handle delivery confirmation menu"""
    
    contract_id = session.context_data.get("selected_contract")
    
    if user_input == "1":
        # Full delivery
        await update_contract_status(contract_id, ContractStatus.COMPLETED, db)
        
        return at_client.build_ussd_response(
            "Full delivery confirmed!\n"
            "Buyer will be notified.\n"
            "Payment will be processed.",
            end_session=True
        )
    
    elif user_input == "2":
        # Partial delivery
        return at_client.build_ussd_response(
            "Partial delivery noted.\n"
            "SMS will be sent for details.\n"
            "0. Main Menu",
            end_session=False
        )
    
    elif user_input == "3":
        # Report issue
        await update_contract_status(contract_id, ContractStatus.DISPUTED, db)
        
        return at_client.build_ussd_response(
            "Issue reported.\n"
            "Contract marked for review.\n"
            "Support will contact you.",
            end_session=True
        )
    
    elif user_input == "0":
        session.current_menu = "contract_detail"
        contract_result = await db.execute(
            select(Contract).where(Contract.id == contract_id)
        )
        contract = contract_result.scalar_one_or_none()
        
        if contract:
            return contract_detail_menu(contract, at_client)
    
    return at_client.build_ussd_response(
        "Invalid selection.\n0. Back",
        end_session=False
    )


def main_menu() -> str:
    """Generate main USSD menu"""
    return """Welcome to VoicePact
1. View My Contracts
2. Confirm Delivery
3. Check Payments
4. Help & Support
0. Exit"""


def contract_detail_menu(contract: Contract, at_client: AfricasTalkingClient) -> str:
    """Generate contract detail menu"""
    status_emoji = get_status_emoji(contract.status)
    
    # Get basic contract info
    product = contract.terms.get('product', 'Product')
    amount = contract.total_amount or 0
    currency = contract.currency
    
    menu_text = f"Contract Details\n"
    menu_text += f"{status_emoji} {contract.id[:12]}...\n"
    menu_text += f"Product: {product}\n"
    menu_text += f"Value: {currency} {amount:,.0f}\n"
    menu_text += f"Status: {contract.status.value.title()}\n\n"
    
    if contract.status == ContractStatus.ACTIVE:
        menu_text += "1. Confirm Delivery\n"
    
    menu_text += "2. Report Issue\n"
    menu_text += "0. Back"
    
    return at_client.build_ussd_response(menu_text, end_session=False)


def get_status_emoji(status: ContractStatus) -> str:
    """Get emoji for contract status"""
    status_emojis = {
        ContractStatus.PENDING: "pending",
        ContractStatus.CONFIRMED: "confirmed",
        ContractStatus.ACTIVE: "active",
        ContractStatus.COMPLETED: "completed",
        ContractStatus.DISPUTED: "disputed",
        ContractStatus.CANCELLED: "cancelled",
        ContractStatus.EXPIRED: "expired"
    }
    return status_emojis.get(status, "unknown")


async def get_or_create_session(
    session_id: str,
    phone_number: str,
    db: AsyncSession
) -> USSDSession:
    """Get existing USSD session or create new one"""
    
    result = await db.execute(
        select(USSDSession).where(USSDSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        session = USSDSession(
            session_id=session_id,
            phone_number=phone_number,
            current_menu="main",
            context_data={},
            is_active=True,
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        db.add(session)
    
    return session


async def get_user_contracts(phone_number: str, db: AsyncSession) -> List[Contract]:
    """Get contracts for a phone number"""
    
    result = await db.execute(
        select(Contract)
        .join(ContractParty)
        .where(
            and_(
                ContractParty.phone_number == phone_number,
                Contract.status.in_([
                    ContractStatus.CONFIRMED,
                    ContractStatus.ACTIVE,
                    ContractStatus.PENDING
                ])
            )
        )
        .order_by(Contract.created_at.desc())
    )
    
    return result.scalars().all()


async def update_contract_status(
    contract_id: str,
    status: ContractStatus,
    db: AsyncSession
):
    """Update contract status"""
    
    result = await db.execute(
        select(Contract).where(Contract.id == contract_id)
    )
    contract = result.scalar_one_or_none()
    
    if contract:
        contract.status = status
        if status == ContractStatus.COMPLETED:
            contract.completed_at = datetime.utcnow()
        await db.commit()


@router.get("/test/{phone_number}")
async def test_ussd_menu(
    phone_number: str,
    at_client: AfricasTalkingClient = Depends(get_africastalking_client),
    db: AsyncSession = Depends(get_db)
):
    """Test USSD menu generation for a phone number"""
    try:
        contracts = await get_user_contracts(phone_number, db)
        
        if contracts:
            menu = at_client.generate_ussd_contract_menu([
                {
                    "id": contract.id,
                    "status": contract.status.value,
                    "total_amount": float(contract.total_amount or 0),
                    "currency": contract.currency
                }
                for contract in contracts
            ])
        else:
            menu = "No contracts found for this number."
        
        return {
            "phone_number": phone_number,
            "contracts_count": len(contracts),
            "ussd_menu": menu
        }
        
    except Exception as e:
        logger.error(f"USSD test failed: {e}")
        return {"error": str(e)}