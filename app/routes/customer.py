from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models_supabase import Sale, User
from app.utils import get_customer_summary

bp = Blueprint('customer', __name__, url_prefix='/customer')


@bp.route('/dashboard')
@login_required
def dashboard():
    """Customer dashboard - view purchases, payments, and advance balance"""
    if current_user.role != 'customer':
        return redirect(url_for('admin.dashboard'))
    
    customer_id = current_user.id
    summary = get_customer_summary(customer_id)
    
    total_purchases = summary.get('total_purchases', 0)
    total_payments = summary.get('total_payments', 0)
    pending_due = summary.get('pending_dues', 0)
    advance_balance = User.get_advance_balance(customer_id)
    
    customer_sales, _ = Sale.get_by_customer(customer_id, page=1, per_page=50, with_items=True)
    
    return render_template(
        'customer/dashboard.html',
        summary=summary,
        total_purchases=total_purchases,
        total_payments=total_payments,
        pending_due=pending_due,
        advance_balance=advance_balance,
        recent_sales=customer_sales
    )


@bp.route('/invoices')
@login_required
def invoices():
    """View all customer invoices"""
    if current_user.role != 'customer':
        return redirect(url_for('admin.dashboard'))
    
    customer_sales, _ = Sale.get_by_customer(current_user.id, page=1, per_page=100, with_items=True)
    
    return render_template(
        'customer/invoices.html',
        invoices=customer_sales,
        business_name='Adarsh Oil Mill'
    )


@bp.route('/invoice/<int:sale_id>')
@login_required
def view_invoice(sale_id):
    """
    View invoice as HTML (print-friendly)
    Users can use browser's "Print -> Save as PDF" to download
    """
    if current_user.role != 'customer':
        return redirect(url_for('admin.dashboard'))
    
    sale = Sale.get_by_id_with_items(sale_id)
    
    if not sale or sale.get('customer_id') != current_user.id:
        return redirect(url_for('customer.dashboard'))
    
    advance_balance = User.get_advance_balance(current_user.id)
    
    return render_template(
        'customer/invoice_pdf.html',
        sale=sale,
        business_name='Adarsh Oil Mill',
        advance_balance=advance_balance,
        current_user=current_user
    )


@bp.route('/advance-balance')
@login_required
def advance_balance():
    """View advance balance and transaction history"""
    if current_user.role != 'customer':
        return redirect(url_for('admin.dashboard'))
    
    current_balance = User.get_advance_balance(current_user.id)
    transactions = User.get_advance_transactions(current_user.id, limit=50)
    
    total_deposited = sum(t.get('amount', 0) for t in transactions if t.get('type') == 'deposit')
    total_redeemed = sum(t.get('amount', 0) for t in transactions if t.get('type') == 'redeem')
    total_withdrawn = sum(t.get('amount', 0) for t in transactions if t.get('type') == 'withdraw')
    
    return render_template(
        'customer/advance_balance.html',
        current_balance=current_balance,
        transactions=transactions,
        total_deposited=total_deposited,
        total_redeemed=total_redeemed,
        total_withdrawn=total_withdrawn
    )


@bp.route('/profile')
@login_required
def profile():
    """View customer profile"""
    if current_user.role != 'customer':
        return redirect(url_for('admin.dashboard'))
    
    return render_template(
        'customer/profile.html',
        customer=current_user
    )


# ============================================
# API ENDPOINTS FOR CUSTOMER (AJAX)
# ============================================

@bp.route('/api/advance-balance')
@login_required
def api_advance_balance():
    """Get current advance balance as JSON"""
    from flask import jsonify
    
    if current_user.role != 'customer':
        return jsonify({'error': 'Unauthorized'}), 403
    
    balance = User.get_advance_balance(current_user.id)
    return jsonify({
        'advance_balance': balance,
        'formatted_balance': f"Rs.{balance:,.2f}"
    })


@bp.route('/api/recent-invoices')
@login_required
def api_recent_invoices():
    """Get recent invoices as JSON"""
    from flask import jsonify
    
    if current_user.role != 'customer':
        return jsonify({'error': 'Unauthorized'}), 403
    
    sales, _ = Sale.get_by_customer(current_user.id, page=1, per_page=10, with_items=False)
    
    recent_invoices = [{
        'invoice_number': sale.get('invoice_number'),
        'date': sale.get('date'),
        'total_amount': sale.get('total_amount'),
        'payment_status': sale.get('payment_status'),
        'due_amount': sale.get('due_amount', 0)
    } for sale in sales]
    
    return jsonify(recent_invoices)


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_customer_dashboard_data(customer_id):
    """Helper to get all customer dashboard data"""
    summary = get_customer_summary(customer_id)
    advance_balance = User.get_advance_balance(customer_id)
    recent_sales, _ = Sale.get_by_customer(customer_id, page=1, per_page=5, with_items=False)
    
    return {
        'total_purchases': summary.get('total_purchases', 0),
        'total_payments': summary.get('total_payments', 0),
        'pending_due': summary.get('pending_dues', 0),
        'advance_balance': advance_balance,
        'recent_sales': recent_sales
    }
