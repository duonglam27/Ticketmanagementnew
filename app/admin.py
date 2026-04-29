from flask import Blueprint, render_template, abort, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime

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

    events = Event.query.all()
    users = User.query.all()
    orders = Order.query.filter(Order.status == OrderStatus.PAID).all()

    total_revenue = sum(o.total_amount for o in orders)

    return render_template(
        'admin/index.html',
        events=events,
        total_events=len(events),
        pending_events=len([e for e in events if e.status == EventStatus.PENDING]),
        approved_events=len([e for e in events if e.status == EventStatus.APPROVED]),
        rejected_events=len([e for e in events if e.status == EventStatus.REJECTED]),
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

    query = Event.query

    if status:
        query = query.filter(Event.status == EventStatus(status))

    if category:
        query = query.filter(Event.category == category)

    events = query.order_by(Event.created_at.desc()).all()

    return render_template('admin/events.html', events=events)


# =========================
# ✅ DUYỆT EVENT
# =========================
@admin_bp.route('/event/<int:event_id>/approve')
@login_required
def approve_event(event_id):
    if not current_user.is_admin():
        abort(403)

    event = Event.query.get_or_404(event_id)
    event.status = EventStatus.APPROVED

    db.session.commit()
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

    event = Event.query.get_or_404(event_id)
    event.status = EventStatus.REJECTED

    db.session.commit()
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

    event = Event.query.get_or_404(event_id)
    event.status = EventStatus.CANCELLED

    db.session.commit()
    flash("Đã hủy sự kiện!", "warning")

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

    query = User.query

    if role:
        query = query.filter(User.role == RoleEnum(role))

    users = query.all()

    return render_template('admin/users.html', users=users)


# =========================
# 🔁 PHÂN QUYỀN USER
# =========================
@admin_bp.route('/user/<int:user_id>/role/<role>')
@login_required
def change_user_role(user_id, role):
    if not current_user.is_admin():
        abort(403)

    user = User.query.get_or_404(user_id)

    try:
        user.role = RoleEnum(role)
        db.session.commit()
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

    user = User.query.get_or_404(user_id)

    user.role = RoleEnum.ORGANIZER
    db.session.commit()

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

    user = User.query.get_or_404(user_id)

    user.role = RoleEnum.USER
    db.session.commit()

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

    user = User.query.get_or_404(user_id)

    # ❌ Không cho khóa admin
    if user.role == RoleEnum.ADMIN:
        flash("Không thể khóa Admin!", "danger")
        return redirect(url_for('admin.manage_users'))

    user.is_active = not user.is_active
    db.session.commit()

    flash("Cập nhật trạng thái user!", "success")
    return redirect(url_for('admin.manage_users'))

# =========================
# 💰 DOANH THU
# =========================
@admin_bp.route('/revenue')
@login_required
def revenue():
    if not current_user.is_admin():
        abort(403)

    orders = Order.query.filter(Order.status == OrderStatus.PAID).all()

    total_revenue = sum(o.total_amount for o in orders)

    return render_template(
        'admin/revenue.html',
        orders=orders,
        total_revenue=total_revenue
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

    query = Ticket.query

    if status:
        query = query.filter(Ticket.status == TicketStatus(status))

    tickets = query.all()

    return render_template('admin/tickets.html', tickets=tickets)


# =========================
# 📷 CHECK-IN QR
# =========================
@admin_bp.route('/checkin/<int:ticket_id>')
@login_required
def checkin(ticket_id):
    if not current_user.is_admin():
        abort(403)

    ticket = Ticket.query.get_or_404(ticket_id)

    if ticket.checked_in:
        flash("Vé đã được check-in trước đó!", "warning")
    else:
        ticket.checked_in = True
        ticket.checked_in_at = datetime.now()
        db.session.commit()
        flash("Check-in thành công!", "success")

    return redirect(url_for('admin.manage_tickets'))