from sqlalchemy.orm import joinedload
from app import db
from app.models import User, Event, RoleEnum, Showing, TicketType, Seat, Ticket, TicketStatus
from sqlalchemy import or_
# --- USER DAO ---

def get_user_by_email(email):
    """Tìm user theo email - dùng cho login/register check"""
    return User.query.filter_by(email=email).first()

def get_user_by_id(user_id):
    """Sử dụng cú pháp mới của SQLAlchemy 3.0+"""
    return db.session.get(User, user_id)

def create_user(email, name, password_hash, role=RoleEnum.USER, avatar=None):
    """Tạo user mới từ các tham số thô"""
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
    """Hàm hỗ trợ commit các thay đổi của object đã nằm trong session"""
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        return False

# --- EVENT DAO ---

def create_event(name, description, category, location, event_type, image, organizer_id):
    """Tạo event mới"""
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

def get_all_events(limit=None):
    """Lấy danh sách sự kiện, mặc định mới nhất lên đầu"""
    query = Event.query.order_by(Event.created_at.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def get_events(kw=None, category=None, organizer_id=None, page=1, per_page=12):
    """
    Tìm kiếm và lọc sự kiện với phân trang.
    """
    query = Event.query

    if kw:
        query = query.filter(or_(
            Event.name.icontains(kw),
            Event.description.icontains(kw),
            Event.location.icontains(kw)
        ))

    if category:
        query = query.filter(Event.category == category)

    if organizer_id:
        query = query.filter(Event.organizer_id == organizer_id)

    # Mặc định sự kiện mới nhất hoặc sắp diễn ra lên đầu
    query = query.order_by(Event.created_at.desc())

    return query.paginate(page=page, per_page=per_page)


def get_event_by_id(event_id):
    """Lấy chi tiết 1 sự kiện (dùng db.session.get cho SQLAlchemy 2.0+)"""
    return db.session.get(Event, event_id)

def get_event_details(event_id):
    """
    Lấy chi tiết sự kiện kèm theo tất cả suất diễn (showings)
    và loại vé (ticket_types) liên quan.
    """
    return db.session.query(Event)\
        .options(joinedload(Event.showings).joinedload(Showing.ticket_types))\
        .filter(Event.id == event_id)\
        .first()

def delete_event(event_id):
    """Xóa sự kiện (Lưu ý: Sẽ xóa cascade các Showing/Tickets nếu cấu hình trong Model)"""
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

def create_showing(event_id, start_time):
    """Tạo một khung giờ diễn cho sự kiện"""
    try:
        s = Showing(event_id=event_id, start_time=start_time)
        db.session.add(s)
        db.session.commit()
        return s
    except Exception as e:
        db.session.rollback()
        raise e

def create_ticket_type(showing_id, name, price, quantity):
        """Tạo loại vé (VIP, Standard...) cho một suất diễn cụ thể"""
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


def get_events_with_showings():
    """Lấy sự kiện và nạp sẵn luôn danh sách suất diễn để tăng tốc độ load"""
    return Event.query.options(joinedload(Event.showings)).all()



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

def create_showing_nc(event_id, start_time):
    s = Showing(event_id=event_id, start_time=start_time)
    db.session.add(s)
    return s

def create_ticket_type_nc(showing_id, name, price, quantity):
    tt = TicketType(
        showing_id=showing_id,
        name=name,
        base_price=price,
        total_quantity=quantity
    )
    db.session.add(tt)
    return tt


def bulk_create_seats_nc(showing_id, seat_numbers_list):
    """
    Tạo hàng loạt ghế cho một suất diễn mà không commit.
    Trả về danh sách các object Seat đã được nạp vào session.
    """
    if not seat_numbers_list:
        return []

    # 1. Chuẩn bị dữ liệu dạng list of dicts cho Bulk Insert
    # mappings = [{"showing_id": 1, "seat_number": "A1"}, ...]
    mappings = [
        {
            "showing_id": showing_id,
            "seat_number": str(s_num).strip()
        }
        for s_num in seat_numbers_list if str(s_num).strip()
    ]

    # 2. Sử dụng bulk_insert_mappings để tăng hiệu năng (không commit)
    # Phương thức này đưa dữ liệu vào session cực nhanh
    db.session.bulk_insert_mappings(Seat, mappings)

    # 3. Lấy lại các object đã tạo (Cần thiết cho bước init_tickets_bulk_nc)
    # Vì bulk_insert không trả về object trực tiếp, ta truy vấn lại trong session
    return Seat.query.filter_by(showing_id=showing_id).all()


def init_tickets_bulk_nc(showing_id, ticket_type_id, seat_objects):
    """
    Khởi tạo hàng loạt vé trống gắn liền với danh sách ghế.
    seat_objects: Danh sách các đối tượng Seat đã có ID từ database.
    """
    if not seat_objects:
        return

    # 1. Chuẩn bị dữ liệu ánh xạ (mapping)
    # Trạng thái mặc định là AVAILABLE (Sẵn sàng bán)
    mappings = [
        {
            "showing_id": showing_id,
            "ticket_type_id": ticket_type_id,
            "seat_id": seat.id,
            "status": TicketStatus.AVAILABLE,
            # ticket_code sẽ được tự động sinh bởi uuid.uuid4() trong Model
        }
        for seat in seat_objects
    ]

    # 2. Thực thi nạp hàng loạt vào session
    db.session.bulk_insert_mappings(Ticket, mappings)

def get_showing_by_id(showing_id):
    """
    Lấy chi tiết suất diễn và nạp trước dữ liệu Event để tối ưu hiệu năng.
    """
    return db.session.query(Showing)\
        .options(joinedload(Showing.event))\
        .filter(Showing.id == showing_id)\
        .first()

def get_tickets_by_showing(showing_id):
    """
    Lấy danh sách vé kèm theo Ghế và Loại vé.
    Sắp xếp theo số ghế (A1, A2...) để hiển thị sơ đồ ngăn nắp.
    """
    return db.session.query(Ticket)\
        .join(Seat)\
        .options(
            joinedload(Ticket.seat),
            joinedload(Ticket.ticket_type)
        )\
        .filter(Ticket.showing_id == showing_id)\
        .order_by(Seat.seat_number)\
        .all()


def search_events(keyword=None, category=None):
    query = Event.query

    if keyword:
        # Sử dụng ilike kết hợp với f-string để bọc ký tự đại diện %
        search = f"%{keyword}%"
        query = query.filter(
            Event.name.ilike(search) |
            Event.location_name.ilike(search)
        )

    # Chỉ lọc nếu người dùng chọn một danh mục cụ thể
    if category and category != "Tất cả":
        query = query.filter(Event.category == category)

    return query.all()


def get_all_categories():
    # Lấy danh sách các loại sự kiện duy nhất để đổ vào dropdown lọc
    return db.session.query(Event.category).distinct().all()