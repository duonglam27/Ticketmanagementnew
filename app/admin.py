from flask import Blueprint, render_template, abort, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
from . import admindao as dao

from app import db
from app.models import (
    Event, EventStatus,
    User, RoleEnum,
    Order, OrderStatus,
    Ticket, TicketStatus
)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# =========================
# 🔥 DASHBOARD
# =========================
@admin_bp.route('/')
@login_required
def admin_dashboard():
    if not current_user.is_admin():
        abort(403)

    events = dao.get_all_events()
    users = dao.get_all_users()
    orders = dao.get_paid_orders()

    total_revenue = dao.calculate_total_revenue(orders)

    return render_template(
        'admin/index.html',
        events=events,
        total_events=len(events),
        pending_events=dao.count_pending_events(events),
        approved_events=dao.count_approved_events(events),
        rejected_events=dao.count_rejected_events(events),
        total_users=len(users),
        total_revenue=total_revenue
    )


# =========================
# 📌 QUẢN LÝ EVENT
# =========================
@admin_bp.route('/events')
@login_required
def manage_events():
    if not current_user.is_admin():
        abort(403)

    status = request.args.get('status')
    category = request.args.get('category')

    events = dao.get_events(status, category)

    return render_template(
        'admin/events.html',
        events=events
    )


# =========================
# ✅ DUYỆT EVENT
# =========================
@admin_bp.route('/event/<int:event_id>/approve')
@login_required
def approve_event(event_id):
    if not current_user.is_admin():
        abort(403)

    dao.update_event_status(
        event_id,
        EventStatus.APPROVED
    )

    flash("Đã duyệt sự kiện!", "success")

    return redirect(url_for('admin.manage_events'))


# =========================
# ❌ TỪ CHỐI EVENT
# =========================
@admin_bp.route('/event/<int:event_id>/reject')
@login_required
def reject_event(event_id):
    if not current_user.is_admin():
        abort(403)

    dao.update_event_status(
        event_id,
        EventStatus.REJECTED
    )

    flash("Đã từ chối sự kiện!", "danger")

    return redirect(url_for('admin.manage_events'))


# =========================
# ⚠️ HỦY EVENT
# =========================
@admin_bp.route('/event/<int:event_id>/cancel')
@login_required
def cancel_event(event_id):
    if not current_user.is_admin():
        abort(403)

    dao.update_event_status(
        event_id,
        EventStatus.CANCELLED
    )

    flash("Đã hủy sự kiện!", "warning")

    return redirect(url_for('admin.manage_events'))

# =========================
# 📌 EVENT DETAIL
# =========================
@admin_bp.route('/event/<int:event_id>')
@login_required
def event_detail_admin(event_id):
    if not current_user.is_admin():
        abort(403)

    event = dao.get_event_detail(event_id)

    tickets = dao.get_event_tickets(event_id)

    return render_template(
        'admin/event_detail.html',
        event=event,
        tickets=tickets
    )

# =========================
# ❌ DELETE EVENT
# =========================
@admin_bp.route('/event/<int:event_id>/delete')
@login_required
def delete_event_admin(event_id):
    if not current_user.is_admin():
        abort(403)

    dao.delete_event(event_id)

    flash("Đã xóa event!", "danger")

    return redirect(url_for('admin.manage_events'))

# =========================
# 👤 QUẢN LÝ USER
# =========================
@admin_bp.route('/users')
@login_required
def manage_users():
    if not current_user.is_admin():
        abort(403)

    role = request.args.get('role')

    users = dao.get_users(role)

    return render_template(
        'admin/users.html',
        users=users
    )


# =========================
# 🔁 PHÂN QUYỀN USER
# =========================
@admin_bp.route('/user/<int:user_id>/role/<role>')
@login_required
def change_user_role(user_id, role):
    if not current_user.is_admin():
        abort(403)

    try:
        dao.change_user_role(user_id, role)

        flash("Cập nhật quyền thành công!", "success")

    except:
        flash("Vai trò không hợp lệ!", "danger")

    return redirect(url_for('admin.manage_users'))

# =========================
# CHUYỂN USER → ORGANIZER
# =========================
@admin_bp.route('/user/<int:user_id>/make-organizer')
@login_required
def make_organizer(user_id):
    if not current_user.is_admin():
        abort(403)

    dao.make_user_organizer(user_id)

    flash("Đã chuyển thành Organizer!", "success")

    return redirect(url_for('admin.manage_users'))


# =========================
# CHUYỂN ORGANIZER → USER
# =========================
@admin_bp.route('/user/<int:user_id>/make-user')
@login_required
def make_user(user_id):
    if not current_user.is_admin():
        abort(403)

    dao.make_organizer_user(user_id)

    flash("Đã chuyển về User!", "warning")

    return redirect(url_for('admin.manage_users'))

# =========================
# 🔒 KHÓA / MỞ USER
# =========================
@admin_bp.route('/user/<int:user_id>/toggle-active')
@login_required
def toggle_user(user_id):
    if not current_user.is_admin():
        abort(403)

    user = dao.get_user(user_id)

    success = dao.toggle_user_status(user)

    if not success:
        flash("Không thể khóa Admin!", "danger")
    else:
        flash("Cập nhật trạng thái user!", "success")

    return redirect(url_for('admin.manage_users'))


# =========================
# 👤 USER DETAIL
# =========================
@admin_bp.route('/user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def user_detail(user_id):
    if not current_user.is_admin():
        abort(403)

    user = dao.get_user(user_id)

    # UPDATE INFO
    if request.method == 'POST':

        dao.update_user_info(
            user,
            request.form.get('name'),
            request.form.get('email')
        )

        flash("Cập nhật user thành công!", "success")

        return redirect(
            url_for('admin.user_detail', user_id=user.id)
        )

    # =========================
    # PHÂN ROLE
    # =========================
    orders = []
    events = []

    if user.role == RoleEnum.USER:
        orders = dao.get_user_orders(user.id)

    elif user.role == RoleEnum.ORGANIZER:
        events = dao.get_organizer_events(user.id)

    return render_template(
        'admin/user_detail.html',
        user=user,
        orders=orders,
        events=events
    )


# =========================
# ❌ DELETE USER
# =========================
@admin_bp.route('/user/<int:user_id>/delete')
@login_required
def delete_user(user_id):
    if not current_user.is_admin():
        abort(403)

    user = dao.get_user(user_id)

    success = dao.remove_user(user)

    if not success:
        flash("Không thể xóa admin!", "danger")
    else:
        flash("Đã xóa user!", "success")

    return redirect(url_for('admin.manage_users'))


# =========================
# 👨‍💼 ORGANIZERS
# =========================
@admin_bp.route('/organizers')
@login_required
def organizers():
    if not current_user.is_admin():
        abort(403)

    organizers = dao.get_organizers()

    return render_template(
        'admin/organizers.html',
        organizers=organizers
    )


# =========================
# 💰 DOANH THU
# =========================
@admin_bp.route('/revenue')
@login_required
def revenue():
    if not current_user.is_admin():
        abort(403)

    # Orders đã thanh toán
    orders = dao.get_paid_orders()

    # Tổng doanh thu
    total_revenue = dao.get_total_revenue(orders)

    # Chart doanh thu
    chart_labels, chart_values = dao.get_revenue_by_day()

    return render_template(
        'admin/revenue.html',
        orders=orders,
        total_revenue=total_revenue,
        chart_labels=chart_labels,
        chart_values=chart_values
    )


# =========================
# 🎟️ QUẢN LÝ TICKET
# =========================
@admin_bp.route('/tickets')
@login_required
def manage_tickets():
    if not current_user.is_admin():
        abort(403)

    status = request.args.get('status')

    tickets = dao.get_tickets(status)

    return render_template(
        'admin/tickets.html',
        tickets=tickets
    )


# =========================
# 📷 CHECK-IN QR
# =========================
@admin_bp.route('/checkin/<int:ticket_id>')
@login_required
def checkin(ticket_id):
    if not current_user.is_admin():
        abort(403)

    ticket = dao.get_ticket(ticket_id)

    success = dao.checkin_ticket(ticket)

    if success:
        flash("Check-in thành công!", "success")
    else:
        flash("Vé đã được check-in trước đó!", "warning")

    return redirect(url_for('admin.manage_tickets'))

# =========================
# 📦 LIST ORDERS
# =========================
@admin_bp.route('/orders')
@login_required
def manage_orders():
    if not current_user.is_admin():
        abort(403)

    orders = dao.get_orders()

    return render_template(
        'admin/orders.html',
        orders=orders
    )


# =========================
# 📦 ORDER DETAIL
# =========================
@admin_bp.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    if not current_user.is_admin():
        abort(403)

    order = dao.get_order(order_id)

    return render_template(
        'admin/order_detail.html',
        order=order
    )


# =========================
# ❌ CANCEL ORDER
# =========================
@admin_bp.route('/order/<int:order_id>/cancel')
@login_required
def cancel_order(order_id):
    if not current_user.is_admin():
        abort(403)

    order = dao.get_order(order_id)

    dao.cancel_order(order)

    flash("Đã hủy đơn!", "warning")

    return redirect(
        url_for('admin.manage_orders')
    )