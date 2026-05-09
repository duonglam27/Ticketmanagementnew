from datetime import datetime, timedelta

from flask import render_template, request, redirect, url_for, flash, abort, current_app, jsonify
from flask_login import login_user as flask_login_user, logout_user, current_user, login_required
from app import dao, login, service, scheduler
from app.models import Order, Payment


def init_routes(app):
    @login.user_loader
    def load_user(user_id):
        # DAO chịu trách nhiệm lấy User từ DB
        return dao.get_user_by_id(user_id)

    @app.route('/')
    def home():
        keyword = request.args.get('q', '').strip()
        category = request.args.get('cat', '').strip()
        location = request.args.get('loc', '').strip()  # Lấy địa điểm từ query string

        events = dao.search_events_simple(keyword=keyword, category=category, location=location)
        categories = dao.get_all_categories()
        locations = dao.get_all_locations()

        return render_template('index.html',
                               events=events,
                               categories=categories,
                               locations=locations)

    @app.route('/register', methods=['GET', 'POST'])
    def user_register():
        if current_user.is_authenticated:
            return redirect(url_for('home'))

        err_msg = None
        if request.method == 'POST':
            # 1. Thu thập dữ liệu từ Form
            data = request.form
            password = data.get('password')
            confirm = data.get('confirm')
            avatar_file = request.files.get('avatar')

            # 2. Kiểm tra logic giao diện cơ bản (Validation)
            if password != confirm:
                err_msg = 'Mật khẩu xác nhận không khớp!'
            else:
                try:
                    # 3. Gọi Service để xử lý nghiệp vụ (Upload ảnh, Hash pass, DB)
                    service.register_user(
                        email=data.get('email'),
                        name=data.get('name'),
                        password=password,
                        avatar=avatar_file  # Truyền file thô vào Service
                    )
                    flash("Đăng ký thành công! Vui lòng đăng nhập.", "success")
                    return redirect(url_for('user_login'))
                except ValueError as e:
                    err_msg = str(e)
                except Exception:
                    err_msg = 'Hệ thống đang bận, vui lòng thử lại sau!'

        return render_template('register.html', err_msg=err_msg)

    @app.route('/login', methods=['GET', 'POST'])
    def user_login():
        if current_user.is_authenticated:
            return redirect(url_for('home'))

        err_msg = None
        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')

            user = service.authenticate_user(email, password)

            if user:
                flask_login_user(user)

                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)

                # PHÂN QUYỀN
                if user.is_admin():
                    return redirect(url_for('admin.admin_dashboard'))
                else:
                    return redirect(url_for('home'))

            err_msg = 'Email hoặc mật khẩu không chính xác'

        return render_template('login.html', err_msg=err_msg)

    @app.route('/logout')
    def user_logout():
        logout_user()
        return redirect(url_for('user_login'))

    @app.route('/organizer/create-event', methods=['GET', 'POST'])
    @login_required
    def event_create():
        if request.method == 'POST':
            print(request.form)
            try:
                new_event = service.create_event_complex_service(
                    data=request.form,
                    files=request.files,
                    user_id=current_user.id
                )
                flash(f"Thành công! '{new_event.name}' đã sẵn sàng bán vé.", "success")
                return redirect(url_for('organizer_dashboard'))
            except Exception as e:
                flash(f"Lỗi hệ thống: {str(e)}", "danger")

        return render_template('organizer/create_event.html')

    @app.route('/organizer/dashboard')
    @login_required
    def organizer_dashboard():
        data = service.get_dashboard_service(current_user.id)

        return render_template(
            'organizer/dashboard.html',
            summary=data["summary"],
            events=data["events"],
            active_page='dashboard'
        )

    @app.route('/organizer/events')
    @login_required
    def organizer_events():
        tab = request.args.get('tab', 'upcoming')

        events = service.get_my_events(current_user.id, tab)

        return render_template(
            'organizer/my_events.html',
            events=events,
            active_tab=tab
        )

    @app.route("/my-tickets")
    @login_required
    def my_tickets():
        # Gọi hàm trực tiếp từ service
        user_tickets = service.get_my_tickets_logic(user_id=current_user.id)

        return render_template("my_tickets.html", tickets=user_tickets)

    @app.route("/ticket/<int:ticket_id>")
    @login_required
    def view_ticket_detail(ticket_id):
        # Gọi Service xử lý logic (truyền ID vé và ID người dùng hiện tại)
        ticket = service.get_ticket_detail_logic(ticket_id, current_user.id)

        # Nếu không tìm thấy vé hoặc có lỗi logic
        if not ticket:
            abort(404)

        # Trả về giao diện chi tiết vé
        return render_template("ticket_detail.html", ticket=ticket)


    @app.route("/staff/scanner")
    @login_required
    def staff_scanner():
        # Kiểm tra nếu KHÔNG phải staff thì đuổi ra
        # if not current_user.is_staff():
        #     abort(403)  # Forbidden

        return render_template("staff/staff_scanner.html")

    # routes.py
    @app.route("/staff/verify-ticket", methods=["POST"])
    @login_required
    def verify_ticket():
        # if not current_user.is_staff():
        #     return jsonify({"success": False, "message": "Từ chối truy cập"}), 403

        data = request.json
        qr_data = data.get("qr_code")

        # Gọi service đã viết ở bước trước để check-in
        result = service.scan_and_checkin_logic(qr_data)

        return jsonify(result)

    @app.route('/organizer/reports')
    @login_required
    def organizer_report():

        return render_template('organizer/reports.html')



    @app.route('/organizer/reports/<int:event_id>')
    @login_required
    def reports_detail(event_id):
        data = service.get_event_report(event_id)

        return render_template(
            'organizer/reports_detail.html',
            data=data
        )

    @app.route('/organizer/terms')
    @login_required
    def terms():
        return render_template('organizer/setting.html')

    @app.route('/event/<int:event_id>')
    def event_detail(event_id):
        # Gọi service để lấy dữ liệu đã qua xử lý logic
        data = service.get_event_details(event_id)
        if not data:
            abort(404)

        return render_template('event_detail.html', **data)

    @app.route('/booking/<int:showing_id>')
    @login_required  # Cần đăng nhập để bắt đầu giữ chỗ
    def booking(showing_id):
        # 1. Lấy thông tin suất diễn và các loại vé đi kèm
        showing = dao.get_showing_by_id(showing_id)
        if not showing or showing.event.is_finished:
            flash("Suất diễn không tồn tại hoặc đã kết thúc.", "warning")
            return redirect(url_for('home'))

        # 2. Lấy danh sách các loại vé (TicketTypes) của suất diễn này
        ticket_types = dao.get_tickets_by_showing(showing_id)

        return render_template('booking.html',
                               showing=showing,
                               event=showing.event,
                               ticket_types=ticket_types)

    @app.route('/order/create', methods=['POST'])
    @login_required
    def create_order():
        ticket_type_id = request.form.get('ticket_type_id', type=int)
        quantity = request.form.get('quantity', default=1, type=int)

        if not ticket_type_id or quantity <= 0:
            flash("Thông tin đặt vé không hợp lệ.", "warning")
            return redirect(request.referrer or url_for('home'))

        try:
            # 1. Gọi Service (Nơi đã dùng with_for_update để chặn tranh chấp vé cuối)
            result = service.process_booking(
                user_id=current_user.id,
                ticket_type_id=ticket_type_id,
                quantity=quantity
            )

            if result['status'] == 'success':
                order_id = result['order_id']


                timeout = app.config.get('ORDER_TIMEOUT_MINUTES', 3)

                run_time = datetime.utcnow() + timedelta(minutes=timeout)

                # Hẹn giờ chạy hàm auto_cancel_order
                scheduler.add_job(
                    id=f'cancel_order_{order_id}',
                    func=service.auto_cancel_order,
                    trigger='date',
                    run_date=run_time,
                    args=[order_id]  # Truyền order_id vào hàm hủy
                )
                # ------------------------------------

                flash(f"Giữ chỗ thành công! Bạn có {timeout} phút để thanh toán.", "success")
                return redirect(url_for('order_detail', order_id=order_id))

            else:
                flash(result['message'], "danger")
                return redirect(request.referrer or url_for('home'))

        except Exception as e:
            app.logger.error(f"Order Creation Error: {str(e)}")
            flash("Hệ thống đang bận, vui lòng thử lại sau giây lát.", "danger")
            return redirect(request.referrer or url_for('home'))


    from app.models import PaymentStatus

    @app.route('/order/<int:order_id>')
    def order_detail(order_id):

        order = dao.get_order_by_id(order_id)

        remaining_seconds = 0

        latest_payment = None

        # =========================
        # LẤY PAYMENT MỚI NHẤT
        # =========================
        latest_payment = None

        if order.payment:
            latest_payment = order.payment

        # =========================
        # COUNTDOWN CHỈ KHI:
        # ORDER PENDING
        # VÀ CHƯA PAYMENT SUCCESS
        # =========================
        is_paid = (
                latest_payment
                and latest_payment.status == PaymentStatus.SUCCESS
        )

        if order.status.name == 'PENDING' and not is_paid:
            timeout_mins = current_app.config.get(
                'ORDER_TIMEOUT_MINUTES',
                1
            )

            now = datetime.utcnow()

            expiry_time = (
                    order.created_at +
                    timedelta(minutes=timeout_mins)
            )

            diff = (expiry_time - now).total_seconds()

            remaining_seconds = max(0, int(diff))

            print(
                f"DEBUG: "
                f"Created At: {order.created_at} | "
                f"Now UTC: {now} | "
                f"Diff: {diff}"
            )

        return render_template(
            'orders.html',
            order=order,
            remaining=remaining_seconds,
            latest_payment=latest_payment
        )

    @app.route('/order/cancel/<int:order_id>', methods=['POST'])
    @login_required
    def cancel_order(order_id):
        success, message = service.cancel_order_service(order_id, current_user.id)

        flash(message, "success" if success else "danger")

        # Nếu không có trang list orders, có thể dùng request.referrer
        # để quay lại trang trước đó người dùng đang đứng
        return redirect(request.referrer or url_for('home'))

    # @app.route('/order/process-payment/<int:order_id>', methods=['POST'])
    # @login_required
    # def process_payment(order_id):
    #     method = request.form.get('payment_method', 'CASH')
    #     success, message = service.process_payment_service(order_id, current_user.id, method)
    #
    #     if success:
    #         flash(message, "success")
    #         # Ví dụ: return redirect(url_for('my_tickets'))
    #         return redirect(url_for('home'))  # Tạm thời về Home
    #     else:
    #         flash(message, "danger")
    #         # Quay lại trang thanh toán để họ chọn lại phương thức payment
    #         return redirect(url_for('checkout', order_id=order_id))

    @app.route("/payment/momo/<int:order_id>", methods=["POST"])
    def momo_payment(order_id):

        response_data = service.create_momo_payment(
            order_id=order_id
        )

        if response_data.get("resultCode") == 0:
            return redirect(response_data["payUrl"])

        return jsonify(response_data), 400

    @app.route("/payment/momo-ipn", methods=["POST"])
    def momo_ipn():

        data = request.json

        service.handle_momo_ipn(data)

        return jsonify({
            "message": "success"
        })

    @app.route("/payment/momo-confirm")
    def momo_confirm():

        momo_order_id = request.args.get("orderId")

        payment = Payment.query.filter_by(
            gateway_order_id=momo_order_id
        ).first()

        if payment:
            return redirect(
                url_for(
                    "order_detail",
                    order_id=payment.order_id
                )
            )

        flash("Không tìm thấy đơn hàng", "danger")

        return redirect(url_for("home"))

    @app.route("/api/check-in", methods=["POST"])
    def check_in():
        # Nhận dữ liệu QR từ thiết bị scan gửi lên
        data = request.json
        qr_code = data.get("qr_code")

        if not qr_code:
            return jsonify({"success": False, "message": "Mã QR không hợp lệ"}), 400

        # Gọi service xử lý logic
        result = service.process_check_in(qr_code=qr_code)

        # Trả về kết quả theo mẫu chuẩn của bạn
        status_code = result.pop("code")
        return jsonify(result), status_code