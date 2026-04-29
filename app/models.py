import uuid
import enum
from datetime import datetime
from flask_login import UserMixin
from sqlalchemy.orm import relationship
from app import  db

# =========================
# ENUM
# =========================

class RoleEnum(enum.Enum):
    ADMIN = "admin"
    ORGANIZER = "organizer"
    USER = "user"


class OrderStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


class TicketStatus(enum.Enum):
    AVAILABLE = "available"
    LOCKED = "locked"
    SOLD = "sold"


class PaymentStatus(enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class PaymentMethod(enum.Enum):
    CASH = "cash"
    MOMO = "momo"
    VNPAY = "vnpay"

class EventStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

# =========================
# USER
# =========================

class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(RoleEnum), default=RoleEnum.USER)
    avatar = db.Column(db.String(255), default='/static/SystemPicture/avatardefault.jpg')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    events = relationship('Event', backref='organizer')
    orders = relationship('Order', backref='user')

    def is_admin(self):
        return self.role == RoleEnum.ADMIN

    def is_user(self):
        return self.role == RoleEnum.USER

    def is_organizer(self):
        return self.role == RoleEnum.ORGANIZER

    def has_role(self, role):
        """
        role: 'admin', 'user', 'organizer'
        """
        return self.role.value == role

# =========================
# EVENT
# =========================

class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))

    # New Fields for UI
    location_name = db.Column(db.String(100))  # e.g., "Sân vận động Mỹ Đình"
    city = db.Column(db.String(50))  # e.g., "Hà Nội"
    event_type = db.Column(db.String(20))  # "Offline" or "Online"
    status = db.Column(db.Enum(EventStatus), default=EventStatus.PENDING)

    # Dual Image Support
    image_poster = db.Column(db.String(255))  # Vertical (720x958)
    image_banner = db.Column(db.String(255))  # Horizontal (1280x720)

    # Organizer Info (to match UI)
    organizer_brand = db.Column(db.String(100))
    organizer_logo = db.Column(db.String(255))

    organizer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    showings = relationship('Showing', backref='event')

# =========================
# SHOWING
# =========================

class Showing(db.Model):
    __tablename__ = 'showings'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'))

    start_time = db.Column(db.DateTime, nullable=False)

    ticket_types = relationship('TicketType', backref='showing')
    tickets = relationship('Ticket', backref='showing')
    seats = relationship('Seat', backref='showing')


# =========================
# SEAT (optional)
# =========================

class Seat(db.Model):
    __tablename__ = 'seats'

    id = db.Column(db.Integer, primary_key=True)
    showing_id = db.Column(db.Integer, db.ForeignKey('showings.id'))

    seat_number = db.Column(db.String(10))

    ticket = relationship('Ticket', backref='seat', uselist=False)


# =========================
# TICKET TYPE
# =========================

class TicketType(db.Model):
    __tablename__ = 'ticket_types'

    id = db.Column(db.Integer, primary_key=True)
    showing_id = db.Column(db.Integer, db.ForeignKey('showings.id'))

    name = db.Column(db.String(100))
    base_price = db.Column(db.Float)
    total_quantity = db.Column(db.Integer)

    sold_quantity = db.Column(db.Integer, default=0)

    tickets = relationship('Ticket', backref='ticket_type')

    def get_price(self):
        remaining = self.total_quantity - self.sold_quantity

        if remaining < 10:
            return self.base_price * 1.5
        elif remaining < 50:
            return self.base_price * 1.2
        return self.base_price


# =========================
# TICKET
# =========================

class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)

    ticket_code = db.Column(db.String(100), unique=True, default=lambda: str(uuid.uuid4()))

    showing_id = db.Column(db.Integer, db.ForeignKey('showings.id'))
    ticket_type_id = db.Column(db.Integer, db.ForeignKey('ticket_types.id'))

    seat_id = db.Column(db.Integer, db.ForeignKey('seats.id'), nullable=True)

    status = db.Column(db.Enum(TicketStatus), default=TicketStatus.AVAILABLE)
    locked_until = db.Column(db.DateTime)

    checked_in = db.Column(db.Boolean, default=False)
    checked_in_at = db.Column(db.DateTime)


    __table_args__ = (
        db.UniqueConstraint('seat_id', name='uq_ticket_seat'),
    )


# =========================
# ORDER
# =========================

class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    status = db.Column(db.Enum(OrderStatus), default=OrderStatus.PENDING)
    total_amount = db.Column(db.Float)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = relationship('OrderItem', backref='order')
    payment = relationship('Payment', backref='order', uselist=False)


# =========================
# ORDER ITEM
# =========================

class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'))

    price = db.Column(db.Float)

    ticket = relationship('Ticket')

    __table_args__ = (
        db.UniqueConstraint('ticket_id', name='uq_ticket_orderitem'),
    )


# =========================
# PAYMENT
# =========================

class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    amount = db.Column(db.Float)
    method = db.Column(db.Enum(PaymentMethod))
    status = db.Column(db.Enum(PaymentStatus), default=PaymentStatus.PENDING)

    transaction_id = db.Column(db.String(255))
    paid_at = db.Column(db.DateTime)
