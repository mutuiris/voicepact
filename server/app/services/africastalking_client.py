import asyncio
import hashlib
import hmac
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

import africastalking
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AfricasTalkingException(Exception):
    def __init__(self, message: str, error_code: Optional[str] = None, response_data: Optional[dict] = None):
        self.message = message
        self.error_code = error_code
        self.response_data = response_data or {}
        super().__init__(self.message)


class CircuitBreakerOpen(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, expected_exception=Exception):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'

    async def call(self, func, *args, **kwargs):
        if self.state == 'OPEN':
            if time.time() - self.last_failure_time < self.recovery_timeout:
                raise CircuitBreakerOpen("Circuit breaker is OPEN")
            else:
                self.state = 'HALF_OPEN'

        try:
            result = await func(*args, **kwargs)
            self.reset()
            return result
        except self.expected_exception as e:
            self.record_failure()
            raise e

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'

    def reset(self):
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'


# AfricasTalking Client
class AfricasTalkingClient:
    def __init__(self):
        self.username = settings.at_username
        self.api_key = settings.get_secret_value('at_api_key')
        self.voice_number = settings.at_voice_number
        self.service_code = settings.at_ussd_service_code
        
        africastalking.initialize(self.username, self.api_key)
        
        # Always available services
        self.sms_service = africastalking.SMS
        self.voice_service = africastalking.Voice
        
        # Optional services
        try:
            self.payment_service = africastalking.Payment
        except (AttributeError, Exception):
            self.payment_service = None
            logger.warning("Payment API not available")
            
        try:
            self.airtime_service = africastalking.Airtime
        except (AttributeError, Exception):
            self.airtime_service = None
            logger.warning("Airtime API not available")
            
        try:
            self.token_service = africastalking.Token
        except (AttributeError, Exception):
            self.token_service = None
            logger.warning("Token API not available")
        
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive
            ),
            headers={'User-Agent': f'{settings.app_name}/1.0'}
        )
        
        self.sms_circuit_breaker = CircuitBreaker()
        self.voice_circuit_breaker = CircuitBreaker()
        self.payment_circuit_breaker = CircuitBreaker()
        
        self.webhook_secret = settings.get_secret_value('webhook_secret')

    async def close(self):
        await self.http_client.aclose()

    # Verify webhook signature
    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        if not self.webhook_secret or not signature:
            return False
        
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(f"sha256={expected_signature}", signature)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))
    )
    # Send SMS
    async def send_sms(
        self,
        message: str,
        recipients: List[str],
        sender_id: Optional[str] = None,
        enqueue: bool = False
    ) -> Dict[str, Any]:
        async def _send():
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.sms_service.send(
                        message=message,
                        recipients=recipients,
                        sender_id=sender_id,
                        enqueue=enqueue
                    )
                )
                return response
            except Exception as e:
                logger.error(f"SMS send failed: {str(e)}")
                raise AfricasTalkingException(f"SMS send failed: {str(e)}")

        return await self.sms_circuit_breaker.call(_send)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    # Send bulk SMS
    async def send_bulk_sms(
        self,
        messages: List[Dict[str, Union[str, List[str]]]],
        sender_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        tasks = []
        for msg_data in messages:
            task = self.send_sms(
                message=msg_data['message'],
                recipients=msg_data['recipients'],
                sender_id=sender_id
            )
            tasks.append(task)
        
        return await asyncio.gather(*tasks, return_exceptions=True)

    # Fetch SMS messages
    async def fetch_sms_messages(self, last_received_id: int = 0) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.sms_service.fetch_messages(last_received_id)
            )
            return response
        except Exception as e:
            logger.error(f"SMS fetch failed: {str(e)}")
            raise AfricasTalkingException(f"SMS fetch failed: {str(e)}")

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8)
    )
    async def make_voice_call(
        self,
        recipients: List[str],
        from_number: Optional[str] = None
    ) -> Dict[str, Any]:
        async def _call():
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.voice_service.call({
                        'to': recipients,
                        'from': from_number or self.voice_number
                    })
                )
                return response
            except Exception as e:
                logger.error(f"Voice call failed: {str(e)}")
                raise AfricasTalkingException(f"Voice call failed: {str(e)}")

        return await self.voice_circuit_breaker.call(_call)

    # Upload voice media
    async def upload_voice_media(self, phone_number: str, media_url: str) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.voice_service.upload_media_file(phone_number, media_url)
            )
            return response
        except Exception as e:
            logger.error(f"Voice media upload failed: {str(e)}")
            raise AfricasTalkingException(f"Voice media upload failed: {str(e)}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    # Mobile checkout
    async def mobile_checkout(
        self,
        phone_number: str,
        amount: Union[int, float],
        currency_code: str = "KES",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        async def _checkout():
            try:
                checkout_data = {
                    'productName': settings.at_payment_product_name,
                    'phoneNumber': phone_number,
                    'currencyCode': currency_code,
                    'amount': amount,
                    'metadata': metadata or {}
                }
                
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.payment_service.mobile_checkout(checkout_data)
                )
                return response
            except Exception as e:
                logger.error(f"Mobile checkout failed: {str(e)}")
                raise AfricasTalkingException(f"Mobile checkout failed: {str(e)}")

        return await self.payment_circuit_breaker.call(_checkout)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    # Mobile data transfer
    async def mobile_data_transfer(
        self,
        phone_number: str,
        amount: Union[int, float],
        currency_code: str = "KES",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        async def _transfer():
            try:
                transfer_data = {
                    'productName': settings.at_payment_product_name,
                    'recipients': [{
                        'phoneNumber': phone_number,
                        'currencyCode': currency_code,
                        'amount': amount,
                        'metadata': metadata or {}
                    }]
                }
                
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.payment_service.mobile_data(transfer_data)
                )
                return response
            except Exception as e:
                logger.error(f"Mobile data transfer failed: {str(e)}")
                raise AfricasTalkingException(f"Mobile data transfer failed: {str(e)}")

        return await self.payment_circuit_breaker.call(_transfer)

    # Query transaction status
    async def query_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.payment_service.fetch_product_transactions({
                    'productName': settings.at_payment_product_name,
                    'filters': {'transactionId': transaction_id}
                })
            )
            return response
        except Exception as e:
            logger.error(f"Transaction query failed: {str(e)}")
            raise AfricasTalkingException(f"Transaction query failed: {str(e)}")

    # Get wallet balance
    async def get_wallet_balance(self) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.payment_service.fetch_wallet_balance()
            )
            return response
        except Exception as e:
            logger.error(f"Wallet balance query failed: {str(e)}")
            raise AfricasTalkingException(f"Wallet balance query failed: {str(e)}")

    # Send airtime
    async def send_airtime(
        self,
        recipients: List[Dict[str, str]],
        max_num_retry: int = 3
    ) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.airtime_service.send({
                    'recipients': recipients,
                    'maxNumRetry': max_num_retry
                })
            )
            return response
        except Exception as e:
            logger.error(f"Airtime send failed: {str(e)}")
            raise AfricasTalkingException(f"Airtime send failed: {str(e)}")

    # Create checkout token
    async def create_checkout_token(self, phone_number: str) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.token_service.create_checkout_token(phone_number)
            )
            return response
        except Exception as e:
            logger.error(f"Checkout token creation failed: {str(e)}")
            raise AfricasTalkingException(f"Checkout token creation failed: {str(e)}")

    # Check SIM swap state
    async def check_sim_swap_state(self, phone_numbers: List[str]) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.voice_service.check_sim_swap_state(phone_numbers)
            )
            return response
        except Exception as e:
            logger.error(f"SIM swap check failed: {str(e)}")
            raise AfricasTalkingException(f"SIM swap check failed: {str(e)}")

    # USSD utilities
    def build_ussd_response(self, text: str, end_session: bool = False) -> str:
        if end_session:
            return f"END {text}"
        return f"CON {text}"

    def parse_ussd_input(self, text: str) -> List[str]:
        return text.split('*') if text else []

    async def validate_phone_number(self, phone_number: str) -> bool:
        if not phone_number.startswith('+'):
            return False
        
        phone_digits = ''.join(filter(str.isdigit, phone_number))
        return len(phone_digits) >= 10 and len(phone_digits) <= 15

    async def format_phone_number(self, phone_number: str, country_code: str = "254") -> str:
        phone_clean = ''.join(filter(str.isdigit, phone_number))
        
        if phone_clean.startswith(country_code):
            return f"+{phone_clean}"
        elif phone_clean.startswith('0'):
            return f"+{country_code}{phone_clean[1:]}"
        else:
            return f"+{country_code}{phone_clean}"

    # SMS templates
    def generate_contract_sms(
        self,
        contract_id: str,
        contract_terms: Dict[str, Any]
    ) -> str:
        product = contract_terms.get('product', 'Product')
        quantity = contract_terms.get('quantity', '')
        unit = contract_terms.get('unit', '')
        total_amount = contract_terms.get('total_amount', 0)
        currency = contract_terms.get('currency', 'KES')
        delivery_date = contract_terms.get('delivery_deadline', '')
        
        quantity_str = f"{quantity} {unit}" if quantity and unit else "Items"
        amount_str = f"{currency} {total_amount:,.2f}" if total_amount else "Amount TBD"
        date_str = f", Due: {delivery_date}" if delivery_date else ""
        
        return (
            f"VoicePact Contract Summary:\n"
            f"ID: {contract_id}\n"
            f"Product: {product} ({quantity_str})\n"
            f"Total: {amount_str}{date_str}\n"
            f"Reply YES-{contract_id} to confirm or NO-{contract_id} to decline"
        )

    # Payment SMS templates
    def generate_payment_sms(
        self,
        contract_id: str,
        amount: Union[int, float],
        currency: str = "KES",
        action: str = "received"
    ) -> str:
        return (
            f"VoicePact Payment {action.title()}:\n"
            f"Contract: {contract_id}\n"
            f"Amount: {currency} {amount:,.2f}\n"
            f"Status: Processing\n"
            f"You will receive confirmation shortly."
        )

    def generate_delivery_sms(
        self,
        contract_id: str,
        delivery_type: str = "full"
    ) -> str:
        return (
            f"VoicePact Delivery Alert:\n"
            f"Contract: {contract_id}\n"
            f"Type: {delivery_type.title()} delivery claimed\n"
            f"Please inspect and reply:\n"
            f"ACCEPT-{contract_id} or DISPUTE-{contract_id}"
        )

    def generate_ussd_contract_menu(self, contracts: List[Dict[str, Any]]) -> str:
        if not contracts:
            return "No active contracts found."
        
        menu_items = ["Select Contract:"]
        for i, contract in enumerate(contracts[:9], 1):
            status = contract.get('status', 'unknown')
            amount = contract.get('total_amount', 0)
            currency = contract.get('currency', 'KES')
            menu_items.append(f"{i}. {contract['id']} - {status.title()} ({currency} {amount:,.0f})")
        
        return "\n".join(menu_items)

    def generate_ussd_contract_detail(self, contract: Dict[str, Any]) -> str:
        product = contract.get('terms', {}).get('product', 'Product')
        quantity = contract.get('terms', {}).get('quantity', '')
        unit = contract.get('terms', {}).get('unit', '')
        amount = contract.get('total_amount', 0)
        currency = contract.get('currency', 'KES')
        status = contract.get('status', 'unknown')
        
        quantity_str = f" ({quantity} {unit})" if quantity and unit else ""
        
        return (
            f"Contract: {contract['id']}\n"
            f"Product: {product}{quantity_str}\n"
            f"Amount: {currency} {amount:,.2f}\n"
            f"Status: {status.title()}\n"
            f"1. Confirm Delivery\n"
            f"2. Report Issue\n"
            f"0. Back"
        )

    async def process_webhook_data(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        processed_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'original_data': webhook_data
        }
        
        if 'status' in webhook_data:
            processed_data['status'] = webhook_data['status']
        
        if 'transactionId' in webhook_data:
            processed_data['transaction_id'] = webhook_data['transactionId']
        
        if 'phoneNumber' in webhook_data:
            processed_data['phone_number'] = await self.format_phone_number(
                webhook_data['phoneNumber']
            )
        
        if 'amount' in webhook_data:
            try:
                amount_str = str(webhook_data['amount']).replace(',', '')
                processed_data['amount'] = float(amount_str)
            except (ValueError, TypeError):
                processed_data['amount'] = 0.0
        
        return processed_data

    async def health_check(self) -> Dict[str, str]:
        health_status = {
            'sms_service': 'unknown',
            'payment_service': 'unknown',
            'voice_service': 'unknown'
        }
        
        try:
            await self.get_wallet_balance()
            health_status['payment_service'] = 'healthy'
        except Exception as e:
            health_status['payment_service'] = f'error: {str(e)[:50]}'
        
        try:
            circuit_states = {
                'sms_circuit': self.sms_circuit_breaker.state,
                'voice_circuit': self.voice_circuit_breaker.state,
                'payment_circuit': self.payment_circuit_breaker.state
            }
            health_status.update(circuit_states)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
        
        return health_status


_client_instance = None


async def get_africastalking_client() -> AfricasTalkingClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = AfricasTalkingClient()
    return _client_instance


async def close_africastalking_client():
    global _client_instance
    if _client_instance:
        await _client_instance.close()
        _client_instance = None