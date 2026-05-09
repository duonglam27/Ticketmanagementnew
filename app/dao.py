
import uuid
from datetime import datetime

from sqlalchemy.orm import joinedload
from sqlalchemy import or_, func, case, and_
from app import db
from app.models import (
    User, Event, RoleEnum,
    Showing, TicketType, Seat, Ticket, TicketStatus,
    EventStatus, Order, OrderItem, OrderStatus
)

# ======================================================
# USER DAO
# ======================================================

def get_user_by_email(email):
    return User.query.filter_by(email=email).first()


def get_user_by_id(user_id):
    return db.session.get(User, user_id)


def create_user(email, name, password_hash, role=RoleEnum.USER, avatar=None):
    try:
        user = User(
            email=email,
            name=name,
            password_hash=password_hash,
            role=role,
            avatar=avatar
        )
        db.session.add(user)
        db.session.commit()
        return user
    except Exception as e:
        db.session.rollback()
        raise e


def update_user_db():
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


# ======================================================
# EVENT - BASIC CRUD
# ======================================================

def create_event(name, description, category, location, event_type, image, organizer_id):
    try:
        e = Event(
            name=name,
            description=description,
            category=category,
            location=location,
            event_type=event_type,
            image=image,
            organizer_id=organizer_id
        )
        db.session.add(e)
        db.session.commit()
        return e
    except Exception as e:
        db.session.rollback()
        raise e


def create_event_nc(data, organizer_id):
    e = Event(
        name=data.get('name'),
        description=data.get('description'),
        category=data.get('category'),
        location_name=data.get('location_name'),
        city=data.get('city'),
        event_type=data.get('event_type'),
        image_poster=data.get('image_poster'),
        image_banner=data.get('image_banner'),
        organizer_brand=data.get('organizer_brand'),
        organizer_logo=data.get('organizer_logo'),
        organizer_id=organizer_id
    )
    db.session.add(e)
    return e


def get_event_by_id(event_id):
    return db.session.get(Event, event_id)


def delete_event(event_id):
    try:
        e = get_event_by_id(event_id)
        if e:
            db.session.delete(e)
            db.session.commit()
            return True
        return False
    except Exception as e:
        db.session.rollback()
        raise e


# ======================================================
# ======================================================
# EVENT - QUERY / FILTER / SEARCH
# ======================================================

def get_all_events(limit=None):
    query = Event.query\
        .filter(Event.status == EventStatus.APPROVED)\
        .order_by(Event.created_at.desc())

    if limit:
        query = query.limit(limit)

    return query.all()


def get_events(
    kw=None,
    category=None,
    organizer_id=None,
    page=1,
    per_page=12
):
    """
    Dùng cho:
    - Trang list có phân trang
    - Admin / Organizer / User
    """

    query = Event.query

    # User chỉ thấy APPROVED
    if not organizer_id:
        query = query.filter(Event.status == EventStatus.APPROVED)

    # Search keyword
    if kw:
        search = f"%{kw}%"
        query = query.filter(or_(
            Event.name.ilike(search),
            Event.description.ilike(search),
            Event.location_name.ilike(search)
        ))

    # Filter category
    if category:
        query = query.filter(Event.category == category)

    # Filter theo organizer
    if organizer_id:
        query = query.filter(Event.organizer_id == organizer_id)

    query = query.order_by(Event.created_at.desc())

    return query.paginate(page=page, per_page=per_page)


def get_events_by_user(user_id):
    return Event.query\
        .options(joinedload(Event.showings))\
        .filter_by(organizer_id=user_id)\
        .all()

def get_organizer_events_full(user_id):
    return (
        db.session.query(
            Event.id,
            Event.name,
            Event.image_banner,
            Event.status,
            func.min(Showing.start_time).label("start_time"),

            func.count(Ticket.id).label("total"),
            func.sum(
                case((Ticket.status == TicketStatus.SOLD, 1), else_=0)
            ).label("sold"),

            func.sum(OrderItem.price).label("revenue")
        )
        .outerjoin(Showing, Showing.event_id == Event.id)
        .outerjoin(Ticket, Ticket.showing_id == Showing.id)
        .outerjoin(OrderItem, OrderItem.ticket_id == Ticket.id)
        .outerjoin(Order, Order.id == OrderItem.order_id)

        .filter(Event.organizer_id == user_id)

        .filter(
            (Order.status == OrderStatus.PAID) | (Order.id == None)
        )

        .group_by(Event.id)
        .order_by(Event.created_at.desc())
        .all()
    )


def get_all_categories():
    """Lấy danh sách category duy nhất từ các sự kiện đã APPROVED"""

    categories = db.session.query(Event.category) \
        .filter(Event.status == EventStatus.APPROVED) \
        .distinct().all()

    return [c[0] for c in categories if c[0]]

def get_all_locations():
    """Lấy danh sách các tỉnh thành duy nhất từ các sự kiện đã APPROVED"""
    # Giả sử bạn dùng cột 'city' hoặc 'location_name'
    locations = db.session.query(Event.city)\
        .filter(Event.status == EventStatus.APPROVED)\
        .distinct().all()
    return [loc[0] for loc in locations if loc[0]]

def search_events_simple(keyword=None, category=None, location=None):
    # Sử dụng joinedload để nạp sẵn showings và ticket_types nhằm phục vụ hàm min_price
    query = Event.query.options(
        joinedload(Event.showings).joinedload(Showing.ticket_types)
    ).filter(Event.status == EventStatus.APPROVED)

    if keyword:
        search = f"%{keyword}%"
        query = query.filter(
            Event.name.ilike(search) |
            Event.location_name.ilike(search)
        )

    if category and category != "Tất cả":
        query = query.filter(Event.category == category)

    if location:
        query = query.filter(Event.city == location)

    # Sắp xếp sự kiện mới nhất lên đầu
    return query.order_by(Event.id.desc()).all()


def search_events_full(keyword=None, category=None, limit=None):
    """
    Dùng cho:
    - Trang explore
    - Trang cần hiển thị giá vé, showings

    Có eager loading để tránh N+1
    """

    query = Event.query.options(
        joinedload(Event.showings)
        .joinedload(Showing.ticket_types)
    )

    if category and category != "Tất cả":
        query = query.filter(Event.category == category)

    if keyword and keyword.strip():
        search = f"%{keyword.strip()}%"
        query = query.filter(or_(
            Event.name.ilike(search),
            Event.location_name.ilike(search),
            Event.city.ilike(search)
        ))

    query = query.order_by(Event.created_at.desc())

    if limit:
        query = query.limit(limit)

    return query.all()

# ======================================================
# EVENT - DETAIL / RELATION LOAD
# ======================================================

def get_event_details(event_id):
    return db.session.query(Event)\
        .options(
            joinedload(Event.showings)
            .joinedload(Showing.ticket_types)
        )\
        .filter(Event.id == event_id)\
        .first()


def get_events_with_showings():
    return Event.query\
        .filter(Event.status == EventStatus.APPROVED)\
        .options(joinedload(Event.showings))\
        .all()


#Orders



# ======================================================
# SHOWING & TICKET TYPE
# ======================================================

def create_showing(event_id, start_time):
    try:
        s = Showing(event_id=event_id, start_time=start_time)
        db.session.add(s)
        db.session.commit()
        return s
    except Exception as e:
        db.session.rollback()
        raise e


def create_showing_nc(event_id, start_time):
    showing = Showing(event_id=event_id, start_time=start_time)
    db.session.add(showing)
    return showing


def create_ticket_type(showing_id, name, price, quantity):
    try:
        tt = TicketType(
            showing_id=showing_id,
            name=name,
            base_price=price,
            total_quantity=quantity
        )
        db.session.add(tt)
        db.session.commit()
        return tt
    except Exception as e:
        db.session.rollback()
        raise e


def create_ticket_type_nc(showing_id, name, base_price, total_quantity):
    tt = TicketType(
        showing_id=showing_id,
        name=name,
        base_price=base_price,
        total_quantity=total_quantity
    )
    db.session.add(tt)
    return tt


# ======================================================
# SEAT & TICKET (BULK)
# ======================================================

def get_ticket_by_id(ticket_id):

    return Ticket.query.get(ticket_id)

def get_user_tickets(user_id):
    # Join chính xác theo tên Class Model
    return Ticket.query.join(OrderItem).join(Order).filter(
        Order.user_id == user_id
    ).order_by(Ticket.id.desc()).all()

def init_showing_seats_and_tickets(showing_id, rows, cols, ticket_type_id):
    seats = []
    for r in range(rows):
        row_label = chr(65 + r)
        for c in range(1, cols + 1):
            seats.append(Seat(showing_id=showing_id, seat_number=f"{row_label}{c}"))

    db.session.add_all(seats)
    db.session.flush() # Lấy Seat ID

    tickets = []
    for s in seats:
        tickets.append(Ticket(
            showing_id=showing_id,
            ticket_type_id=ticket_type_id,
            seat_id=s.id,
            status=TicketStatus.AVAILABLE,
            qr_code=str(uuid.uuid4()) # QR code sẵn sàng cho check-in
        ))

    db.session.bulk_save_objects(tickets)
    return len(seats)



def get_ticket_by_code(qr_code_data):
    """Tìm vé dựa trên dữ liệu QR code quét được"""
    return Ticket.query.filter_by(qr_code=qr_code_data).first()

def update_ticket_checkin(ticket_id):
    """Cập nhật trạng thái vé thành USED và ghi nhận thời gian"""
    ticket = Ticket.query.get(ticket_id)
    if ticket:
        ticket.status = TicketStatus.USED
        ticket.checked_in_at = datetime.now()
        db.session.commit()
        return True
    return False

# ======================================================
# SHOWING / BOOKING
# ======================================================

def get_showing_by_id(showing_id):
    return db.session.query(Showing)\
        .options(joinedload(Showing.event))\
        .filter(Showing.id == showing_id)\
        .first()


def get_tickets_by_showing(showing_id):
    return db.session.query(Ticket)\
        .join(Seat)\
        .options(
            joinedload(Ticket.seat),
            joinedload(Ticket.ticket_type)
        )\
        .filter(Ticket.showing_id == showing_id)\
        .order_by(Seat.seat_number)\
        .all()


# ======================================================
# DASHBOARD
# ======================================================

def get_dashboard_summary(user_id):
    return db.session.query(
        func.count(func.distinct(Event.id)).label('total_events'),
        func.count(Ticket.id).label('total_tickets'),
        func.sum(
            case((Ticket.status == TicketStatus.SOLD, 1), else_=0)
        ).label('sold_tickets'),
        func.sum(OrderItem.price).label('total_revenue')
    )\
    .join(Showing, Showing.event_id == Event.id)\
    .join(Ticket, Ticket.showing_id == Showing.id)\
    .outerjoin(OrderItem, OrderItem.ticket_id == Ticket.id)\
    .outerjoin(Order, Order.id == OrderItem.order_id)\
    .filter(Event.organizer_id == user_id)\
    .filter((Order.status == OrderStatus.PAID) | (Order.id == None))\
    .first()


def get_dashboard_events(user_id):
    return (
        db.session.query(
            Event.id,
            Event.name,
            Event.image_banner,
            func.count(Ticket.id).label('total_tickets'),
            func.sum(
                case((Ticket.status == TicketStatus.SOLD, 1), else_=0)
            ).label('sold_tickets'),
            func.sum(OrderItem.price).label('revenue')
        )
        .join(Showing, Showing.event_id == Event.id)
        .join(Ticket, Ticket.showing_id == Showing.id)
        .outerjoin(OrderItem, OrderItem.ticket_id == Ticket.id)
        .outerjoin(Order, Order.id == OrderItem.order_id)
        .filter(Event.organizer_id == user_id)
        .filter((Order.status == OrderStatus.PAID) | (Order.id == None))
        .group_by(Event.id)
        .all()
    )


# ======================================================
# LEGACY / STATS (GIỮ NGUYÊN)
# ======================================================

def get_events_with_stats(user_id):
    return db.session.query(
        Event,
        func.count(Ticket.id).label('total_tickets'),
        func.sum(case((Ticket.status == 'SOLD', 1), else_=0)).label('sold_tickets'),
        func.sum(case((Ticket.status == 'SOLD', Ticket.price), else_=0)).label('revenue')
    ).join(Showing).join(Ticket).filter(Event.user_id == user_id)\
     .group_by(Event.id).all()




#REPORT
def get_report_summary(event_id):
    return (
        db.session.query(
            func.count(Ticket.id).label("total"),
            func.sum(
                case((Ticket.status == TicketStatus.SOLD, 1), else_=0)
            ).label("sold"),
            func.sum(OrderItem.price).label("revenue")
        )
        .join(Showing, Showing.id == Ticket.showing_id)
        .outerjoin(OrderItem, OrderItem.ticket_id == Ticket.id)
        .outerjoin(Order, Order.id == OrderItem.order_id)
        .filter(Showing.event_id == event_id)
        .filter(
            (Order.status == OrderStatus.PAID) | (Order.id == None)
        )
        .first()
    )


def get_revenue_by_day(event_id):
    return (
        db.session.query(
            func.date(Order.created_at).label("date"),
            func.sum(OrderItem.price).label("revenue")
        )
        .join(OrderItem, Order.id == OrderItem.order_id)
        .join(Ticket, Ticket.id == OrderItem.ticket_id)
        .join(Showing, Showing.id == Ticket.showing_id)
        .filter(Showing.event_id == event_id)
        .filter(Order.status == OrderStatus.PAID)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
        .all()
    )



def get_ticket_type_stats(event_id):
    return (
        db.session.query(
            TicketType.name,
            func.count(Ticket.id).label("sold")
        )
        .join(Ticket, Ticket.ticket_type_id == TicketType.id)
        .join(Showing, Showing.id == Ticket.showing_id)
        .filter(Showing.event_id == event_id)
        .filter(Ticket.status == TicketStatus.SOLD)
        .group_by(TicketType.name)
        .all()
    )


#Order
def cancel_order_db(order):
    """Cập nhật trạng thái đơn hàng và giải phóng vé"""
    order.status = OrderStatus.CANCELLED

    # Giả sử Order có quan hệ tickets (order.tickets)
    for ticket in order.tickets:
        # 1. Cập nhật trạng thái vé về lại AVAILABLE
        ticket.status = TicketStatus.AVAILABLE
        ticket.order_id = None  # Gỡ bỏ liên kết với đơn hàng cũ nếu cần

        # 2. Hoàn tác sold_quantity trong TicketType
        t_type = ticket.ticket_type
        if t_type and t_type.sold_quantity > 0:
            t_type.sold_quantity -= 1

    db.session.add(order)
    return True

def get_order_by_id(order_id):
    return Order.query.options(
        joinedload(Order.items)
            .joinedload(OrderItem.ticket)
            .joinedload(Ticket.ticket_type)
            .joinedload(TicketType.showing) # Load thêm Showing
            .joinedload(Showing.event),     # Load thêm Event để hiện tên show
        joinedload(Order.items)
            .joinedload(OrderItem.ticket)
            .joinedload(Ticket.seat)
    ).get(order_id)


def create_order(user_id, total_amount, ticket_items):
    try:
        # 1. Khởi tạo Order
        new_order = Order(
            user_id=user_id,
            total_amount=total_amount,
            status=OrderStatus.PENDING
        )
        db.session.add(new_order)
        db.session.flush()

        # Lấy danh sách ID để truy vấn một lần
        ticket_ids = [item['ticket_id'] for item in ticket_items]

        # 2. Truy vấn tất cả vé và khóa bản ghi (Pessimistic Locking)
        tickets = Ticket.query.filter(Ticket.id.in_(ticket_ids)).with_for_update().all()
        ticket_map = {t.id: t for t in tickets}

        for item in ticket_items:
            t_id = item['ticket_id']
            ticket = ticket_map.get(t_id)

            # Kiểm tra xem vé có còn trống không trước khi khóa
            if not ticket or ticket.status != TicketStatus.AVAILABLE:
                raise Exception(f"Vé {t_id} không còn khả dụng hoặc đã bị người khác đặt.")

            # 3. Tạo OrderItem
            order_item = OrderItem(
                order_id=new_order.id,
                ticket_id=t_id,
                price=item['price']
            )
            db.session.add(order_item)

            # 4. Cập nhật trạng thái
            ticket.status = TicketStatus.LOCKED

        db.session.commit()
        return new_order
    except Exception as e:
        db.session.rollback()
        raise e


def update_order_status(order_id, status):
    """Cập nhật trạng thái đơn hàng (PAID, CANCELLED,...)"""
    order = Order.query.get(order_id)
    if order:
        order.status = status

        # Nếu thanh toán thành công, chuyển vé sang SOLD
        if status == OrderStatus.PAID:
            for item in order.order_items:
                item.ticket.status = TicketStatus.SOLD

        # Nếu hủy đơn, trả vé về AVAILABLE
        elif status == OrderStatus.CANCELLED:
            for item in order.order_items:
                item.ticket.status = TicketStatus.AVAILABLE

        db.session.commit()
    return order


def add_order_item(order_id, ticket_id, price):
    """Thêm chi tiết vé vào đơn hàng"""
    item = OrderItem(
        order_id=order_id,
        ticket_id=ticket_id,
        price=price
    )
    db.session.add(item)
    return item

def get_user_orders(user_id):
    """Lấy lịch sử mua vé của người dùng"""
    return Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()


def get_available_tickets_by_type(ticket_type_id, limit):
    return Ticket.query.filter(
        Ticket.ticket_type_id == ticket_type_id,
        Ticket.status == TicketStatus.AVAILABLE # Chỉ lấy vé có trạng thái sẵn sàng
    ).limit(limit).with_for_update().all()


#Payment
def get_order_for_payment(order_id):
    return Order.query.get(order_id)


def complete_payment_db(order, payment_method):
    order.status = OrderStatus.PAID
    order.payment_method = payment_method  # Lưu ý: Model Order chưa có cột này, Lâm nên thêm vào hoặc lưu vào bảng Payment

    # Duyệt qua items thay vì tickets trực tiếp
    for item in order.items:
        if item.ticket:
            item.ticket.status = TicketStatus.SOLD
            item.ticket.locked_until = None

    db.session.add(order)
    return order


# Checkin
def get_by_qr(qr_code):
    return Ticket.query.filter_by(qr_code=qr_code).first()

def update_status(ticket, status, check_in_time=None):
    ticket.status = status
    if check_in_time:
        ticket.checked_in_at = check_in_time
    db.session.commit()
    return ticket