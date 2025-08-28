#!/usr/bin/env python3
"""
VoicePact SMS Demo Script

Usage:
    python test_sms_demo.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.services.africastalking_client import AfricasTalkingClient
from app.services.contract_generator import ContractGenerator
from app.services.crypto_service import CryptoService
from app.core.config import get_settings


class SMSDemo:
    def __init__(self):
        self.settings = get_settings()
        self.at_client = None
        self.contract_generator = ContractGenerator()
        self.crypto_service = CryptoService()
        
    async def initialize(self):
        """Initialize the AT client"""
        self.at_client = AfricasTalkingClient()
        print("Africa's Talking client initialized")
    
    async def demo_sms_contract_flow(self):
        """Demonstrate the full SMS-based contract flow"""
        print("\nVoicePact SMS Demo Starting...")
        print("=" * 50)
        
        # Verified Number
        test_number = "+254711082231"

        farmer_phone = test_number # Seller
        buyer_phone = test_number # Buyer
        
        # Step 1: Simulate voice transcript
        print("\nStep 1: Creating Contract from 'Voice' Transcript")
        transcript = """
        John: Grace, my maize will be ready September 20th. I can offer you 100 bags of grade A maize.
        Grace: Perfect timing John. What's your price per bag?
        John: KES 3,200 per bag. I need 30% payment upfront this time.
        Grace: Deal. So 100 bags at KES 3,200, that's KES 320,000 total. 
        I'll pay KES 96,000 upfront, balance on delivery to my Thika Road warehouse.
        """
        
        print(f"Transcript: {transcript[:100]}...")
        
        # Step 2: Extract contract terms
        print("\nStep 2: AI Contract Term Extraction")
        terms = {
            "product": "Grade A Maize",
            "quantity": "100",
            "unit": "bags",
            "unit_price": 3200,
            "total_amount": 320000,
            "currency": "KES",
            "upfront_payment": 96000,
            "delivery_location": "Thika Road Warehouse",
            "delivery_deadline": "September 20, 2025",
            "quality_requirements": "Grade A standard"
        }
        
        print(f"Terms extracted: {terms['product']} - {terms['currency']} {terms['total_amount']:,}")
        
        # Step 3: Generate contract
        print("\nStep 3: Contract Generation")
        contract_id = self.contract_generator.generate_contract_id("agricultural_supply")
        contract_hash = self.crypto_service.generate_contract_hash(
            f"{transcript}:{str(sorted(terms.items()))}"
        )
        
        parties = [
            {"phone": farmer_phone, "role": "seller", "name": "John Kamau"},
            {"phone": buyer_phone, "role": "buyer", "name": "Grace Wanjiku"}
        ]
        
        print(f"Contract created: {contract_id}")
        print(f"Hash: {contract_hash[:16]}...")
        
        # Step 4: Send SMS confirmations
        print("\nStep 4: Sending SMS Confirmations")
        try:
            message = self.at_client.generate_contract_sms(contract_id, terms)
            print(f"SMS Message:")
            print("-" * 30)
            print(message)
            print("-" * 30)
            
            # Send to both parties
            if self.should_send_real_sms():
                recipients = [party["phone"] for party in parties]
                response = await self.at_client.send_sms(
                    message=message,
                    recipients=recipients
                )
                print(f"SMS sent to {len(recipients)} recipients")
                print(f"Response: {response}")
            else:
                print("SMS sending skipped (demo mode - set real phone numbers to test)")
                
        except Exception as e:
            print(f"SMS sending failed: {e}")
            print("Make sure AT_API_KEY is set correctly in .env")
        
        # Step 5: Simulate SMS confirmations
        print("\nStep 5: SMS Confirmation Simulation")
        confirmations = [
            {"phone": farmer_phone, "message": f"YES-{contract_id}"},
            {"phone": buyer_phone, "message": f"YES-{contract_id}"}
        ]
        
        for conf in confirmations:
            print(f"📲 {conf['phone']}: {conf['message']}")
        
        # Step 6: Payment initiation (simulation)
        print("\nStep 6: Payment Escrow Simulation")
        upfront_amount = terms['upfront_payment']
        print(f"Buyer pays upfront: {terms['currency']} {upfront_amount:,}")
        
        if self.should_send_real_sms():
            try:
                # Test mobile checkout (this will prompt the user's phone)
                print("Initiating test mobile checkout...")
                payment_response = await self.at_client.mobile_checkout(
                    phone_number=buyer_phone,
                    amount=upfront_amount,
                    currency_code=terms['currency'],
                    metadata={"contract_id": contract_id, "type": "upfront"}
                )
                print(f"Payment initiated: {payment_response}")
            except Exception as e:
                print(f"Payment initiation failed: {e}")
                print("This is normal in sandbox mode")
        
        # Step 7: USSD Menu simulation
        print("\n📞 Step 7: USSD Menu Simulation (*483#)")
        ussd_menu = f"""
VoicePact USSD Menu
1. View My Contracts
2. Confirm Delivery
3. Check Payments
4. Help & Support

Contract Status:
{contract_id[:12]}...
Status: Confirmed
Amount: {terms['currency']} {terms['total_amount']:,}
"""
        print(ussd_menu)
        
        # Step 8: Delivery confirmation
        print("\nStep 8: Delivery Confirmation Flow")
        delivery_sms = self.at_client.generate_delivery_sms(contract_id, "full")
        print(f"Delivery SMS to buyer:")
        print(delivery_sms)
        
        print("\nDemo Complete!")
        print("=" * 50)
        print(f"Contract Created: {contract_id}")
        print(f"Parties Notified: {len(parties)} via SMS")
        print(f"Payment Escrow: {terms['currency']} {upfront_amount:,}")
        print(f"Multi-modal Access: SMS + USSD")
        print(f"Crypto Security: Contract hash generated")
    
    def should_send_real_sms(self) -> bool:
        """Check if we should send real SMS"""
        return (
            self.settings.at_api_key != "your_africastalking_api_key_here" and
            self.settings.at_username != "sandbox" and
            len(self.settings.get_secret_value('at_api_key')) > 10
        )
    
    async def test_sms_basic(self):
        """Test basic SMS functionality"""
        print("\nBasic SMS Test")
        test_number = "+254700000000"
        
        try:
            message = f"VoicePact SMS Test - {datetime.now().strftime('%H:%M:%S')}"
            
            if self.should_send_real_sms():
                response = await self.at_client.send_sms(
                    message=message,
                    recipients=[test_number]
                )
                print(f"SMS sent successfully: {response}")
            else:
                print(f"Would send SMS: '{message}' to {test_number}")
                print("Set real API key and phone number to test")
                
        except Exception as e:
            print(f"SMS test failed: {e}")
    
    async def run_demo(self):
        """Run the full demo"""
        try:
            await self.initialize()

            if self.should_send_real_sms():
                await self.test_sms_basic()

            await self.demo_sms_contract_flow()
            
        except Exception as e:
            print(f"Demo failed: {str(e)}")
            print("Check your .env file and AT API configuration")
        finally:
            if self.at_client:
                await self.at_client.close()


async def main():
    """Main demo function"""
    print("🎙️ VoicePact SMS Demo")
    print("This demonstrates VoicePact functionality using SMS API")
    print("Perfect for hackathon demos when Voice API isn't available\n")
    
    # Check environment
    settings = get_settings()
    print(f"Environment: {settings.environment}")
    print(f"AT Username: {settings.at_username}")
    print(f"API Key Set: {'Yes' if settings.get_secret_value('at_api_key') != 'your_africastalking_api_key_here' else 'No - Update .env'}")
    
    demo = SMSDemo()
    await demo.run_demo()


if __name__ == "__main__":
    # Handle missing dependencies gracefully
    try:
        asyncio.run(main())
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: pip install -r requirements.txt")
    except Exception as e:
        print(f"Demo failed: {e}")
        print("Make sure to:")
        print("   1. Copy .env.template to .env")
        print("   2. Set your AT_API_KEY in .env")
        print("   3. Update phone numbers in the script")