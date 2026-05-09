import time
from datetime import datetime
from flask import current_app, abort
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import RoleEnum, EventStatus, TicketType, TicketStatus, OrderStatus, Order
from app import dao, db
import cloudinary.uploader
from app import db
from app.config import Config
from app.models import (
    Order,
    Payment,
    PaymentMethod,
    PaymentStatus
)


# --- USER SERVICES ---

def register_user(email, name, password, avatar=None):
    if not email or not password:
        raise ValueError("Email và mật khẩu không được để trống")

    # 1. Logic kiểm tra (Giao tiếp với DAO)
    if dao.get_user_by_email(email):
        raise ValueError("Email đã tồn tại")

    # 2. Xử lý dữ liệu (Hash mật khẩu)
    hashed_password = generate_password_hash(password.strip())
    avatar_url = avatar or '/static/SystemPicture/avatardefault.jpg'

    # 3. Gọi DAO với tham số thô
    try:
        return dao.create_user(
            email=email,
            name=name,
            password_hash=hashed_password,
            role=RoleEnum.USER,
            avatar=avatar_url
        )
    except Exception as e:
        # Lỗi DB thực sự sẽ được xử lý ở đây nếu DAO raise lên
        raise e


def authenticate_user(email, password):
    if not email or not password:
        return None

    user = dao.get_user_by_email(email)
    if user and check_password_hash(user.password_hash, password):
        return user
    return None


def update_user_profile(user_id, name=None, avatar=None):
    user = dao.get_user_by_id(user_id)
    if not user:
        return None

    if name:
        user.name = name
    if avatar:
        user.avatar = avatar

    # Vì user là object đang nằm trong session, chỉ cần bảo DAO commit
    if dao.update_user_db():
        return user
    return None


def change_user_password(user_id, old_password, new_password):
    user = dao.get_user_by_id(user_id)
    if not user or not check_password_hash(user.password_hash, old_password):
        return False

    user.password_hash = generate_password_hash(new_password)
    return dao.update_user_db()

def get_my_tickets_logic(user_id):
    # 1. Lấy toàn bộ vé từ DAO (đã join qua Order)
    tickets = dao.get_user_tickets(user_id)

    # 2. Lọc lấy cả 3 trạng thái để kiểm tra
    # Bạn có thể thêm bất kỳ status nào muốn hiện vào list này
    valid_tickets = [
        t for t in tickets
        if t.status in [TicketStatus.SOLD, TicketStatus.USED, TicketStatus.AVAILABLE]
    ]

    return valid_tickets


def get_ticket_detail_logic(ticket_id, user_id):
    """
    Logic: Lấy vé và kiểm tra xem vé có thuộc về user_id này không.
    """
    ticket = dao.get_ticket_by_id(ticket_id)

    # 1. Nếu không tìm thấy vé
    if not ticket:
        return None

    # 2. Kiểm tra bảo mật: Ticket -> OrderItem -> Order -> user_id
    # Lưu ý: Cần kiểm tra kỹ các mối quan hệ (relationship) tránh lỗi NoneType
    try:
        owner_id = ticket.order_item.order.user_id
        if owner_id != user_id:
            abort(403)  # Không có quyền xem vé người khác
    except AttributeError:
        # Trường hợp dữ liệu rác, vé không gắn với đơn hàng nào
        abort(404)

    return ticket


def scan_and_checkin_logic(qr_code_data):
    """
    Logic nghiệp vụ cho nhân viên soát vé
    """
    ticket = dao.get_ticket_by_code(qr_code_data)

    if not ticket:
        return {"success": False, "message": "Vé không tồn tại trong hệ thống!"}

    # Kiểm tra nếu vé đã được dùng rồi
    if ticket.status == TicketStatus.USED:
        return {
            "success": False,
            "message": f"Vé này đã check-in vào lúc {ticket.checked_in_at.strftime('%H:%M')}"
        }

    # Kiểm tra nếu vé chưa thanh toán (Available nhưng chưa Sold)
    if ticket.status != TicketStatus.SOLD:
        return {"success": False, "message": "Vé này chưa được thanh toán thành công!"}

    # Nếu mọi thứ OK, tiến hành check-in
    dao.update_ticket_checkin(ticket.id)

    return {
        "success": True,
        "message": "Check-in thành công!",
        "event": ticket.showing.event.name,
        "seat": ticket.seat.seat_number if ticket.seat else "Tự do"
    }


def parse_seat_config(config_str):
    # config_str = "5 hàng, 10 cột"
    parts = [int(s) for s in config_str.split() if s.isdigit()]
    return parts[0], parts[1]  # Trả về (5, 10)


def create_event_complex_service(data, files, user_id):
    try:
        # 1. Upload ảnh (Đảm bảo các key 'poster', 'banner', 'org_logo' khớp với HTML)
        poster_url = upload_to_cloud(files.get('poster'), "posters")
        banner_url = upload_to_cloud(files.get('banner'), "banners")
        logo_url = upload_to_cloud(files.get('org_logo'), "logos")

        # 2. Tạo Event - Sửa data_dict thành data
        new_event = dao.create_event_nc(
            data={
                'name': data.get('name'),
                'description': data.get('description'),
                'category': data.get('category'),
                'location_name': data.get('location_name'),
                'city': data.get('city'),
                'event_type': data.get('event_type'),
                'image_poster': poster_url,
                'image_banner': banner_url,
                'organizer_brand': data.get('organizer_brand'),
                'organizer_logo': logo_url
            },
            organizer_id=user_id
        )
        db.session.flush()

        # 3. Lấy dữ liệu mảng
        start_times = data.getlist('start_time[]')
        seat_configs = data.getlist('seat_numbers[]')
        ticket_names = data.getlist('ticket_name[]')
        ticket_prices = data.getlist('ticket_price[]')

        for i in range(len(start_times)):
            if not start_times[i]: continue

            # A. Tạo Suất chiếu
            showing = dao.create_showing_nc(new_event.id, start_times[i])
            db.session.flush()

            # B. Tạo Loại vé
            price = float(ticket_prices[i]) if i < len(ticket_prices) else 0
            t_type = dao.create_ticket_type_nc(
                showing_id=showing.id,
                name=ticket_names[i] if i < len(ticket_names) else "Standard",
                base_price=price,
                total_quantity=0  # Sẽ cập nhật sau khi tạo ghế
            )
            db.session.flush()

            # C. Tạo Ghế và Vé (Tự động sinh QR code bên trong)
            if i < len(seat_configs) and "x" in seat_configs[i]:
                rows, cols = map(int, seat_configs[i].split('x'))

                # Sử dụng hàm helper v2 (nhớ bỏ db.session.commit() trong hàm đó)
                total_seats = dao.init_showing_seats_and_tickets(
                    showing.id, rows, cols, t_type.id
                )
                t_type.total_quantity = total_seats

        # CHỐT HẠ: Chỉ commit 1 lần duy nhất để bảo đảm an toàn dữ liệu
        db.session.commit()
        return new_event

    except Exception as e:
        db.session.rollback()
        print(f"Lỗi tạo sự kiện: {str(e)}")
        raise e

def upload_to_cloud(file, folder_name):
    """Helper xử lý upload an toàn"""
    if file and file.filename:
        res = cloudinary.uploader.upload(file, folder=f"ticket_app/{folder_name}")
        return res.get('secure_url')
    return "/static/images/default.jpg"


def get_dashboard_service(user_id):
    rows = dao.get_organizer_events_full(user_id)

    total_events = len(rows)
    total_tickets = 0
    sold_tickets = 0
    revenue = 0

    events = []

    for r in rows:
        event_id, name, banner, status, start_time, total, sold, rev = r

        total = total or 0
        sold = sold or 0
        rev = float(rev or 0)

        total_tickets += total
        sold_tickets += sold
        revenue += rev

        progress = int((sold / total) * 100) if total else 0

        events.append({
            "id": event_id,
            "name": name,
            "banner": banner,
            "status": status.value,
            "total": total,
            "sold": sold,
            "revenue": rev,
            "progress": progress
        })

    # chỉ lấy 5 event gần nhất
    events = events[:5]

    return {
        "summary": {
            "total_events": total_events,
            "total_tickets": total_tickets,
            "sold_tickets": sold_tickets,
            "revenue": revenue
        },
        "events": events
    }


def get_my_events(user_id, tab):
    rows = dao.get_organizer_events_full(user_id)

    result = []
    now = datetime.now()

    for r in rows:

        event_id, name, banner, status, start_time, total, sold, revenue = r

        # ===== NORMALIZE DATA (chống NULL từ DB) =====
        total = total or 0
        sold = sold or 0
        revenue = float(revenue or 0)
        banner = banner or "/static/images/default.jpg"

        progress = int((sold / total) * 100) if total else 0

        # ===== STATUS FLAGS =====
        status_value = status.value if hasattr(status, "value") else status

        is_pending = status_value == 'pending'
        is_approved = status_value == 'approved'
        is_rejected = status_value == 'rejected'

        is_upcoming = start_time and start_time >= now
        is_past = start_time and start_time < now

        # ===== FILTER LOGIC (chuẩn UX) =====
        if tab == 'pending':
            if not is_pending:
                continue

        elif tab == 'upcoming':
            if not (is_approved and is_upcoming):
                continue

        elif tab == 'past':
            if not (is_approved and is_past):
                continue

        elif tab == 'rejected':
            if not is_rejected:
                continue

        # 👉 tab = all (optional future)
        elif tab == 'all':
            pass

        # ===== MAP STATUS → LABEL UI =====
        if is_pending:
            status_label = "Chờ duyệt"
            status_class = "warning"
        elif is_rejected:
            status_label = "Bị từ chối"
            status_class = "danger"
        elif is_approved and is_upcoming:
            status_label = "Đang bán"
            status_class = "success"
        elif is_approved and is_past:
            status_label = "Đã kết thúc"
            status_class = "secondary"
        else:
            status_label = "Không xác định"
            status_class = "dark"

        # ===== FINAL DATA =====
        result.append({
            "id": event_id,
            "name": name,
            "banner": banner,
            "start_time": start_time,
            "status": status.value,
            "status_label": status_label,
            "status_class": status_class,
            "total": total,
            "sold": sold,
            "revenue": revenue,
            "progress": progress
        })

    # ===== SORT (rất quan trọng UX) =====
    result.sort(key=lambda x: x["start_time"] or datetime.max)

    return result


def get_event_details(event_id):
    event = dao.get_event_details(event_id)
    if not event:
        return None

    # Lọc danh sách tất cả các loại vé còn khả dụng (còn chỗ)
    available_tickets = []
    for s in event.showings:
        for tt in s.ticket_types:
            if (tt.total_quantity - tt.sold_quantity) > 0:
                available_tickets.append(tt)

    # Trả về kết quả đã được "xử lý sẵn" cho Frontend
    return {
        "event": event,
        "min_price": event.min_price,
        "is_finished": event.is_finished,
        # Nếu chỉ có đúng 1 loại vé khả dụng, flag này sẽ là True
        "is_single_ticket": len(available_tickets) == 1,
        "target_ticket_id": available_tickets[0].id if len(available_tickets) == 1 else None
    }


def get_event_report(event_id):
    event = dao.get_event_details(event_id)

    summary = dao.get_report_summary(event_id)
    revenue_by_day = dao.get_revenue_by_day(event_id)
    ticket_stats = dao.get_ticket_type_stats(event_id)

    return {
        "event": event,
        "summary": {
            "total": summary.total or 0,
            "sold": summary.sold or 0,
            "revenue": float(summary.revenue or 0),
            "percent": int((summary.sold / summary.total) * 100) if summary.total else 0
        },
        "chart": revenue_by_day,
        "tickets": ticket_stats
    }


# Order
def process_booking(user_id, ticket_type_id, quantity):
    try:
        print("\n========== START BOOKING ==========")
        print("USER ID:", user_id)
        print("TICKET TYPE ID:", ticket_type_id)
        print("QUANTITY:", quantity)

        # =====================================================
        # 1. LOCK TicketType
        # =====================================================
        tt = TicketType.query.with_for_update().get(ticket_type_id)

        print("\n[1] TICKET TYPE:")
        print("TT =", tt)

        if tt:
            print("TT.ID =", tt.id)
            print("TT.NAME =", tt.name)
            print("TT.TOTAL =", tt.total_quantity)
            print("TT.SOLD =", tt.sold_quantity)
            print("TT.REMAIN =", tt.total_quantity - tt.sold_quantity)

        # =====================================================
        # CHECK STOCK
        # =====================================================
        if not tt:
            print("❌ TicketType không tồn tại")
            return {
                'status': 'error',
                'message': 'Không tìm thấy loại vé!'
            }

        remain = tt.total_quantity - tt.sold_quantity

        print("\n[2] CHECK REMAIN:")
        print("REMAIN =", remain)

        if remain < quantity:
            print("❌ Không đủ vé")
            return {
                'status': 'error',
                'message': 'Rất tiếc, không đủ vé!'
            }

        # =====================================================
        # 3. GET AVAILABLE TICKETS
        # =====================================================
        tickets_to_lock = dao.get_available_tickets_by_type(
            ticket_type_id,
            limit=quantity
        )

        print("\n[3] AVAILABLE TICKETS:")
        print("COUNT =", len(tickets_to_lock))

        for t in tickets_to_lock:
            print(
                "TICKET:",
                t.id,
                t.ticket_code,
                t.status
            )

        if len(tickets_to_lock) < quantity:
            print("❌ Vé bị người khác giữ trước")
            return {
                'status': 'error',
                'message': 'Vé vừa mới bị người khác đặt mất!'
            }

        # =====================================================
        # 4. PRICE
        # =====================================================
        unit_price = tt.get_price()

        print("\n[4] PRICE:")
        print("UNIT PRICE =", unit_price)

        # =====================================================
        # 5. BUILD ORDER ITEMS
        # =====================================================
        ticket_items_data = []

        for t in tickets_to_lock:
            item = {
                'ticket_id': t.id,
                'price': unit_price
            }

            ticket_items_data.append(item)

        print("\n[5] ORDER ITEMS:")
        print(ticket_items_data)

        # =====================================================
        # 6. CREATE ORDER
        # =====================================================
        total_amount = unit_price * quantity

        print("\n[6] CREATE ORDER:")
        print("TOTAL =", total_amount)

        new_order = dao.create_order(
            user_id=user_id,
            total_amount=total_amount,
            ticket_items=ticket_items_data
        )

        print("NEW ORDER =", new_order)
        print("NEW ORDER ID =", new_order.id)

        # =====================================================
        # 7. UPDATE SOLD QUANTITY
        # =====================================================
        print("\n[7] UPDATE SOLD:")

        before = tt.sold_quantity

        tt.sold_quantity += quantity

        after = tt.sold_quantity

        print("BEFORE =", before)
        print("AFTER =", after)

        # =====================================================
        # 8. COMMIT
        # =====================================================
        print("\n[8] COMMIT DB")

        db.session.commit()

        print("✅ BOOKING SUCCESS")
        print("========== END ==========\n")

        return {
            'status': 'success',
            'order_id': new_order.id
        }

    except Exception as e:
        print("\n❌ CRITICAL ERROR")
        print(type(e))
        print(str(e))

        db.session.rollback()

        print("ROLLBACK DONE")
        print("========== END ==========\n")

        return {
            'status': 'error',
            'message': str(e)
        }


def cancel_order_service(order_id, user_id):
    try:
        order = dao.get_order_by_id(order_id)
        if not order or order.user_id != user_id:
            return False, "Đơn hàng không tồn tại."

        if order.status == OrderStatus.CANCELLED:
            return False, "Đơn hàng đã được hủy rồi."

        for item in order.items:
            ticket = item.ticket
            if ticket:
                # 1. Hoàn trạng thái vé
                ticket.status = TicketStatus.AVAILABLE

                # 2. Hoàn số lượng cho kho
                if ticket.ticket_type:
                    ticket.ticket_type.sold_quantity -= 1

            # 3. QUAN TRỌNG: Xóa item này để không bị lỗi Unique khi mua lại vé này
            db.session.delete(item)

        order.status = OrderStatus.CANCELLED
        db.session.commit()
        return True, "Hủy đơn và giải phóng vé thành công."
    except Exception as e:
        db.session.rollback()
        return False, str(e)


from app import create_app


def auto_cancel_order(order_id):
    # Lấy đối tượng app thực sự từ proxy current_app

    with create_app().app_context():
        print(f"--- ĐANG THỰC THI HỦY ĐƠN #{order_id} ---")
        try:
            # Truy vấn đơn hàng
            order = Order.query.get(order_id)

            # Kiểm tra trạng thái bằng .name hoặc giá trị Enum
            if order and order.status == OrderStatus.PENDING:
                for item in order.items:
                    # 1. Trả lại trạng thái vé trống
                    item.ticket.status = TicketStatus.AVAILABLE

                    # 2. Hoàn lại số lượng đã bán cho loại vé (Chống tranh chấp)
                    if item.ticket.ticket_type:
                        item.ticket.ticket_type.sold_quantity -= 1

                    # 3. Xóa OrderItem để tránh lỗi Duplicate entry '27'
                    db.session.delete(item)

                # 4. Cập nhật trạng thái đơn hàng thành CANCELLED
                order.status = OrderStatus.CANCELLED

                db.session.commit()
                print(f"--- THÀNH CÔNG: Đã hủy đơn #{order_id} và giải phóng vé ---")
            else:
                print(f"--- BỎ QUA: Đơn #{order_id} không còn ở trạng thái chờ ---")

        except Exception as e:
            db.session.rollback()
            print(f"--- LỖI HỆ THỐNG KHI HỦY: {str(e)} ---")


# def process_payment_service(order_id, user_id, payment_method):
#     try:
#         order = dao.get_order_for_payment(order_id)
#
#         # 1. Kiểm tra đơn hàng
#         if not order or order.user_id != user_id:
#             return False, "Đơn hàng không hợp lệ."
#
#         if order.status == OrderStatus.PAID:
#             return False, "Đơn hàng này đã được thanh toán rồi."
#
#         # 2. Kiểm tra thời hạn thanh toán (Ví dụ: Lâm chỉ cho giữ vé trong 10 phút)
#         # Giả sử Lâm có trường created_at trong Order
#         # if (datetime.utcnow() - order.created_at).minutes > 10:
#         #    return False, "Giao dịch đã hết hạn thanh toán."
#
#         # 3. Gọi API thanh toán (Zalopay/VNPAY/Momo) ở đây nếu cần
#         # Ở bước này, mình giả định thanh toán giả lập hoặc thành công
#         payment_success = True
#
#         if payment_success:
#             dao.complete_payment_db(order, payment_method)
#             db.session.commit()
#             return True, "Thanh toán thành công! Chúc Lâm xem show vui vẻ."
#
#         return False, "Thanh toán thất bại từ phía ngân hàng."
#
#     except Exception as e:
#         db.session.rollback()
#         return False, str(e)

import hashlib
import hmac
import json
import requests
import uuid

from datetime import datetime


def create_momo_payment(order_id):
    order = Order.query.get(order_id)

    if not order:
        raise ValueError("Order không tồn tại")

    endpoint = "https://test-payment.momo.vn/v2/gateway/api/create"

    amount = str(int(order.total_amount))

    request_id = str(uuid.uuid4())

    order_id_momo = f"ORD{order.id}-{request_id[:8]}"

    order_info = f"Thanh toan don hang {order.id}"

    raw_signature = (
        f"accessKey={Config.MOMO_ACCESS_KEY}"
        f"&amount={amount}"
        f"&extraData="
        f"&ipnUrl={Config.BASE_URL}/payment/momo-ipn"
        f"&orderId={order_id_momo}"
        f"&orderInfo={order_info}"
        f"&partnerCode={Config.MOMO_PARTNER_CODE}"
        f"&redirectUrl={Config.BASE_URL}/payment/momo-confirm"
        f"&requestId={request_id}"
        f"&requestType=captureWallet"
    )

    signature = hmac.new(
        Config.MOMO_SECRET_KEY.encode("utf-8"),
        raw_signature.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    payload = {
        "partnerCode": Config.MOMO_PARTNER_CODE,
        "partnerName": "Test",
        "storeId": "MomoStore",
        "requestId": request_id,
        "amount": amount,
        "orderId": order_id_momo,
        "orderInfo": order_info,
        "redirectUrl": f"{Config.BASE_URL}/payment/momo-confirm",
        "ipnUrl": f"{Config.BASE_URL}/payment/momo-ipn",
        "lang": "vi",
        "extraData": "",
        "requestType": "captureWallet",
        "signature": signature
    }

    data = json.dumps(payload)

    response = requests.post(
        endpoint,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(data))
        }
    )

    response_data = response.json()

    # ======================
    # CREATE PAYMENT DB
    # ======================

    payment = Payment(
        order_id=order.id,
        amount=float(amount),
        method=PaymentMethod.MOMO,
        status=PaymentStatus.PENDING,

        transaction_id=request_id,

        gateway_order_id=order_id_momo,

        gateway_response=json.dumps(response_data)
    )

    if response_data.get("resultCode") != 0:
        payment.status = PaymentStatus.FAILED

    db.session.add(payment)
    db.session.commit()

    return response_data


def handle_momo_ipn(data):
    request_id = data.get("requestId")
    result_code = data.get("resultCode")
    trans_id = data.get("transId")

    payment = Payment.query.filter_by(transaction_id=request_id).first()

    if not payment:
        return False

    if payment.status == PaymentStatus.SUCCESS:
        return True

    payment.gateway_response = json.dumps(data)
    payment.gateway_transaction_id = str(trans_id)

    # =========================================================
    # XỬ LÝ KHI THANH TOÁN THÀNH CÔNG (result_code == 0)
    # =========================================================
    if result_code == 0:
        payment.status = PaymentStatus.SUCCESS
        payment.paid_at = datetime.utcnow()

        if payment.order:
            # 1. Cập nhật trạng thái Đơn hàng
            payment.order.status = OrderStatus.PAID

            # 2. CẬP NHẬT TRẠNG THÁI TỪNG VÉ SANG SOLD
            # Duyệt qua tất cả các item trong đơn hàng
            for item in payment.order.items:
                if item.ticket:
                    item.ticket.status = TicketStatus.SOLD
                    # (Tùy chọn) Ghi nhận ngày bán vào vé nếu có trường sold_at
                    # item.ticket.sold_at = datetime.utcnow()

            print(f"--- Đã chuyển trạng thái vé sang SOLD cho đơn hàng #{payment.order.id} ---")

    # =========================
    # KHI THANH TOÁN THẤT BẠI
    # =========================
    else:
        payment.status = PaymentStatus.FAILED
        # Lưu ý: Bạn có thể chọn giữ Order ở trạng thái PENDING
        # để khách thanh toán lại, hoặc hủy luôn tùy logic app.

    db.session.commit()
    return True

def process_check_in(self, qr_code, current_user_id=None):
    ticket = self.ticket_dao.get_by_qr(qr_code)

    # 1. Kiểm tra tồn tại
    if not ticket:
        return {"success": False, "message": "Vé không tồn tại", "code": 404}

    # 2. Kiểm tra quyền sở hữu (Security check cho User)
    # Truy xuất user_id thông qua mối quan hệ Ticket -> OrderItem -> Order
    if ticket.order_item and ticket.order_item.order:
        owner_id = ticket.order_item.order.user_id
        if current_user_id and owner_id != current_user_id:
            return {"success": False, "message": "Vé này không thuộc về bạn", "code": 403}
    else:
        return {"success": False, "message": "Vé chưa được thanh toán hoàn tất", "code": 400}

    # 3. Kiểm tra trạng thái vé
    if ticket.status == TicketStatus.USED:
        return {"success": False, "message": "Vé đã được sử dụng trước đó", "code": 400}

    if ticket.status != TicketStatus.SOLD:
        return {"success": False, "message": "Vé không ở trạng thái có thể check-in", "code": 400}

    # 4. Thực hiện Check-in
    updated_ticket = self.ticket_dao.update_status(
        ticket,
        TicketStatus.USED,
        check_in_time=datetime.utcnow()
    )

    return {
        "success": True,
        "message": "Check-in thành công",
        "ticket_code": updated_ticket.ticket_code,
        "code": 200
    }
