from werkzeug.security import generate_password_hash, check_password_hash
from app.models import RoleEnum
from app import dao, db
import cloudinary.uploader
import cloudinary.uploader

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




def create_event_complex_service(data, files, user_id):
    try:
        # 1. Xử lý File thật qua Cloudinary
        poster_url = upload_to_cloud(files.get('poster'), "posters")
        banner_url = upload_to_cloud(files.get('banner'), "banners")
        logo_url = upload_to_cloud(files.get('org_logo'), "logos")

        # 2. Khởi tạo Event (Sử dụng hàm _nc - Non Commit)
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
        db.session.flush()  # Lấy ID để dùng cho Showing

        # 3. Lặp qua các Suất diễn (Showings)
        start_times = data.getlist('start_time')
        seat_data = data.getlist('seat_numbers')  # Chuỗi "A1, A2, B1"

        for i in range(len(start_times)):
            if not start_times[i]: continue

            # Tạo Suất diễn
            showing = dao.create_showing_nc(new_event.id, start_times[i])
            db.session.flush()

            # 4. Xử lý Ghế ngồi (Seats) - Dùng Bulk Insert
            if i < len(seat_data) and seat_data[i]:
                # Tách chuỗi ghế thành list ['A1', 'A2']
                seats_list = [s.strip() for s in seat_data[i].split(',') if s.strip()]

                # DAO này sẽ dùng bulk_insert_mappings
                created_seats = dao.bulk_create_seats_nc(showing.id, seats_list)
                db.session.flush()

                # 5. Tự động tạo Loại vé mặc định (Nếu Form của bạn chưa chia loại vé)
                # Hoặc lặp qua TicketType nếu Form của bạn có phần nhập Giá vé
                t_type = dao.create_ticket_type_nc(
                    showing_id=showing.id,
                    name="Vé Tiêu Chuẩn",
                    price=float(data.get('base_price', 0)),
                    quantity=len(seats_list)
                )
                db.session.flush()

                # 6. Khởi tạo các bản ghi Vé (Tickets) tương ứng với từng ghế
                # Đây là bước quan trọng để khách hàng có thể "chọn" vé
                dao.init_tickets_bulk_nc(showing.id, t_type.id, created_seats)

        #Lưu tất cả dữ liệu sạch vào Database
        db.session.commit()
        return new_event

    except Exception as e:
        db.session.rollback()
        print(f"CRITICAL ERROR: {str(e)}")
        raise e


def upload_to_cloud(file, folder_name):
    """Helper xử lý upload an toàn"""
    if file and file.filename:
        res = cloudinary.uploader.upload(file, folder=f"ticket_app/{folder_name}")
        return res.get('secure_url')
    return "/static/images/default.jpg"