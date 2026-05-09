from app.models import (
    Event,
    EventStatus,
    User,
    Order,
    OrderStatus, Ticket, Showing, RoleEnum
)
from app import db
from sqlalchemy import func
from datetime import datetime
# =========================
# DASHBOARD DAO
# =========================

def get_all_events():
    return Event.query.all()


def get_all_users():
    return User.query.all()


def get_paid_orders():
    return Order.query.filter(
        Order.status == OrderStatus.PAID
    ).all()


def calculate_total_revenue(orders):
    return sum(o.total_amount for o in orders)


def count_pending_events(events):
    return len([
        e for e in events
        if e.status == EventStatus.PENDING
    ])


def count_approved_events(events):
    return len([
        e for e in events
        if e.status == EventStatus.APPROVED
    ])


def count_rejected_events(events):
    return len([
        e for e in events
        if e.status == EventStatus.REJECTED
    ])

# =========================
# EVENT DAO
# =========================

def get_events(status=None, category=None):
    query = Event.query

    if status:
        query = query.filter(
            Event.status == EventStatus(status)
        )

    if category:
        query = query.filter(
            Event.category == category
        )

    return query.order_by(
        Event.created_at.desc()
    ).all()

# =========================
# EVENT ACTIONS
# =========================

def get_event_by_id(event_id):
    return Event.query.get_or_404(event_id)


def update_event_status(event_id, status):
    event = Event.query.get_or_404(event_id)

    event.status = status

    db.session.commit()

    return event

# =========================
# EVENT DETAIL
# =========================

def get_event_detail(event_id):
    return Event.query.get_or_404(event_id)


def get_event_tickets(event_id):
    return Ticket.query.join(
        Showing,
        Ticket.showing_id == Showing.id
    ).filter(
        Showing.event_id == event_id
    ).all()


# =========================
# DELETE EVENT
# =========================

def delete_event(event_id):
    event = Event.query.get_or_404(event_id)

    db.session.delete(event)
    db.session.commit()

# =========================
# USER DAO
# =========================

def get_users(role=None):
    query = User.query

    if role:
        query = query.filter(
            User.role == RoleEnum(role)
        )

    return query.all()


def get_user_by_id(user_id):
    return User.query.get_or_404(user_id)


def change_user_role(user_id, role):
    user = User.query.get_or_404(user_id)

    user.role = RoleEnum(role)

    db.session.commit()

    return user


def make_user_organizer(user_id):
    user = User.query.get_or_404(user_id)

    user.role = RoleEnum.ORGANIZER

    db.session.commit()

    return user


def make_organizer_user(user_id):
    user = User.query.get_or_404(user_id)

    user.role = RoleEnum.USER

    db.session.commit()

    return user

# =========================
# TOGGLE USER
# =========================
def toggle_user_status(user):
    if user.role == RoleEnum.ADMIN:
        return False

    user.active = not user.active

    db.session.commit()

    return True


# =========================
# USER DETAIL
# =========================
def update_user_info(user, name, email):
    user.name = name
    user.email = email

    db.session.commit()


def get_user_orders(user_id):
    return Order.query.filter_by(user_id=user_id).all()


def get_organizer_events(user_id):
    return Event.query.filter_by(organizer_id=user_id).all()


# =========================
# DELETE USER
# =========================
def remove_user(user):
    if user.role == RoleEnum.ADMIN:
        return False

    db.session.delete(user)
    db.session.commit()

    return True


# =========================
# ORGANIZERS
# =========================
def get_organizers():
    return User.query.filter(
        User.role == RoleEnum.ORGANIZER
    ).all()

# =========================
# GET USER
# =========================
def get_user(user_id):
    return User.query.get_or_404(user_id)

# =========================
# REVENUE
# =========================
def get_paid_orders():
    return Order.query.filter(
        Order.status == OrderStatus.PAID
    ).order_by(
        Order.created_at.desc()
    ).all()


def get_total_revenue(orders):
    return sum(o.total_amount for o in orders)


def get_revenue_by_day():
    revenue_data = db.session.query(
        func.date(Order.created_at).label("date"),
        func.sum(Order.total_amount).label("revenue")
    ).filter(
        Order.status == OrderStatus.PAID
    ).group_by(
        func.date(Order.created_at)
    ).order_by(
        func.date(Order.created_at)
    ).all()

    chart_labels = [str(r.date) for r in revenue_data]
    chart_values = [float(r.revenue) for r in revenue_data]

    return chart_labels, chart_values

# =========================
# TICKET
# =========================
def get_tickets(status=None):
    query = Ticket.query

    if status:
        query = query.filter(
            Ticket.status == TicketStatus(status)
        )

    return query.all()


def get_ticket(ticket_id):
    return Ticket.query.get_or_404(ticket_id)


def checkin_ticket(ticket):
    if ticket.checked_in:
        return False

    ticket.checked_in = True
    ticket.checked_in_at = datetime.now()

    db.session.commit()

    return True

# =========================
# ORDER
# =========================
def get_orders():
    return Order.query.order_by(
        Order.created_at.desc()
    ).all()


def get_order(order_id):
    return Order.query.get_or_404(order_id)


def cancel_order(order):
    order.status = OrderStatus.CANCELLED

    db.session.commit()