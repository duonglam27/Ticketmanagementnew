from datetime import datetime, timedelta

from flask import render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_user as flask_login_user, logout_user, current_user, login_required
from app import dao, login, service, scheduler
from app.models import Order


def init_routes(app):
    @login.user_loader
    def load_user(user_id):
        # DAO chịu trách nhiệm lấy User từ DB
        return dao.get_user_by_id(user_id)


    @app.route('/')
    def home():
        # Lấy keyword từ ô search (name="q") và category từ link (name="cat")
        keyword = request.args.get('q', '').strip()
        category = request.args.get('cat', '').strip()

        # Nếu keyword và category đều rỗng, hàm này tự trả về All Events
        events = dao.search_events_simple(keyword=keyword, category=category)

        return render_template('index.html', events=events)

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

    @app.route('/order/<int:order_id>')
    def order_detail(order_id):
        order = dao.get_order_by_id(order_id)
        remaining_seconds = 0

        if order.status.name == 'PENDING':
            timeout_mins = current_app.config.get('ORDER_TIMEOUT_MINUTES', 1)

            # Dùng utcnow() để so sánh với order.created_at (cũng là UTC)
            now = datetime.utcnow()
            expiry_time = order.created_at + timedelta(minutes=timeout_mins)

            diff = (expiry_time - now).total_seconds()
            remaining_seconds = max(0, int(diff))

            # Kiểm tra Log: Nếu diff dương (ví dụ: 59) là chuẩn!
            print(f"DEBUG: Created At: {order.created_at} | Now UTC: {now} | Diff: {diff}")

        return render_template('orders.html', order=order, remaining=remaining_seconds)

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


    @app.route('/payment/momo/<int:order_id>', methods=['POST', 'GET'])
    def pay_with_momo(order_id):
        order = Order.query.get_or_404(order_id)

        # Test với chuỗi cực kỳ đơn giản trước
        msg = f"Thanhtoandonhang{order.id}"

        result = service.create_momo_payment(order.id, int(order.total_amount), msg)

        if result.get('resultCode') == 0:
            return redirect(result.get('payUrl'))
        else:
            # Nếu vẫn lỗi, in chuỗi raw_signature ra console để đối soát
            return f"Lỗi MoMo: {result.get('message')}. Chi tiết: {result}", 400