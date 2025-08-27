import enum
from datetime import datetime
from typing import Optional, List
from decimal import Decimal

from sqlalchemy import (
    Column,
    String, 
    Text,
    Integer,
    Numeric,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    CheckConstraint,
    UniqueConstraint,
    Enum as SQLEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.sqlite import JSON

from app.core.database import Base


class ContractStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ContractType(str, enum.Enum):
    AGRICULTURAL_SUPPLY = "agricultural_supply"
    SERVICE_AGREEMENT = "service_agreement"
    GOODS_PURCHASE = "goods_purchase"
    LOGISTICS = "logistics"
    OTHER = "other"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    LOCKED = "locked"
    RELEASED = "released"
    REFUNDED = "refunded"
    FAILED = "failed"


class PartyRole(str, enum.Enum):
    BUYER = "buyer"
    SELLER = "seller"
    MEDIATOR = "mediator"
    WITNESS = "witness"


class SignatureStatus(str, enum.Enum):
    PENDING = "pending"
    SIGNED = "signed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    
    audio_url: Mapped[Optional[str]] = mapped_column(String(500))
    transcript: Mapped[str] = mapped_column(Text)
    
    contract_type: Mapped[ContractType] = mapped_column(
        SQLEnum(ContractType), 
        default=ContractType.OTHER
    )
    
    terms: Mapped[dict] = mapped_column(JSON, default=dict)
    
    contract_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    
    total_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2)
    )
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    
    status: Mapped[ContractStatus] = mapped_column(
        SQLEnum(ContractStatus),
        default=ContractStatus.PENDING,
        index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        index=True
    )
    
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    delivery_location: Mapped[Optional[str]] = mapped_column(String(200))
    delivery_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    quality_requirements: Mapped[Optional[str]] = mapped_column(Text)
    additional_terms: Mapped[Optional[str]] = mapped_column(Text)
    
    parties: Mapped[List["ContractParty"]] = relationship(
        "ContractParty",
        back_populates="contract",
        cascade="all, delete-orphan"
    )
    
    signatures: Mapped[List["ContractSignature"]] = relationship(
        "ContractSignature",
        back_populates="contract",
        cascade="all, delete-orphan"
    )
    
    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="contract",
        cascade="all, delete-orphan"
    )
    
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="contract",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_contract_status_created", "status", "created_at"),
        Index("idx_contract_type_status", "contract_type", "status"),
        Index("idx_contract_delivery_deadline", "delivery_deadline"),
        CheckConstraint("total_amount >= 0", name="check_positive_amount"),
        CheckConstraint("created_at <= expires_at", name="check_valid_expiry"),
    )


class ContractParty(Base):
    __tablename__ = "contract_parties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    contract_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        index=True
    )
    
    phone_number: Mapped[str] = mapped_column(String(20), index=True)
    
    role: Mapped[PartyRole] = mapped_column(SQLEnum(PartyRole))
    
    name: Mapped[Optional[str]] = mapped_column(String(100))
    organization: Mapped[Optional[str]] = mapped_column(String(100))
    
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    contract: Mapped["Contract"] = relationship(
        "Contract", 
        back_populates="parties"
    )

    __table_args__ = (
        UniqueConstraint("contract_id", "phone_number", "role", name="unique_party_role"),
        Index("idx_party_phone_role", "phone_number", "role"),
    )


class ContractSignature(Base):
    __tablename__ = "contract_signatures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    contract_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        index=True
    )
    
    signer_phone: Mapped[str] = mapped_column(String(20), index=True)
    
    signature_method: Mapped[str] = mapped_column(
        String(20), 
        default="sms_confirmation"
    )
    
    signature_hash: Mapped[str] = mapped_column(String(128))
    
    signature_data: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    status: Mapped[SignatureStatus] = mapped_column(
        SQLEnum(SignatureStatus),
        default=SignatureStatus.PENDING
    )
    
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(200))
    
    contract: Mapped["Contract"] = relationship(
        "Contract",
        back_populates="signatures"
    )

    __table_args__ = (
        UniqueConstraint("contract_id", "signer_phone", name="unique_contract_signer"),
        Index("idx_signature_phone_status", "signer_phone", "status"),
        Index("idx_signature_created", "created_at"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    contract_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        index=True
    )
    
    transaction_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)
    external_transaction_id: Mapped[Optional[str]] = mapped_column(String(100))
    
    payer_phone: Mapped[str] = mapped_column(String(20), index=True)
    recipient_phone: Mapped[Optional[str]] = mapped_column(String(20))
    
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2))
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    
    payment_type: Mapped[str] = mapped_column(String(20), default="escrow")
    
    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus),
        default=PaymentStatus.PENDING,
        index=True
    )
    
    payment_method: Mapped[Optional[str]] = mapped_column(String(50))
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    failure_reason: Mapped[Optional[str]] = mapped_column(String(200))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    
    metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    contract: Mapped["Contract"] = relationship(
        "Contract",
        back_populates="payments"
    )

    __table_args__ = (
        Index("idx_payment_payer_status", "payer_phone", "status"),
        Index("idx_payment_status_created", "status", "created_at"),
        CheckConstraint("amount > 0", name="check_positive_payment_amount"),
        CheckConstraint("retry_count >= 0", name="check_non_negative_retry"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    contract_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        index=True
    )
    
    action: Mapped[str] = mapped_column(String(50), index=True)
    
    actor_phone: Mapped[Optional[str]] = mapped_column(String(20))
    actor_role: Mapped[Optional[str]] = mapped_column(String(20))
    
    old_values: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    new_values: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    details: Mapped[Optional[str]] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        index=True
    )
    
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(200))
    
    contract: Mapped["Contract"] = relationship(
        "Contract",
        back_populates="audit_logs"
    )

    __table_args__ = (
        Index("idx_audit_action_created", "action", "created_at"),
        Index("idx_audit_actor", "actor_phone"),
    )


class USSDSession(Base):
    __tablename__ = "ussd_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    session_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), index=True)
    
    current_menu: Mapped[str] = mapped_column(String(50), default="main")
    context_data: Mapped[dict] = mapped_column(JSON, default=dict)
    
    last_input: Mapped[Optional[str]] = mapped_column(String(200))
    last_response: Mapped[Optional[str]] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        index=True
    )
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    __table_args__ = (
        Index("idx_ussd_phone_active", "phone_number", "is_active"),
        Index("idx_ussd_expires", "expires_at"),
    )


class VoiceRecording(Base):
    __tablename__ = "voice_recordings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    recording_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    
    participants: Mapped[List[str]] = mapped_column(JSON, default=list)
    
    duration: Mapped[Optional[int]] = mapped_column(Integer)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    
    recording_url: Mapped[Optional[str]] = mapped_column(String(500))
    transcript: Mapped[Optional[str]] = mapped_column(Text)
    
    processing_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    processing_error: Mapped[Optional[str]] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("idx_recording_status_created", "processing_status", "created_at"),
        CheckConstraint("duration >= 0", name="check_non_negative_duration"),
        CheckConstraint("file_size >= 0", name="check_non_negative_file_size"),
    )


class SMSLog(Base):
    __tablename__ = "sms_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    message_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    
    recipient: Mapped[str] = mapped_column(String(20), index=True)
    message: Mapped[str] = mapped_column(Text)
    
    message_type: Mapped[str] = mapped_column(String(50), default="notification")
    
    status: Mapped[str] = mapped_column(String(20), default="sent", index=True)
    
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=10, scale=4))
    
    failure_reason: Mapped[Optional[str]] = mapped_column(String(200))
    
    contract_id: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    
    metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("idx_sms_recipient_status", "recipient", "status"),
        Index("idx_sms_type_sent", "message_type", "sent_at"),
        Index("idx_sms_contract", "contract_id"),
    )