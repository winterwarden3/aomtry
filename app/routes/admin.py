from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
import pandas as pd
import pytz
import uuid
from app.supabase_client import supabase
from app.models_supabase import User, Sale, Expense, Product, Payment
from app.utils import (
    admin_required, get_today_stats, get_monthly_stats, get_pending_dues,
    generate_invoice_number, get_customer_summary, format_currency,
    get_weekly_sales_data, get_monthly_sales_data, get_payment_channel_data, get_nepal_time,
    build_byproduct_note, parse_exchange_from_note, apply_byproduct_exchange_to_line_items,
    is_mustard_extraction_product, is_others_product, is_others_or_dalbanai_product, Pagination,format_time_ago
)
from datetime import datetime, timedelta
from app.brevo_service import send_invoice_email
from app.config import Config

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    
    from datetime import datetime, timedelta
    import calendar
    import pytz
    
    nepal_tz = pytz.timezone('Asia/Kathmandu')
    now = datetime.now(nepal_tz)
    today = now.date()
    
    # Get current month name and abbreviation
    current_month_name = now.strftime('%B')      # "June"
    current_month_abbr = now.strftime('%b').upper()  # "JUN"
    current_year = now.year
    
    # TODAY'S STATS (Fixed - using Nepal date directly)
    today_str = today.strftime('%Y-%m-%d')
    tomorrow = today + timedelta(days=1)
    tomorrow_str = tomorrow.strftime('%Y-%m-%d')
    
    today_start = f"{today_str}T00:00:00"
    today_end = f"{tomorrow_str}T00:00:00"
    
    today_sales = Sale.get_total_by_date_range(today_start, today_end)
    today_sales_count = Sale.get_count_by_date_range(today_start, today_end)
    today_expenses = Expense.get_total_by_date_range(today_start, today_end)
    today_expenses_count = Expense.get_count_by_date_range(today_start, today_end)
    today_profit = today_sales - today_expenses
    
    # MONTHLY STATS (Fixed - using Nepal date directly)
    month_start_str = f"{today.year}-{today.month:02d}-01T00:00:00"
    
    # Get next month's first day
    if today.month == 12:
        next_month_start = f"{today.year + 1}-01-01T00:00:00"
    else:
        next_month_start = f"{today.year}-{today.month + 1:02d}-01T00:00:00"
    
    monthly_sales = Sale.get_total_by_date_range(month_start_str, next_month_start)
    monthly_expenses = Expense.get_total_by_date_range(month_start_str, next_month_start)
    monthly_profit = monthly_sales - monthly_expenses
    
    # OTHER STATS
    pending_dues = get_pending_dues()
    total_customers = User.count_customers()
    new_customers_this_month = User.count_new_customers_since(datetime(today.year, today.month, 1))
    
    # RECENT ACTIVITIES
    recent_activities = []
    
    # ============================================================
    # FIXED: format_time_ago with source parameter
    # ============================================================
    def format_time_ago(date_val, source='auto'):
        """Format time ago with support for both UTC and Nepal time dates"""
        if not date_val:
            return "Unknown"
        try:
            import pytz
            from datetime import datetime
            
            nepal_tz = pytz.timezone('Asia/Kathmandu')
            now_nepal = datetime.now(nepal_tz)
            
            # Parse the date value
            if isinstance(date_val, str):
                # Handle different date formats
                if 'T' in date_val:
                    date_val = date_val.replace('T', ' ').replace('Z', '').split('.')[0]
                naive_date = datetime.strptime(date_val[:19], '%Y-%m-%d %H:%M:%S')
            else:
                # If it's already a datetime object
                naive_date = date_val
            
            # Determine timezone based on source
            if source == 'sale':
                # Sale dates are already in Nepal time
                if naive_date.tzinfo is None:
                    date_nepal = nepal_tz.localize(naive_date)
                else:
                    date_nepal = naive_date.astimezone(nepal_tz)
            elif source == 'expense':
                # Expense dates from Supabase are in UTC
                if naive_date.tzinfo is None:
                    utc_tz = pytz.timezone('UTC')
                    date_utc = utc_tz.localize(naive_date)
                    date_nepal = date_utc.astimezone(nepal_tz)
                else:
                    date_nepal = naive_date.astimezone(nepal_tz)
            else:
                # Default: treat as UTC (for customers and anything else from Supabase)
                if naive_date.tzinfo is None:
                    utc_tz = pytz.timezone('UTC')
                    date_utc = utc_tz.localize(naive_date)
                    date_nepal = date_utc.astimezone(nepal_tz)
                else:
                    date_nepal = naive_date.astimezone(nepal_tz)
            
            # Calculate difference
            diff = now_nepal - date_nepal
            seconds = diff.total_seconds()
            
            # Format the output
            if seconds < 0:
                return "Just now"
            elif seconds < 60:
                return "Just now"
            elif seconds < 3600:
                mins = int(seconds // 60)
                return f"{mins} minute{'s' if mins > 1 else ''} ago"
            elif seconds < 86400:
                hours = int(seconds // 3600)
                return f"{hours} hour{'s' if hours > 1 else ''} ago"
            elif seconds < 2592000:  # 30 days
                days = int(seconds // 86400)
                return f"{days} day{'s' if days > 1 else ''} ago"
            else:
                return date_nepal.strftime('%b %d, %Y')
                
        except Exception as e:
            print(f"Error formatting time: {e}")
            return str(date_val)[:10] if date_val else "Unknown"
    
    # ============================================================
    # Recent Sales - PASS source='sale' because sale dates are in Nepal time
    # ============================================================
    recent_sales = Sale.get_recent(5)

    # Batch fetch all customers at once
    customer_ids = [sale.get('customer_id') for sale in recent_sales if sale.get('customer_id')]
    customers = {}
    if customer_ids:
        # Fetch all customers in one query
        response = supabase.table("users").select("id, name").in_("id", customer_ids).execute()
        customers = {c['id']: c for c in response.data}

    for sale in recent_sales:
        customer_id = sale.get('customer_id')
        if customer_id and customer_id in customers:
            customer_name = customers[customer_id].get('name')
        else:
            customer_name = "Walk-in Customer"
        
        recent_activities.append({
            'icon': 'bi bi-cart-check',
            'icon_bg': 'rgba(34,197,94,0.1)',
            'icon_color': '#16a34a',
            'title': 'New Sale',
            'description': f"Invoice #{sale.get('invoice_number')} - Rs.{sale.get('total_amount', 0):,.2f} from {customer_name}",
            'time_ago': format_time_ago(sale.get('date'), source='sale'),  # ← FIXED: pass source='sale'
            'timestamp': sale.get('date')
        })
    
    # ============================================================
    # Recent Expenses - PASS source='expense' (UTC from Supabase)
    # ============================================================
    recent_expenses = Expense.get_recent(5)
    for expense in recent_expenses:
        recent_activities.append({
            'icon': 'bi bi-receipt',
            'icon_bg': 'rgba(220,38,38,0.1)',
            'icon_color': '#dc2626',
            'title': 'New Expense',
            'description': f"{expense.get('category')} - Rs.{expense.get('amount', 0):,.2f}",
            'time_ago': format_time_ago(expense.get('date'), source='sale'), 
            'timestamp': expense.get('date')
        })
    
    # ============================================================
    # Recent Customers - NO source needed (defaults to UTC)
    # ============================================================
    recent_customers = User.get_all_customers()[:5]
    for customer in recent_customers:
        recent_activities.append({
            'icon': 'bi bi-person-plus',
            'icon_bg': 'rgba(59,130,246,0.1)',
            'icon_color': '#3b82f6',
            'title': 'New Customer',
            'description': f"{customer.get('name')} added to system",
            'time_ago': format_time_ago(customer.get('created_at')),  # ← Works correctly (UTC)
            'timestamp': customer.get('created_at')
        })
    
    # Sort activities by timestamp (newest first)
    recent_activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    recent_activities = recent_activities[:10]
    
    return render_template(
        'admin/dashboard.html',
        today_sales=today_sales,
        today_sales_count=today_sales_count,
        today_expenses=today_expenses,
        today_expenses_count=today_expenses_count,
        today_profit=today_profit,
        monthly_sales=monthly_sales,
        monthly_expenses=monthly_expenses,
        monthly_profit=monthly_profit,
        pending_dues=pending_dues,
        total_customers=total_customers,
        new_customers_this_month=new_customers_this_month,
        recent_activities=recent_activities,
        business_name=Config.BUSINESS_NAME,
        current_month_name=current_month_name,
        current_month_abbr=current_month_abbr,
        current_year=current_year
    )





@bp.route('/sales')
@login_required
@admin_required
def sales_list():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    sales_data, total = Sale.get_all_with_items(page, 10, search)
    
    status_counts = Sale.count_all_payment_statuses()
    paid_sales_count = status_counts['paid']
    pending_sales_count = status_counts['pending']
    advance_sales_count = status_counts['advance']
    
    sales = Pagination(sales_data, page, 10, total)
    
    return render_template(
        'admin/sales.html',
        sales=sales,
        search=search,
        paid_sales_count=paid_sales_count,
        pending_sales_count=pending_sales_count,
        advance_sales_count=advance_sales_count,
        business_name=Config.BUSINESS_NAME
    )




@bp.route('/sales/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_sale():
    from app.utils import calculate_payment_status, generate_invoice_number
    from app.config import Config
    from datetime import datetime
    from app.models_supabase import User
    import secrets
    from flask import session
    
    customer_advance_balance = 0
    selected_customer_id = None
    
    # GET request - show form
    if request.method == 'GET':
        customer_id = request.args.get('customer_id')
        if customer_id:
            selected_customer_id = int(customer_id)
            customer_advance_balance = User.get_advance_balance(selected_customer_id)
        
        # Generate unique token for this form session
        session['sale_form_token'] = secrets.token_hex(16)
        
        return render_template('admin/add_sale.html', 
                             customer_advance_balance=customer_advance_balance, 
                             selected_customer_id=selected_customer_id,
                             form_token=session['sale_form_token'])
    
    # POST request - process form
    if request.method == 'POST':
        # Check if AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # ========== PREVENT DUPLICATE SUBMISSION ==========
        submitted_token = request.form.get('form_token')
        if not submitted_token or submitted_token != session.get('sale_form_token'):
            if is_ajax:
                return jsonify({'success': False, 'error': 'Form already submitted or expired. Please refresh the page.'}), 400
            flash('Form already submitted or expired. Please try again.', 'danger')
            return redirect(url_for('admin.add_sale'))
        
        # Clear token immediately - prevents reuse on refresh
        session.pop('sale_form_token', None)
        
        try:
            customer_id = request.form.get('customer_id')
            customer_name = request.form.get('customer_name')
            email = request.form.get('email')
            advance_used = float(request.form.get('advance_used', 0) or 0)
            
            customer_id_final = None
            if customer_id and str(customer_id).isdigit():
                customer_id_final = int(customer_id)
                user_data = User.get_by_id(customer_id_final)
                if user_data:
                    customer_name = user_data.get('name')
            else:
                user_data = User.get_by_username(customer_name)
                if user_data:
                    customer_id_final = user_data.get('id')
                    customer_name = user_data.get('name')
                    if email and not user_data.get('email'):
                        User.update(customer_id_final, {'email': email})
                else:
                    new_user = User.create({
                        'name': customer_name,
                        'username': customer_name,
                        'email': email if email else None,
                        'role': 'customer'
                    })
                    if new_user:
                        customer_id_final = new_user.get('id')
                        customer_name = new_user.get('name')
            
            products = request.form.getlist('product[]')
            qtys = request.form.getlist('qty[]')
            units = request.form.getlist('unit[]')
            rates = request.form.getlist('rate[]')
            subtotals = request.form.getlist('subtotal[]')
            
            # ========== BYPRODUCT EXCHANGE LOGIC ==========
            exchange_mustard_cake = request.form.get('exchange_mustard_cake') == 'on'
            exchange_rice_bran = request.form.get('exchange_rice_bran') == 'on'

            line_items = [
                {'product_name': products[i], 'quantity': qtys[i], 'rate': rates[i], 'subtotal': subtotals[i]}
                for i in range(len(products)) if products[i] and products[i].strip()
            ]
            line_items = apply_byproduct_exchange_to_line_items(
                line_items, exchange_mustard_cake, exchange_rice_bran
            )
            products = [item['product_name'] for item in line_items]
            qtys = [str(item['quantity']) for item in line_items]
            rates = [str(item['rate']) for item in line_items]
            subtotals = [str(item['subtotal']) for item in line_items]

            sale_note = build_byproduct_note(exchange_mustard_cake, exchange_rice_bran)
            # =============================================
            
            total_amount = sum(float(x or 0) for x in subtotals)
            cash_paid = float(request.form.get('paid_amount') or 0)
            
            # Validate advance usage
            if advance_used > 0 and customer_id_final:
                available_balance = User.get_advance_balance(customer_id_final)
                if advance_used > available_balance:
                    error_msg = f'Insufficient advance balance. Available: Rs.{available_balance:,.2f}'
                    if is_ajax:
                        return jsonify({'success': False, 'error': error_msg}), 400
                    flash(error_msg, 'danger')
                    return redirect(url_for('admin.add_sale'))
                
                if advance_used > total_amount:
                    error_msg = f'Advance amount cannot exceed total amount (Rs.{total_amount:,.2f})'
                    if is_ajax:
                        return jsonify({'success': False, 'error': error_msg}), 400
                    flash(error_msg, 'danger')
                    return redirect(url_for('admin.add_sale'))
            
            # Prepare sale data
            sale_data = {
                'customer_id': customer_id_final,
                'customer_name': customer_name if customer_name else 'Walk-in Customer',
                'invoice_number': generate_invoice_number(),
                'total_amount': float(total_amount),
                'paid_amount': float(cash_paid),
                'created_by': current_user.id if current_user.id else None,
                'date': get_nepal_time().isoformat(),
                'notes': sale_note
            }
            
            sale_items = []
            for i in range(len(products)):
                if products[i] and products[i].strip():
                    sale_items.append({
                        'product_name': products[i],
                        'quantity': float(qtys[i] or 0),
                        'unit': units[i] if units[i] else 'Kg',
                        'rate': float(rates[i] or 0),
                        'subtotal': float(subtotals[i] or 0)
                    })
            
            if not sale_items:
                error_msg = 'Please add at least one product'
                if is_ajax:
                    return jsonify({'success': False, 'error': error_msg}), 400
                flash(error_msg, 'danger')
                return redirect(url_for('admin.add_sale'))
            
            # Create sale
            sale = Sale.create(sale_data, sale_items, advance_used)
            
            if not sale:
                error_msg = 'Failed to create sale'
                if is_ajax:
                    return jsonify({'success': False, 'error': error_msg}), 500
                flash(error_msg, 'danger')
                return redirect(url_for('admin.add_sale'))
            
            send_invoice = request.form.get('send_invoice') == 'on'
            
            if customer_id_final and send_invoice:
                customer = User.get_by_id(customer_id_final)
                if customer and customer.get('email'):
                    sale['customer_name'] = customer.get('name', 'Customer')
                    sale['customer_email'] = customer.get('email')
                    sale['items'] = sale_items
                    sale['notes'] = sale_note
                    
                    subject = f"Invoice from {Config.BUSINESS_NAME} - #{sale.get('invoice_number')}"
                    
                    html_content = render_template(
                        'admin/invoice_email.html',
                        sale=sale,
                        business_name=Config.BUSINESS_NAME,
                        total_amount=total_amount,
                        paid_amount=cash_paid,
                        due_amount=sale.get('due_amount', 0)
                    )
                    
                    send_invoice_email(customer.get('email'), subject, html_content)
            
            # AJAX response
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': f'Sale #{sale.get("invoice_number")} created successfully!',
                    'invoice_number': sale.get('invoice_number'),
                    'redirect': url_for('admin.sales_list')
                })
            
            # Non-AJAX response (fallback)
            if customer_id_final and send_invoice:
                if customer and customer.get('email'):
                    flash('Sale created successfully! Invoice will be sent shortly.', 'success')
                else:
                    flash('Sale created successfully! (No email - customer has no email)', 'success')
            else:
                flash('Sale created successfully!', 'success')
            
            return redirect(url_for('admin.sales_list'))
            
        except Exception as e:
            print(f"Error creating sale: {e}")
            error_msg = str(e)
            if is_ajax:
                return jsonify({'success': False, 'error': error_msg}), 500
            flash(f'Error: {error_msg}', 'danger')
            return redirect(url_for('admin.add_sale'))
    
    return render_template('admin/add_sale.html', customer_advance_balance=customer_advance_balance, selected_customer_id=selected_customer_id)








@bp.route('/customer/<int:customer_id>/deduct-advance', methods=['POST'])
@login_required
@admin_required
def deduct_advance_balance(customer_id):
    """Manually deduct advance balance from customer - AJAX ready"""
    from app.models_supabase import User
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    customer = User.get_by_id(customer_id)
    if not customer:
        if is_ajax:
            return jsonify({'success': False, 'error': 'Customer not found'}), 404
        flash('Customer not found', 'danger')
        return redirect(url_for('admin.customers_list'))
    
    try:
        amount = float(request.form.get('amount', 0))
        notes = request.form.get('notes', '')
        
        if amount <= 0:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Amount must be greater than 0'}), 400
            flash('Amount must be greater than 0', 'danger')
            return redirect(url_for('admin.customers_list'))
        
        available_balance = User.get_advance_balance(customer_id)
        if amount > available_balance:
            if is_ajax:
                return jsonify({'success': False, 'error': f'Insufficient balance. Available: Rs.{available_balance:,.2f}'}), 400
            flash(f'Insufficient balance. Available: Rs.{available_balance:,.2f}', 'danger')
            return redirect(url_for('admin.customers_list'))
        
        # Deduct advance
        result = User.update_advance_balance(customer_id, amount, "deduct")
        
        if result:
            # Record transaction
            transaction_data = {
                'customer_id': customer_id,
                'amount': amount,
                'type': 'withdraw',
                'notes': f'Manual withdrawal: {notes}' if notes else 'Manual withdrawal',
                'date': get_nepal_time().isoformat()
            }
            supabase.table("advance_transactions").insert(transaction_data).execute()
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': f'Rs.{amount:,.2f} deducted from {customer["name"]}\'s advance balance!',
                    'new_balance': User.get_advance_balance(customer_id)
                })
            flash(f'Rs.{amount:,.2f} deducted from {customer["name"]}\'s advance balance!', 'success')
            return redirect(url_for('admin.customers_list'))
        else:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Failed to deduct advance'}), 500
            flash('Failed to deduct advance', 'danger')
            return redirect(url_for('admin.customers_list'))
            
    except Exception as e:
        if is_ajax:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('admin.customers_list'))










@bp.route('/edit-sale/<int:sale_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_sale(sale_id):
    from app.models_supabase import User
    from datetime import datetime
    
    sale = Sale.get_by_id(sale_id)
    
    if not sale:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Sale not found'}), 404
        flash('Sale not found', 'danger')
        return redirect(url_for('admin.sales_list'))
    
    customer_id = sale.get('customer_id')
    
    # GET request - show form
    if request.method == 'GET':
        sale = Sale.get_by_id_with_items(sale_id) or sale
        exchange_mustard_cake, exchange_rice_bran = parse_exchange_from_note(sale.get('notes', ''))
        current_balance = User.get_advance_balance(customer_id) if customer_id else 0
        return render_template(
            'admin/edit_sale.html',
            sale=sale,
            customer_advance_balance=current_balance,
            exchange_mustard_cake=exchange_mustard_cake,
            exchange_rice_bran=exchange_rice_bran
        )
    
    # POST request - process form
    if request.method == 'POST':
        # Check if AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            exchange_mustard_cake = request.form.get('exchange_mustard_cake') == 'on'
            exchange_rice_bran = request.form.get('exchange_rice_bran') == 'on'
            sale_note = build_byproduct_note(exchange_mustard_cake, exchange_rice_bran)

            # Get existing items
            items = Sale.get_items(sale_id)
            
            # Process existing items and check for new items
            item_updates = []
            new_total = 0
            
            # Process existing items (with numeric IDs)
            for item in items:
                item_id = item['id']
                product = item.get('product_name', '')
                qty = float(item.get('quantity', 0) or 0)
                rate = float(item.get('rate', 0) or 0)
                
                # Get form values for this item
                form_rate = request.form.get(f'item_rate_{item_id}')
                form_qty = request.form.get(f'item_qty_{item_id}')
                form_unit = request.form.get(f'item_unit_{item_id}')
                
                # Update qty if provided
                if form_qty is not None:
                    qty = float(form_qty or 0)
                
                # Apply exchange logic
                if exchange_mustard_cake and is_mustard_extraction_product(product):
                    rate = 0
                elif not exchange_mustard_cake and is_mustard_extraction_product(product) and form_rate is not None:
                    rate = float(form_rate or 0)
                elif form_rate is not None:
                    rate = float(form_rate or 0)

                if exchange_rice_bran and is_others_or_dalbanai_product(product):
                    rate = 0
                    qty = 10
                elif not exchange_rice_bran and is_others_or_dalbanai_product(product) and form_rate is not None:
                    rate = float(form_rate or 0)

                subtotal = round(qty * rate, 2)
                new_total += subtotal
                item_updates.append({
                    'id': item_id, 
                    'rate': rate, 
                    'subtotal': subtotal,
                    'quantity': qty,
                    'unit': form_unit if form_unit else item.get('unit', 'Kg')
                })
            
            # Process new items (with IDs starting with 'new_')
            for key in request.form.keys():
                if key.startswith('item_rate_new_'):
                    new_item_id = key.replace('item_rate_', '')
                    product_name_key = f'product_name_{new_item_id}'
                    qty_key = f'item_qty_{new_item_id}'
                    unit_key = f'item_unit_{new_item_id}'
                    
                    product_name = request.form.get(product_name_key)
                    if not product_name:
                        continue
                    
                    qty = float(request.form.get(qty_key, 0) or 0)
                    unit = request.form.get(unit_key, 'Kg')
                    rate = float(request.form.get(key, 0) or 0)
                    
                    # Apply exchange logic for new items
                    if exchange_mustard_cake and is_mustard_extraction_product(product_name):
                        rate = 0
                        qty = 10
                    if exchange_rice_bran and is_others_or_dalbanai_product(product_name):
                        rate = 0
                        qty = 10
                    
                    subtotal = round(qty * rate, 2)
                    new_total += subtotal
                    
                    # Store new item to be created
                    if not hasattr(request, '_new_items'):
                        request._new_items = []
                    request._new_items.append({
                        'product_name': product_name,
                        'quantity': qty,
                        'unit': unit,
                        'rate': rate,
                        'subtotal': subtotal
                    })
            
            # Update existing items
            if item_updates:
                for update in item_updates:
                    # Update sale_items table
                    supabase.table("sale_items").update({
                        'rate': update['rate'],
                        'subtotal': update['subtotal'],
                        'quantity': update['quantity'],
                        'unit': update['unit']
                    }).eq("id", update['id']).execute()
            
            # Create new items
            if hasattr(request, '_new_items'):
                for new_item in request._new_items:
                    new_item['sale_id'] = sale_id
                    supabase.table("sale_items").insert(new_item).execute()
            
            new_cash_paid = float(request.form.get('paid_amount', 0))
            new_advance_used = float(request.form.get('advance_used', 0))
            
            total = round(new_total, 2)
            old_cash_paid = sale.get('paid_amount', 0)
            old_advance_used = sale.get('advance_used', 0)
            old_advance_amount = sale.get('advance_amount', 0)
            
            # ========== VALIDATIONS ==========
            if new_cash_paid < 0 or new_advance_used < 0:
                error_msg = 'Amounts cannot be negative.'
                if is_ajax:
                    return jsonify({'success': False, 'error': error_msg}), 400
                flash(error_msg, 'danger')
                return redirect(url_for('admin.edit_sale', sale_id=sale_id))
            
            if new_advance_used > total:
                error_msg = f'Advance used cannot exceed total amount (Rs {total:.2f})'
                if is_ajax:
                    return jsonify({'success': False, 'error': error_msg}), 400
                flash(error_msg, 'danger')
                return redirect(url_for('admin.edit_sale', sale_id=sale_id))
            
            # Get customer's ACTUAL advance balance
            customer_actual_balance = User.get_advance_balance(customer_id) if customer_id else 0
            
            # Calculate how much MORE advance is being used
            advance_increase = new_advance_used - old_advance_used
            
            # CRITICAL: Block if trying to use more advance than available
            if advance_increase > 0 and advance_increase > customer_actual_balance:
                error_msg = f'Cannot use Rs {advance_increase:,.2f} advance. Customer only has Rs {customer_actual_balance:,.2f} available.'
                if is_ajax:
                    return jsonify({'success': False, 'error': error_msg}), 400
                flash(error_msg, 'danger')
                return redirect(url_for('admin.edit_sale', sale_id=sale_id))
            
            # Calculate new advance_amount (overpayment)
            total_payment = new_cash_paid + new_advance_used
            
            if total_payment > total:
                new_advance_amount = total_payment - total
                new_due = 0
                payment_status = 'advance'
            elif total_payment == total:
                new_advance_amount = 0
                new_due = 0
                payment_status = 'paid'
            else:
                new_advance_amount = 0
                new_due = total - total_payment
                payment_status = 'partial'
            
            # Calculate net effect on customer's advance balance
            old_net_effect = old_advance_amount - old_advance_used
            new_net_effect = new_advance_amount - new_advance_used
            balance_change = new_net_effect - old_net_effect
            
            # Apply balance change
            if customer_id and balance_change != 0:
                if balance_change > 0:
                    User.update_advance_balance(customer_id, abs(balance_change), "add")
                else:
                    User.update_advance_balance(customer_id, abs(balance_change), "deduct")
            
            # Update sale
            update_result = Sale.update(sale_id, {
                'total_amount': round(total, 2),
                'paid_amount': round(new_cash_paid, 2),
                'advance_used': round(new_advance_used, 2),
                'due_amount': round(new_due, 2),
                'advance_amount': round(new_advance_amount, 2),
                'payment_status': payment_status,
                'notes': sale_note
            })
            
            if update_result:
                # Record audit trail
                if customer_id and balance_change != 0:
                    transaction_data = {
                        'customer_id': customer_id,
                        'sale_id': sale_id,
                        'amount': abs(balance_change),
                        'type': 'edit_sale',
                        'notes': f'Edited sale #{sale.get("invoice_number")}: Cash {old_cash_paid}→{new_cash_paid}, Advance Used {old_advance_used}→{new_advance_used}',
                        'date': get_nepal_time().isoformat()
                    }
                    supabase.table("advance_transactions").insert(transaction_data).execute()
                
                final_balance = User.get_advance_balance(customer_id) if customer_id else 0
                
                if is_ajax:
                    return jsonify({
                        'success': True,
                        'message': f'Sale #{sale.get("invoice_number")} updated successfully! Customer advance balance: Rs {final_balance:,.2f}',
                        'redirect': url_for('admin.sales_list')
                    })
                
                flash(f'Sale updated! Customer advance balance: Rs {final_balance:,.2f}', 'success')
            else:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Failed to update sale'}), 500
                flash('Failed to update sale', 'danger')
            
            if is_ajax:
                return jsonify({'success': True, 'redirect': url_for('admin.sales_list')})
            
            return redirect(url_for('admin.sales_list'))
            
        except Exception as e:
            print(f"Error: {e}")
            error_msg = str(e)
            if is_ajax:
                return jsonify({'success': False, 'error': error_msg}), 500
            flash(f'Error: {error_msg}', 'danger')
            return redirect(url_for('admin.edit_sale', sale_id=sale_id))


@bp.route('/delete-sale/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def delete_sale(sale_id):
    from app.models_supabase import User
    from datetime import datetime
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # Get sale details BEFORE deleting
    sale = Sale.get_by_id(sale_id)
    
    if not sale:
        if is_ajax:
            return jsonify({'success': False, 'error': 'Sale not found'}), 404
        flash('Sale not found', 'danger')
        return redirect(url_for('admin.sales_list'))
    
    customer_id = sale.get('customer_id')
    advance_used = sale.get('advance_used', 0)
    invoice_number = sale.get('invoice_number', '')
    
    try:
        # Refund advance amount back to customer's balance if any was used
        if customer_id and advance_used > 0:
            result = User.update_advance_balance(customer_id, advance_used, "add")
            
            if result:
                # Record audit transaction
                transaction_data = {
                    'customer_id': customer_id,
                    'sale_id': sale_id,
                    'amount': advance_used,
                    'type': 'refund_on_delete',
                    'notes': f'Advance refunded due to deletion of sale #{invoice_number}',
                    'date': get_nepal_time().isoformat()
                }
                supabase.table("advance_transactions").insert(transaction_data).execute()
                print(f"✅ Refunded Rs {advance_used:.2f} advance to customer {customer_id} (sale deleted)")
        
        # Delete sale items first (foreign key constraint)
        supabase.table("sale_items").delete().eq("sale_id", sale_id).execute()
        
        # Then delete the sale
        result = Sale.delete(sale_id)
        
        if result:
            if is_ajax:
                return jsonify({
                    'success': True, 
                    'message': f'Sale #{invoice_number} deleted successfully! Advance balance has been restored.'
                })
            flash('Sale deleted successfully! Advance balance has been restored.', 'success')
        else:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Failed to delete sale'}), 500
            flash('Failed to delete sale', 'danger')
            
    except Exception as e:
        print(f"Error deleting sale: {e}")
        if is_ajax:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Error deleting sale: {str(e)}', 'danger')
    
    if not is_ajax:
        return redirect(url_for('admin.sales_list'))
    
    return jsonify({'success': True})


@bp.route('/sales/<int:sale_id>/invoice')
@login_required
@admin_required
def invoice_view(sale_id):
    sale = Sale.get_by_id_with_items(sale_id)
    if sale:
        if sale.get('customer_id'):
            customer = User.get_by_id(sale.get('customer_id'))
            if customer:
                sale['customer_name'] = customer.get('name')
                sale['customer_email'] = customer.get('email')
                sale['customer_username'] = customer.get('username', '')
                sale['customer_phone'] = customer.get('phone', '') 
                sale['customer_address'] = customer.get('address', '') 
    return render_template('admin/invoice.html', sale=sale)


# ============================================
# CUSTOMER MANAGEMENT
# ============================================

@bp.route('/customers')
@login_required
@admin_required
def customers_list():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    customers_data, total = User.get_customers_paginated(page, 10, search)
    User.enrich_customers_with_sales_stats(customers_data)

    list_stats = User.get_customer_list_stats()
    total_advance_balance = list_stats['total_advance_balance']
    total_customers_with_advance = list_stats['total_customers_with_advance']
    active_customers_count = list_stats['active_customers_count']
    inactive_customers_count = list_stats['inactive_customers_count']
    
    customers = Pagination(customers_data, page, 10, total)
    
    return render_template(
        'admin/customers.html',
        customers=customers,
        search=search,
        active_customers_count=active_customers_count,
        inactive_customers_count=inactive_customers_count,
        total_advance_balance=total_advance_balance,
        total_customers_with_advance=total_customers_with_advance
    )   

@bp.route('/customers/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_customer():
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            existing = User.get_by_username(username)
            
            if existing:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Username already exists!'}), 400
                flash('Username already exists!', 'danger')
                return redirect(url_for('admin.add_customer'))
            
            user_data = {
                'name': request.form.get('name'),
                'username': username,
                'email': request.form.get('email'),
                'phone': request.form.get('phone'),
                'address': request.form.get('address'),
                'role': 'customer'
            }
            
            result = User.create(user_data)
            if result:
                if is_ajax:
                    return jsonify({
                        'success': True,
                        'message': f'Customer "{user_data["name"]}" added successfully!',
                        'redirect': url_for('admin.customers_list')
                    })
                flash('Customer added successfully', 'success')
            else:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Failed to add customer'}), 500
                flash('Failed to add customer', 'danger')
            return redirect(url_for('admin.customers_list'))
            
        except Exception as e:
            if is_ajax:
                return jsonify({'success': False, 'error': str(e)}), 500
            flash(str(e), 'danger')
    
    return render_template('admin/add_customer.html')


@bp.route('/customers/<int:customer_id>/invoices')
@login_required
@admin_required
def customer_invoices(customer_id):
    """Customer invoice list — filtered at DB with items in bulk."""
    customer = User.get_by_id(customer_id)
    if not customer:
        flash('Customer not found', 'danger')
        return redirect(url_for('admin.customers_list'))

    sales, _ = Sale.get_by_customer(customer_id, page=1, per_page=500, with_items=True)

    return render_template(
        'admin/customer_invoices.html',
        customer=customer,
        sales=sales,
        business_name=Config.BUSINESS_NAME
    )


@bp.route('/customers/<int:customer_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_customer(customer_id):
    customer = User.get_by_id(customer_id)
    
    if not customer:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Customer not found'}), 404
        flash('Customer not found', 'danger')
        return redirect(url_for('admin.customers_list'))
    
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            # Check if username already exists (excluding current customer)
            username = request.form.get('username')
            existing = User.get_by_username(username)
            if existing and existing.get('id') != customer_id:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Username already exists!'}), 400
                flash('Username already exists!', 'danger')
                return redirect(url_for('admin.edit_customer', customer_id=customer_id))
            
            result = User.update(customer_id, {
                'name': request.form.get('name'),
                'username': username,
                'phone': request.form.get('phone'),
                'email': request.form.get('email'),
                'address': request.form.get('address'),
                'is_active': 'is_active' in request.form
            })
            
            if result:
                if is_ajax:
                    return jsonify({
                        'success': True,
                        'message': f'Customer "{request.form.get("name")}" updated successfully!',
                        'redirect': url_for('admin.customers_list')
                    })
                flash('Customer updated successfully!', 'success')
            else:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Failed to update customer'}), 500
                flash('Failed to update customer', 'danger')
                
        except Exception as e:
            if is_ajax:
                return jsonify({'success': False, 'error': str(e)}), 500
            flash(f'Error: {str(e)}', 'danger')
        
        if not is_ajax:
            return redirect(url_for('admin.customers_list'))
    
    return render_template('admin/edit_customer.html', customer=customer)

@bp.route('/customers/<int:customer_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_customer(customer_id):
    """Delete a customer and all associated data - AJAX ready"""
    from app.models_supabase import User
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        # Get customer details before deletion
        customer = User.get_by_id(customer_id)
        
        if not customer:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Customer not found'}), 404
            flash('Customer not found', 'danger')
            return redirect(url_for('admin.customers_list'))
        
        customer_name = customer.get('name')
        
        # Delete the customer
        result = User.delete(customer_id)
        
        if result:
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': f'Customer "{customer_name}" deleted successfully!'
                })
            flash(f'Customer "{customer_name}" deleted successfully!', 'success')
        else:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Failed to delete customer'}), 500
            flash('Failed to delete customer', 'danger')
            
    except Exception as e:
        print(f"Error deleting customer: {e}")
        if is_ajax:
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Error deleting customer: {str(e)}', 'danger')
    
    if not is_ajax:
        return redirect(url_for('admin.customers_list'))
    return jsonify({'success': True})


@bp.route('/contact-messages')
@login_required
@admin_required
def contact_messages():
    """View all contact form messages"""
    from app.supabase_client import supabase
    
    try:
        response = supabase.table("contact_messages")\
            .select("*")\
            .order("Date", desc=True)\
            .execute()
        
        messages = response.data if response.data else []
        return render_template('admin/contact_messages.html', messages=messages)
    except Exception as e:
        print(f"Error fetching messages: {e}")
        flash('Error loading messages', 'danger')
        return render_template('admin/contact_messages.html', messages=[])



@bp.route('/delete-contact-message/<int:message_id>', methods=['POST'])
@login_required
@admin_required
def delete_contact_message(message_id):
    """Delete a contact message"""
    from app.supabase_client import supabase
    
    try:
        supabase.table("contact_messages").delete().eq("id", message_id).execute()
        flash('Message deleted successfully', 'success')
    except Exception as e:
        print(f"Error deleting message: {e}")
        flash('Failed to delete message', 'danger')
    
    return redirect(url_for('admin.contact_messages'))


# ============================================
# EXPENSE MANAGEMENT
# ============================================

@bp.route('/expenses')
@login_required
@admin_required
def expenses_list():
    page = request.args.get('page', 1, type=int)
    selected_category = request.args.get('category', '')
    
    expenses_data, total = Expense.get_all_paginated(page, 10, selected_category)
    
    # Calculate stats for stat cards - RETURN NUMBERS, NOT FORMATTED STRINGS
    all_expenses, _ = Expense.get_all_paginated(1, 1000, selected_category)
    grand_total = sum(e.get('amount', 0) for e in all_expenses)
    
    # Average per transaction
    avg_per_transaction = grand_total / total if total > 0 else 0
    
    # Highest expense
    highest_expense = max((e.get('amount', 0) for e in all_expenses), default=0)
    
    expenses = Pagination(expenses_data, page, 10, total)
    categories = Expense.get_categories()
    
    return render_template(
        'admin/expenses.html',
        expenses=expenses,
        categories=categories,
        selected_category=selected_category,
        total_expenses=grand_total,  
        avg_per_transaction=avg_per_transaction,  
        highest_expense=highest_expense,  
        business_name=Config.BUSINESS_NAME
    )


@bp.route('/expenses/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_expense():
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.method == 'POST':
        try:
            expense_data = {
                'category': request.form.get('category'),
                'description': request.form.get('description'),
                'amount': float(request.form.get('amount', 0)),
                'notes': request.form.get('notes', ''),
                'created_by': current_user.id,
                'created_at': get_nepal_time().isoformat(),
                'date': get_nepal_time().isoformat()
            }
            
            # Validate
            if not expense_data['category']:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Category is required'}), 400
                flash('Category is required', 'danger')
                return redirect(url_for('admin.add_expense'))
            
            if expense_data['amount'] <= 0:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Amount must be greater than 0'}), 400
                flash('Amount must be greater than 0', 'danger')
                return redirect(url_for('admin.add_expense'))
            
            result = Expense.create(expense_data)
            
            if result:
                if is_ajax:
                    return jsonify({
                        'success': True,
                        'message': f'Expense of Rs {expense_data["amount"]:,.2f} added successfully!',
                        'redirect': url_for('admin.expenses_list')
                    })
                flash('Expense added successfully', 'success')
            else:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Failed to add expense'}), 500
                flash('Failed to add expense', 'danger')
                
        except Exception as e:
            print(f"Error adding expense: {e}")
            if is_ajax:
                return jsonify({'success': False, 'error': str(e)}), 500
            flash(str(e), 'danger')
        
        if not is_ajax:
            return redirect(url_for('admin.expenses_list'))
    
    return render_template('admin/add_expense.html', business_name=Config.BUSINESS_NAME)


@bp.route('/expenses/<int:expense_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_expense(expense_id):
    expense = Expense.get_by_id(expense_id)
    
    if not expense:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Expense not found'}), 404
        flash('Expense not found', 'danger')
        return redirect(url_for('admin.expenses_list'))
    
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            result = Expense.update(expense_id, {
                'category': request.form.get('category'),
                'description': request.form.get('description'),
                'amount': float(request.form.get('amount') or 0),
                'notes': request.form.get('notes', '')
            })
            
            if result:
                if is_ajax:
                    return jsonify({
                        'success': True,
                        'message': f'Expense updated successfully!',
                        'redirect': url_for('admin.expenses_list')
                    })
                flash('Expense updated successfully!', 'success')
            else:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Failed to update expense'}), 500
                flash('Failed to update expense', 'danger')
                
        except Exception as e:
            if is_ajax:
                return jsonify({'success': False, 'error': str(e)}), 500
            flash(f'Error: {str(e)}', 'danger')
        
        if not is_ajax:
            return redirect(url_for('admin.expenses_list'))
    
    return render_template('admin/edit_expense.html', expense=expense)

@bp.route('/expenses/<int:expense_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_expense(expense_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    result = Expense.delete(expense_id)
    
    if result:
        if is_ajax:
            return jsonify({'success': True, 'message': 'Expense deleted successfully!'})
        flash('Expense deleted successfully!', 'success')
    else:
        if is_ajax:
            return jsonify({'success': False, 'error': 'Failed to delete expense'}), 500
        flash('Failed to delete expense', 'danger')
    
    if not is_ajax:
        return redirect(url_for('admin.expenses_list'))
    return jsonify({'success': True})


# ============================================
# REPORTS
# ============================================

@bp.route('/reports')
@login_required
@admin_required
def reports():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Set default date range if not provided (last 30 days)
    if not start_date:
        start_date = (get_nepal_time() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = get_nepal_time().strftime('%Y-%m-%d')
    
    # Convert to ISO format for database queries
    start_datetime = f"{start_date}T00:00:00"
    end_datetime = f"{end_date}T23:59:59"
    
    # Sales + line items in date range (2 queries, not N+1)
    sales_in_range, range_items = Sale.get_items_by_date_range(start_datetime, end_datetime)

    sales_by_product = {}
    for item in range_items:
        product_name = item.get('product_name', 'Unknown')
        subtotal = float(item.get('subtotal', 0) or 0)
        sales_by_product[product_name] = sales_by_product.get(product_name, 0) + subtotal
    
    # Convert to list of tuples and sort by value (highest first)
    sales_by_type = sorted(sales_by_product.items(), key=lambda x: x[1], reverse=True)
    # Limit to top 10 products
    sales_by_type = sales_by_type[:10]
    
    # If no sales data, show placeholder
    if not sales_by_type:
        sales_by_type = [('No Sales Data', 0)]
    
    # ========== FIXED: Get REAL expenses by category ==========
    all_expenses, total_expenses_count = Expense.get_all_paginated(1, 1000, "")
    
    # Filter expenses by date range
    expenses_in_range = []
    for expense in all_expenses:
        expense_date = expense.get('date', '')
        if expense_date and start_datetime <= expense_date <= end_datetime:
            expenses_in_range.append(expense)
    
    # Aggregate expenses by category
    expenses_by_category_dict = {}
    for expense in expenses_in_range:
        category = expense.get('category', 'Uncategorized')
        amount = expense.get('amount', 0)
        if category in expenses_by_category_dict:
            expenses_by_category_dict[category] += amount
        else:
            expenses_by_category_dict[category] = amount
    
    # Convert to list of tuples and sort by value (highest first)
    expenses_by_category = sorted(expenses_by_category_dict.items(), key=lambda x: x[1], reverse=True)
    
    # If no expenses data, show placeholder
    if not expenses_by_category:
        expenses_by_category = [('No Expense Data', 0)]
    
    # Top customers: aggregate sales in one pass, resolve names in one bulk query
    customer_purchases = {}
    customer_ids_in_range = set()
    for sale in sales_in_range:
        customer_id = sale.get('customer_id')
        total_amount = float(sale.get('total_amount', 0) or 0)
        if customer_id:
            customer_ids_in_range.add(customer_id)
            if customer_id not in customer_purchases:
                customer_purchases[customer_id] = {'name': 'Unknown', 'total': 0.0}
            customer_purchases[customer_id]['total'] += total_amount
        else:
            customer_name = sale.get('customer_name', 'Walk-in Customer')
            key = f"walkin:{customer_name}"
            if key not in customer_purchases:
                customer_purchases[key] = {'name': customer_name, 'total': 0.0}
            customer_purchases[key]['total'] += total_amount

    if customer_ids_in_range:
        names_response = supabase.table("users").select("id, name").in_("id", list(customer_ids_in_range)).execute()
        name_map = {u['id']: u.get('name', 'Unknown') for u in names_response.data}
        for cid, data in customer_purchases.items():
            if isinstance(cid, int) and cid in name_map:
                data['name'] = name_map[cid]

    customer_purchases_by_name = {data['name']: data['total'] for data in customer_purchases.values()}
    
    top_customers = sorted(customer_purchases_by_name.items(), key=lambda x: x[1], reverse=True)
    # Limit to top 10 customers
    top_customers = top_customers[:10]
    
    # If no customers data, show placeholder
    if not top_customers:
        top_customers = [('No customer data', 0)]
    
    # ========== Calculate totals for KPI cards ==========
    total_sales = sum(amount for _, amount in sales_by_type) if sales_by_type[0][0] != 'No Sales Data' else 0
    total_expenses = sum(amount for _, amount in expenses_by_category) if expenses_by_category[0][0] != 'No Expense Data' else 0
    profit = total_sales - total_expenses
    
    return render_template(
        'admin/reports.html',
        total_sales=total_sales,
        total_expenses=total_expenses,
        profit=profit,
        sales_by_type=sales_by_type,
        expenses_by_category=expenses_by_category,
        top_customers=top_customers,
        start_date=start_date,
        end_date=end_date
    )


@bp.route('/profit')
@login_required
@admin_required
def profit_analysis():
    today_stats = get_today_stats()
    monthly_stats = get_monthly_stats()
    
    sales = Sale.get_total_by_date_range('2024-01-01', get_nepal_time().isoformat())
    expenses = Expense.get_total_by_date_range('2024-01-01', get_nepal_time().isoformat())
    profit = sales - expenses
    
    yearly_stats = {
        'sales': sales,
        'expenses': expenses,
        'profit': profit
    }
    
    return render_template(
        'admin/profit.html',
        today_stats=today_stats,
        monthly_stats=monthly_stats,
        yearly_stats=yearly_stats
    )


# ============================================
# API ENDPOINTS
# ============================================

@bp.route('/api/weekly-sales')
@login_required
@admin_required
def weekly_sales():
    return jsonify(get_weekly_sales_data())


@bp.route('/api/monthly-sales')
@login_required
@admin_required
def monthly_sales():
    return jsonify(get_monthly_sales_data())


@bp.route('/reports/payment-channel')
@login_required
@admin_required
def payment_channel_report():
    return jsonify(get_payment_channel_data())


@bp.route('/api/customers/search')
@login_required
@admin_required
def search_customers():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    
    customers_data, total = User.get_customers_paginated(1, 10, q)
    
    return jsonify([{'id': c.get('id'), 'name': c.get('name'), 'email': c.get('email')} for c in customers_data])


# ============================================
# PAYMENT & DUES MANAGEMENT
# ============================================

@bp.route('/customer-dues')
@login_required
@admin_required
def customer_dues():
    """List all customers with pending dues — 2 queries, no per-customer loops."""
    all_customers = User.get_customers_for_dues()
    all_sales = Sale.get_sales_totals_for_dues()

    customer_data = {}
    for customer in all_customers:
        customer_data[customer['id']] = {
            'id': customer['id'],
            'name': customer.get('name', ''),
            'email': customer.get('email', ''),
            'phone': customer.get('phone', ''),
            'total_purchases': 0.0,
            'total_paid_cash': 0.0,
            'total_advance_used': 0.0,
            'pending_due': 0.0,
            'advance_balance': float(customer.get('advance_balance', 0) or 0),
        }

    for sale in all_sales:
        customer_id = sale.get('customer_id')
        if not customer_id or customer_id not in customer_data:
            continue
        data = customer_data[customer_id]
        data['total_purchases'] += float(sale.get('total_amount', 0) or 0)
        data['total_paid_cash'] += float(sale.get('paid_amount', 0) or 0)
        data['total_advance_used'] += float(sale.get('advance_used', 0) or 0)
        data['pending_due'] += float(sale.get('due_amount', 0) or 0)

    customers_with_dues = [
        data for data in customer_data.values()
        if data['pending_due'] > 0 or data['advance_balance'] > 0
    ]
    customers_with_dues.sort(key=lambda x: x['pending_due'], reverse=True)

    total_due_amount = sum(c['pending_due'] for c in customers_with_dues)
    total_advance_balance = sum(c['advance_balance'] for c in customer_data.values())
    customers_with_advance = sum(1 for c in customer_data.values() if c['advance_balance'] > 0)
    
    return render_template(
        'admin/customer_dues.html',
        customers_with_dues=customers_with_dues,
        total_due_amount=total_due_amount,
        total_advance_balance=total_advance_balance,
        customers_with_advance=customers_with_advance
    )

@bp.route('/customer-payment/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def customer_payment(sale_id):
    """Record payment for a specific sale from customer payment history page"""
    from app.models_supabase import User
    from datetime import datetime
    
    sale = Sale.get_by_id(sale_id)
    if not sale:
        flash('Sale not found', 'danger')
        return redirect(request.referrer or url_for('admin.sales_list'))
    
    customer_id = sale.get('customer_id')
    if not customer_id:
        flash('Customer not found for this sale', 'danger')
        return redirect(request.referrer or url_for('admin.sales_list'))
    
    try:
        advance_used = float(request.form.get('advance_amount', 0) or 0)
        cash_amount = float(request.form.get('amount', 0) or 0)
        payment_mode = request.form.get('payment_mode')
        notes = request.form.get('notes', '')
        send_email = request.form.get('send_email') == 'on'
        
        total_payment = advance_used + cash_amount
        
        if total_payment <= 0:
            flash('Invalid payment amount', 'danger')
            return redirect(url_for('admin.customer_dues'))
        
        # Get current sale values
        total_amount = sale.get('total_amount', 0)
        old_cash_paid = sale.get('paid_amount', 0)
        old_advance_used = sale.get('advance_used', 0)
        
        # Calculate new values
        new_cash_paid = old_cash_paid + cash_amount
        new_advance_used = old_advance_used + advance_used
        new_total_paid = new_cash_paid + new_advance_used
        
        # ========== VALIDATIONS ==========
        # Check sufficient advance balance
        if advance_used > 0:
            available_balance = User.get_advance_balance(customer_id)
            if advance_used > available_balance:
                flash(f'Insufficient advance balance. Available: Rs {available_balance:,.2f}', 'danger')
                return redirect(url_for('admin.customer_dues'))
        
        # Check advance used doesn't exceed total
        if new_advance_used > total_amount:
            flash(f'Advance used cannot exceed total amount (Rs {total_amount:.2f})', 'danger')
            return redirect(url_for('admin.customer_dues'))
        
        # Check advance increase doesn't exceed remaining due
        remaining_due_before = total_amount - (old_cash_paid + old_advance_used)
        if advance_used > remaining_due_before and remaining_due_before > 0:
            flash(f'Cannot redeem more advance than remaining due (Rs {remaining_due_before:.2f})', 'danger')
            return redirect(url_for('admin.customer_dues'))
        
        # Calculate new status
        if new_total_paid >= total_amount:
            if new_total_paid > total_amount:
                new_advance_amount = new_total_paid - total_amount
                payment_status = 'advance'
                new_due = 0
            else:
                new_advance_amount = 0
                payment_status = 'paid'
                new_due = 0
        else:
            new_advance_amount = 0
            payment_status = 'partial'
            new_due = total_amount - new_total_paid
        
        # ========== UPDATE ADVANCE BALANCE (CONSISTENT WITH edit_sale) ==========
        # Calculate net change to advance balance (Positive = refund, Negative = deduct)
        net_advance_change = old_advance_used - new_advance_used
        
        if net_advance_change != 0:
            if net_advance_change > 0:
                # Refunding advance back to customer
                User.update_advance_balance(customer_id, net_advance_change, "add")
                print(f"✅ Refunded Rs {net_advance_change:.2f} to customer advance")
            else:
                # Deducting advance from customer
                User.update_advance_balance(customer_id, abs(net_advance_change), "deduct")
                print(f"✅ Deducted Rs {abs(net_advance_change):.2f} from customer advance")
        
        # Handle cash overpayment (creates advance)
        if cash_amount > 0 and new_cash_paid > total_amount and new_advance_amount == 0:
            overpayment = new_cash_paid - total_amount
            User.update_advance_balance(customer_id, overpayment, "add")
            print(f"✅ Added Rs {overpayment:.2f} to customer advance (overpayment)")
        
        # Create payment record
        payment_data = {
            'sale_id': sale_id,
            'customer_id': customer_id,
            'amount': total_payment,
            'payment_mode': payment_mode,
            'notes': notes + (f' (Advance used: Rs {advance_used})' if advance_used > 0 else ''),
            'created_by': current_user.id
        }
        Payment.create(payment_data)
        
        # Update sale
        Sale.update(sale_id, {
            'paid_amount': round(new_cash_paid, 2),
            'advance_used': round(new_advance_used, 2),
            'due_amount': round(new_due, 2),
            'advance_amount': round(new_advance_amount, 2),
            'payment_status': payment_status
        })
        
        # Record transaction for audit
        if advance_used > 0 or cash_amount > 0:
            transaction_data = {
                'customer_id': customer_id,
                'sale_id': sale_id,
                'amount': total_payment,
                'type': 'payment',
                'notes': f'Payment recorded: Cash Rs {cash_amount}, Advance Rs {advance_used}',
                'date': get_nepal_time().isoformat()
            }
            supabase.table("advance_transactions").insert(transaction_data).execute()
        
        # Send email if requested
        if send_email:
            customer = User.get_by_id(customer_id)
            if customer and customer.get('email'):
                try:
                    from app.brevo_service import send_invoice_email
                    subject = f"Payment Receipt - Invoice {sale.get('invoice_number')}"
                    html_content = f"""
                    <html>
                    <body>
                        <h2>Payment Received</h2>
                        <p>Dear {customer.get('name')},</p>
                        <p>We have received your payment of <strong>Rs {total_payment:,.2f}</strong> for invoice <strong>{sale.get('invoice_number')}</strong>.</p>
                        <p>Payment Mode: {payment_mode}</p>
                        <p>Thank you for your business!</p>
                    </body>
                    </html>
                    """
                    send_invoice_email(customer.get('email'), subject, html_content)
                except Exception as e:
                    print(f"Email error: {e}")
        
        flash(f'Payment of Rs {total_payment:,.2f} recorded successfully!', 'success')
        return redirect(url_for('admin.customer_dues'))
        
    except Exception as e:
        print(f"Error: {e}")
        flash(f'Error recording payment: {str(e)}', 'danger')
        return redirect(url_for('admin.customer_dues'))
    
@bp.route('/record-payment-direct/<int:customer_id>', methods=['POST'])
@login_required
@admin_required
def record_payment_direct(customer_id):
    """Record payment directly from customer dues page - WITH EMAIL FIXED"""
    from app.models_supabase import User
    from app.brevo_service import send_invoice_email  # ADD THIS IMPORT
    
    try:
        advance_used = float(request.form.get('advance_amount', 0) or 0)
        cash_amount = float(request.form.get('amount', 0) or 0)
        payment_mode = request.form.get('payment_mode')
        notes = request.form.get('notes', '')
        send_email = request.form.get('send_email') == 'on'
        
        total_payment = advance_used + cash_amount
        
        if total_payment <= 0:
            flash('Invalid payment amount', 'danger')
            return redirect(url_for('admin.customer_dues'))
        
        # Get customer's current advance balance from users table
        current_advance_balance = User.get_advance_balance(customer_id)
        
        # Validate advance usage
        if advance_used > 0 and advance_used > current_advance_balance:
            flash(f'Insufficient advance balance. Available: Rs {current_advance_balance:,.2f}', 'danger')
            return redirect(url_for('admin.customer_dues'))
        
        unpaid_sales = Sale.get_unpaid_by_customer(customer_id)
        
        if not unpaid_sales:
            flash('No pending dues found for this customer', 'warning')
            return redirect(url_for('admin.customer_dues'))
        
        # Sort by oldest first
        unpaid_sales.sort(key=lambda x: x.get('date', ''))
        
        remaining = total_payment
        remaining_advance = advance_used
        
        total_cash_used = 0
        total_advance_deducted = 0
        
        # Store payment details for email
        paid_invoices = []
        
        # Apply payment to unpaid sales only
        for sale in unpaid_sales:
            if remaining <= 0:
                break
            
            due = sale.get('due_amount', 0)
            if due <= 0:
                continue
            
            payment_for_sale = min(remaining, due)
            remaining -= payment_for_sale
            
            # Determine what portion of this payment was advance vs cash
            advance_portion = 0
            cash_portion = payment_for_sale
            
            if remaining_advance > 0:
                if payment_for_sale <= remaining_advance:
                    advance_portion = payment_for_sale
                    cash_portion = 0
                    remaining_advance -= payment_for_sale
                else:
                    advance_portion = remaining_advance
                    cash_portion = payment_for_sale - remaining_advance
                    remaining_advance = 0
            
            total_advance_deducted += advance_portion
            total_cash_used += cash_portion
            
            # Track for email
            paid_invoices.append({
                'invoice_number': sale.get('invoice_number'),
                'amount': payment_for_sale,
                'advance_portion': advance_portion,
                'cash_portion': cash_portion,
                'old_due': due,
                'new_due': due - payment_for_sale
            })
            
            # Get current sale values
            old_paid = sale.get('paid_amount', 0)
            old_advance_used = sale.get('advance_used', 0)
            sale_total = sale.get('total_amount', 0)
            old_advance_amount = sale.get('advance_amount', 0)
            
            # Calculate new values
            new_paid = old_paid + cash_portion
            new_advance_used = old_advance_used + advance_portion
            
            total_paid = new_paid + new_advance_used
            
            # Determine payment status and due
            if total_paid >= sale_total:
                if total_paid > sale_total:
                    new_advance_amount = total_paid - sale_total
                    new_due = 0
                    payment_status = 'advance'
                else:
                    new_advance_amount = 0
                    new_due = 0
                    payment_status = 'paid'
            else:
                new_advance_amount = 0
                new_due = sale_total - total_paid
                payment_status = 'partial'
            
            # Update sale
            Sale.update(sale['id'], {
                'paid_amount': round(new_paid, 2),
                'advance_used': round(new_advance_used, 2),
                'due_amount': round(new_due, 2),
                'advance_amount': round(new_advance_amount, 2),
                'payment_status': payment_status
            })
            
            # Create payment record
            payment_data = {
                'sale_id': sale['id'],
                'customer_id': customer_id,
                'amount': round(payment_for_sale, 2),
                'payment_mode': payment_mode,
                'notes': f'Cash: Rs {cash_portion:,.2f}, Advance: Rs {advance_portion:,.2f}' if advance_portion > 0 else notes,
                'created_by': current_user.id
            }
            Payment.create(payment_data)
        
        # Update customer's advance balance
        if total_advance_deducted > 0:
            User.update_advance_balance(customer_id, total_advance_deducted, "deduct")
        
        # Handle remaining cash (overpayment) - creates new advance credit
        overpayment_amount = 0
        if remaining > 0:
            overpayment_amount = remaining
            User.update_advance_balance(customer_id, remaining, "add")
            transaction_data = {
                'customer_id': customer_id,
                'amount': remaining,
                'type': 'deposit',
                'notes': f'Overpayment from Customer Dues page',
                'date': get_nepal_time().isoformat()
            }
            supabase.table("advance_transactions").insert(transaction_data).execute()
            
            flash_msg = f'✅ Payment of Rs {total_payment:,.2f} recorded!\n'
            flash_msg += f'   • Cash paid: Rs {total_cash_used:,.2f}\n'
            flash_msg += f'   • Advance used: Rs {total_advance_deducted:,.2f}\n'
            flash_msg += f'   • Overpayment: Rs {remaining:,.2f} added as advance balance'
        else:
            if total_advance_deducted > 0:
                flash_msg = f'✅ Payment of Rs {total_payment:,.2f} recorded!\n'
                flash_msg += f'   • Cash paid: Rs {total_cash_used:,.2f}\n'
                flash_msg += f'   • Advance used: Rs {total_advance_deducted:,.2f}'
            else:
                flash_msg = f'✅ Payment of Rs {total_payment:,.2f} recorded successfully!\n'
                flash_msg += f'   • Cash paid: Rs {total_cash_used:,.2f}'
        
        # ========== ADD EMAIL SENDING HERE ==========
        # Send email if requested
        if send_email:
            customer = User.get_by_id(customer_id)
            if customer and customer.get('email'):
                try:
                    customer_name = customer.get('name', 'Customer')
                    customer_email = customer.get('email')
                    
                    # Calculate total remaining due after payment
                    remaining_due = sum(sale.get('due_amount', 0) for sale in unpaid_sales)
                    
                    # Build invoice list HTML
                    invoices_html = ""
                    for inv in paid_invoices:
                        invoices_html += f"""
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{inv['invoice_number']}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right;">Rs {inv['amount']:,.2f}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right;">Rs {inv['new_due']:,.2f}</td>
                        </tr>
                        """
                    
                    # Build email content
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="UTF-8">
                        <title>Payment Receipt</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 16px; }}
                            .header {{ text-align: center; padding-bottom: 20px; border-bottom: 2px solid #0C5B3F; }}
                            .header h2 {{ color: #0C5B3F; margin: 0; }}
                            .amount {{ font-size: 32px; font-weight: bold; color: #16a34a; }}
                            .details {{ margin: 20px 0; padding: 15px; background: #f9fafb; border-radius: 8px; }}
                            .invoice-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                            .invoice-table th {{ background: #f3f4f6; padding: 10px; text-align: left; }}
                            .footer {{ text-align: center; font-size: 12px; color: #888; margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
                            .success {{ color: #16a34a; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="header">
                                <h2>Payment Receipt</h2>
                                <p>{Config.BUSINESS_NAME}</p>
                            </div>
                            
                            <p>Dear <strong>{customer_name}</strong>,</p>
                            
                            <p>Thank you for your payment. Here are the details:</p>
                            
                            <div class="details">
                                <p><strong>Total Payment:</strong> <span class="amount">Rs {total_payment:,.2f}</span></p>
                                <p><strong>Payment Mode:</strong> {payment_mode}</p>
                                <p><strong>Date:</strong> {get_nepal_time().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    """
                    
                    if total_cash_used > 0:
                        html_content += f'<p><strong>Cash Paid:</strong> Rs {total_cash_used:,.2f}</p>'
                    
                    if total_advance_deducted > 0:
                        html_content += f'<p><strong>Advance Used:</strong> Rs {total_advance_deducted:,.2f}</p>'
                    
                    if overpayment_amount > 0:
                        html_content += f'<p><strong>Overpayment (New Advance Credit):</strong> <span class="success">Rs {overpayment_amount:,.2f}</span></p>'
                    
                    html_content += f"""
                                <p><strong>Remaining Due Balance:</strong> Rs {remaining_due:,.2f}</p>
                            </div>
                            
                            <h3>Payment Applied To:</h3>
                            <table class="invoice-table">
                                <thead>
                                    <tr>
                                        <th>Invoice #</th>
                                        <th>Amount Paid</th>
                                        <th>Remaining Due</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {invoices_html if invoices_html else '<tr><td colspan="3" style="padding: 8px; text-align: center;">No invoices updated</td></tr>'}
                                </tbody>
                            </table>
                            
                            <p>Thank you for your business!</p>
                            
                            <div class="footer">
                                <p>{Config.BUSINESS_NAME}<br>Mainapokhar, Bardiya, Nepal</p>
                                <p>For any queries, please contact us at support@adarshoilmill.com.np</p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    
                    subject = f"Payment Receipt from {Config.BUSINESS_NAME}"
                    
                    # Send email via Brevo
                    email_sent = send_invoice_email(customer_email, subject, html_content)
                    
                    if email_sent:
                        print(f"✅ Payment receipt email sent to {customer_email}")
                        flash_msg += f"\n   • Receipt sent to {customer_email}"
                    else:
                        print(f"❌ Failed to send email to {customer_email}")
                        flash_msg += f"\n   • ⚠️ Email failed to send"
                        
                except Exception as email_error:
                    print(f"Email error: {email_error}")
                    flash_msg += f"\n   • ⚠️ Email error: {str(email_error)}"
            else:
                if customer and not customer.get('email'):
                    print(f"⚠️ Cannot send email - customer has no email address")
                    flash_msg += f"\n   • ⚠️ No email address on file"
        # ========== END EMAIL SENDING ==========
        
        # Record audit transaction
        audit_data = {
            'customer_id': customer_id,
            'amount': total_payment,
            'cash_amount': total_cash_used,
            'advance_amount': total_advance_deducted,
            'type': 'bulk_payment',
            'notes': f'Bulk payment: Cash Rs {total_cash_used}, Advance Rs {total_advance_deducted}',
            'date': get_nepal_time().isoformat()
        }
        supabase.table("advance_transactions").insert(audit_data).execute()
        
        flash(flash_msg, 'success')
        return redirect(url_for('admin.customer_dues'))
        
    except Exception as e:
        print(f"Error in record_payment_direct: {e}")
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('admin.customer_dues'))

# ============================================
# ADVANCE BALANCE MANAGEMENT (NEW ROUTES)
# ============================================

@bp.route('/api/customer/<int:customer_id>/advance-balance')
@login_required
@admin_required
def api_get_advance_balance(customer_id):
    """API endpoint to get customer's advance balance"""
    from app.models_supabase import User
    balance = User.get_advance_balance(customer_id)
    return jsonify({'advance_balance': balance, 'customer_id': customer_id})


@bp.route('/customer/<int:customer_id>/add-advance', methods=['GET', 'POST'])
@login_required
@admin_required
def add_customer_advance(customer_id):
    """Manually add advance balance to customer - AJAX ready"""
    from app.models_supabase import User
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    customer = User.get_by_id(customer_id)
    if not customer:
        if is_ajax:
            return jsonify({'success': False, 'error': 'Customer not found'}), 404
        flash('Customer not found', 'danger')
        return redirect(url_for('admin.customers_list'))
    
    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', 0))
            notes = request.form.get('notes', '')
            payment_mode = request.form.get('payment_mode', 'Cash')
            
            if amount <= 0:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Amount must be greater than 0'}), 400
                flash('Amount must be greater than 0', 'danger')
                return redirect(url_for('admin.add_customer_advance', customer_id=customer_id))
            
            # Add advance deposit
            result = User.add_advance_deposit(customer_id, amount, notes)
            
            if result:
                # Record in payments table as well
                payment_data = {
                    'customer_id': customer_id,
                    'amount': amount,
                    'payment_mode': payment_mode,
                    'notes': f'Advance deposit: {notes}' if notes else 'Advance deposit',
                    'created_by': current_user.id
                }
                from app.models_supabase import Payment
                Payment.create(payment_data)
                
                if is_ajax:
                    return jsonify({
                        'success': True,
                        'message': f'Rs.{amount:,.2f} added to {customer["name"]}\'s advance balance!',
                        'new_balance': User.get_advance_balance(customer_id)
                    })
                flash(f'Rs.{amount:,.2f} added to {customer["name"]}\'s advance balance!', 'success')
                return redirect(url_for('admin.customer_dues'))
            else:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Failed to add advance balance'}), 500
                flash('Failed to add advance balance', 'danger')
                
        except Exception as e:
            if is_ajax:
                return jsonify({'success': False, 'error': str(e)}), 500
            flash(f'Error: {str(e)}', 'danger')
    
    # GET request
    current_balance = User.get_advance_balance(customer_id)
    return render_template('admin/add_customer_advance.html', customer=customer, balance=current_balance)

@bp.route('/customer/<int:customer_id>/advance-history')
@login_required
@admin_required
def customer_advance_history(customer_id):
    """View advance transaction history for a customer"""
    from app.models_supabase import User
    
    customer = User.get_by_id(customer_id)
    if not customer:
        flash('Customer not found', 'danger')
        return redirect(url_for('admin.customers_list'))
    
    transactions = User.get_advance_transactions(customer_id)
    current_balance = User.get_advance_balance(customer_id)
    
    return render_template(
        'admin/customer_advance_history.html',
        customer=customer,
        transactions=transactions,
        current_balance=current_balance
    )










@bp.route('/record-payment/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def record_payment(sale_id):
    """Record a payment against a sale (handles advance redemption)"""
    from app.models_supabase import User
    
    sale = Sale.get_by_id(sale_id)
    if not sale:
        flash('Sale not found', 'danger')
        return redirect(url_for('admin.sales_list'))
    
    # Get payment details from form
    advance_used = float(request.form.get('advance_amount', 0) or 0)
    cash_amount = float(request.form.get('amount', 0) or 0)
    payment_mode = request.form.get('payment_mode')
    notes = request.form.get('notes', '')
    send_email = request.form.get('send_email') == 'on'
    
    # Total payment amount
    amount = advance_used + cash_amount
    
    if amount <= 0:
        flash('Invalid payment amount', 'danger')
        return redirect(request.referrer or url_for('admin.sales_list'))
    
    customer_id = sale.get('customer_id')
    
    # Check if advance usage is valid
    if advance_used > 0 and customer_id:
        available_balance = User.get_advance_balance(customer_id)
        if advance_used > available_balance:
            flash(f'Insufficient advance balance. Available: Rs.{available_balance:,.2f}', 'danger')
            return redirect(request.referrer or url_for('admin.sales_list'))
        
        # Deduct advance from customer balance
        User.update_advance_balance(customer_id, advance_used, "deduct")
        
        # Record advance transaction
        from datetime import datetime
        transaction_data = {
            'customer_id': customer_id,
            'sale_id': sale_id,
            'amount': advance_used,
            'type': 'redeem',
            'notes': f'Redeemed for invoice {sale.get("invoice_number")}',
            'date': get_nepal_time().isoformat()
        }
        supabase.table("advance_transactions").insert(transaction_data).execute()
    
    # Get current sale values
    total_amount = sale.get('total_amount', 0)
    current_paid = sale.get('paid_amount', 0)
    current_advance = sale.get('advance_amount', 0)
    
    # Calculate new values
    new_paid = current_paid + amount
    
    if new_paid > total_amount:
        # Overpayment scenario
        new_due = 0
        new_advance = new_paid - total_amount
        payment_status = 'advance'
    elif new_paid == total_amount:
        # Exactly paid
        new_due = 0
        new_advance = 0
        payment_status = 'paid'
    else:
        # Partial payment
        new_due = total_amount - new_paid
        new_advance = 0
        payment_status = 'partial'
    
    # Create payment record
    payment_data = {
        'sale_id': sale_id,
        'customer_id': customer_id,
        'amount': amount,
        'payment_mode': payment_mode,
        'notes': notes + (f' (Advance used: Rs.{advance_used})' if advance_used > 0 else ''),
        'created_by': current_user.id
    }
    
    payment = Payment.create(payment_data)
    
    if payment:
        # Update sale
        Sale.update(sale_id, {
            'paid_amount': new_paid,
            'due_amount': new_due,
            'advance_amount': new_advance,
            'payment_status': payment_status
        })
        
        customer = User.get_by_id(customer_id) if customer_id else None
        
        # Prepare success message
        if advance_used > 0:
            flash_msg = f'Payment of Rs.{amount:,.2f} recorded! (Advance: Rs.{advance_used:,.2f} + Cash: Rs.{cash_amount:,.2f})'
        else:
            flash_msg = f'Payment of Rs.{amount:,.2f} recorded!'
        
        if new_advance > 0:
            flash_msg += f' New advance balance: Rs.{new_advance:,.2f}'
        elif new_due == 0:
            flash_msg += ' Invoice fully paid!'
        else:
            flash_msg += f' Remaining due: Rs.{new_due:,.2f}'
        
        # Send email if requested
        if send_email and customer and customer.get('email'):
            try:
                from app.brevo_service import send_invoice_email
                from app.config import Config
                
                subject = f"Payment Receipt from {Config.BUSINESS_NAME}"
                
                if new_advance > 0:
                    status_msg = f'Advance Payment: Rs.{new_advance:,.2f} (Credit balance)'
                elif new_due == 0:
                    status_msg = 'Fully Paid ✓'
                else:
                    status_msg = f'Remaining Due: Rs.{new_due:,.2f}'
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Payment Receipt</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; }}
                        .container {{ max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 16px; }}
                        .header {{ text-align: center; padding-bottom: 20px; border-bottom: 2px solid #0C5B3F; }}
                        .amount {{ font-size: 32px; font-weight: bold; color: #16a34a; }}
                        .footer {{ text-align: center; font-size: 12px; color: #888; margin-top: 20px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h2 style="color: #0C5B3F;">Payment Receipt</h2>
                        </div>
                        <p>Dear <strong>{customer.get('name')}</strong>,</p>
                        <p>We have received your payment:</p>
                        <p><strong>Invoice:</strong> {sale.get('invoice_number')}</p>
                        <p><strong>Amount:</strong> <span class="amount">Rs.{amount:,.2f}</span></p>
                        <p><strong>Mode:</strong> {payment_mode}</p>
                        <p><strong>Status:</strong> {status_msg}</p>
                        <p>Thank you for your business!</p>
                        <div class="footer">
                            <p>{Config.BUSINESS_NAME} | Mainapokhar, Bardiya, Nepal</p>
                        </div>
                    </div>
                </body>
                </html>
                """
                
                send_invoice_email(customer.get('email'), subject, html_content)
                flash(f'{flash_msg} Receipt sent to {customer.get("email")}', 'success')
            except Exception as e:
                print(f"Email error: {e}")
                flash(f'{flash_msg} (Email failed)', 'warning')
        else:
            flash(flash_msg, 'success')
        
      
# Redirect back
        if customer_id:
            return redirect(url_for('admin.customer_dues'))
        else:
            return redirect(url_for('admin.sales_list'))








# ============================================
# MASTER ADMIN PANEL - BATCH SALES ENTRY
# ============================================

def _resolve_sale_customer(customer_id, customer_name, email=None):
    """Resolve or auto-create customer using the same rules as add_sale."""
    name = (customer_name or '').strip()
    customer_id_final = None

    if customer_id and str(customer_id).isdigit():
        customer_id_final = int(customer_id)
        user_data = User.get_by_id(customer_id_final)
        if user_data:
            return customer_id_final, user_data.get('name', name), user_data.get('email')

    if not name:
        return None, 'Walk-in Customer', None

    user_data = User.get_by_username(name)
    if user_data:
        if email and not user_data.get('email'):
            User.update(user_data.get('id'), {'email': email})
        return user_data.get('id'), user_data.get('name'), user_data.get('email')

    new_user = User.create({
        'name': name,
        'username': name,
        'email': email if email else None,
        'role': 'customer'
    })
    if new_user:
        return new_user.get('id'), new_user.get('name'), new_user.get('email')

    return None, name, None


def _build_sale_items_from_batch(items):
    """Normalize and validate line items for batch sale creation."""
    sale_items = []
    for item in items:
        product_name = (item.get('product_name') or '').strip()
        if not product_name:
            continue

        quantity = float(item.get('quantity', 0) or 0)
        rate = float(item.get('rate', 0) or 0)
        
        # Allow rate 0 for byproduct exchange
        if quantity <= 0:
            continue

        subtotal = float(item.get('subtotal', 0) or 0)
        if subtotal <= 0 and rate > 0:
            subtotal = quantity * rate

        sale_items.append({
            'product_name': product_name,
            'quantity': quantity,
            'unit': item.get('unit', 'Kg') or 'Kg',
            'rate': rate,
            'subtotal': subtotal
        })

    return sale_items


@bp.route('/master-panel')
@login_required
@admin_required
def master_panel():
    """Master admin panel for batch sales entry"""
    from app.models_supabase import User
    from datetime import datetime
    
    # Get all customers for dropdown
    all_customers = User.get_all_customers()
    customers_list = [{'id': c.get('id'), 'name': c.get('name')} for c in all_customers]
    
    return render_template(
        'admin/master_panel.html',
        customers=customers_list,
        business_name=Config.BUSINESS_NAME
    )


@bp.route('/master-panel/api/customer/search', methods=['GET'])
@login_required
@admin_required
def master_panel_search_customer():
    """Search or create customer on the fly - SAME AS add_sale"""
    from app.models_supabase import User
    
    q = request.args.get('name', '').strip()
    
    if not q:
        return jsonify({'exists': False, 'customers': []})
    
    customers_data, _ = User.get_customers_paginated(1, 10, q)
    
    exact_match = None
    for c in customers_data:
        if c.get('name', '').lower() == q.lower():
            exact_match = {
                'id': c.get('id'),
                'name': c.get('name'),
                'advance_balance': User.get_advance_balance(c.get('id'))
            }
            break
    
    if exact_match:
        return jsonify({
            'exists': True,
            'exact_match': exact_match,
            'suggestions': [{'id': c.get('id'), 'name': c.get('name')} for c in customers_data[:5]]
        })
    elif customers_data:
        return jsonify({
            'exists': False,
            'suggestions': [{'id': c.get('id'), 'name': c.get('name')} for c in customers_data[:5]],
            'can_create': True
        })
    else:
        return jsonify({
            'exists': False,
            'suggestions': [],
            'can_create': True
        })


@bp.route('/master-panel/api/customer/create', methods=['POST'])
@login_required
@admin_required
def master_panel_create_customer():
    """Auto-create a new customer - SAME AS add_sale"""
    from app.models_supabase import User
    
    data = request.get_json()
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'success': False, 'error': 'Customer name required'})
    
    existing = User.get_by_username(name)
    if existing:
        return jsonify({
            'success': True,
            'exists': True,
            'customer': {
                'id': existing.get('id'),
                'name': existing.get('name'),
                'advance_balance': User.get_advance_balance(existing.get('id'))
            }
        })
    
    user_data = {
        'name': name,
        'username': name,
        'role': 'customer',
        'is_active': True
    }
    
    new_user = User.create(user_data)
    
    if new_user:
        return jsonify({
            'success': True,
            'exists': False,
            'customer': {
                'id': new_user.get('id'),
                'name': new_user.get('name'),
                'advance_balance': 0
            }
        })
    else:
        return jsonify({'success': False, 'error': 'Failed to create customer'})


@bp.route('/master-panel/api/customer/<int:customer_id>/advance')
@login_required
@admin_required
def master_panel_get_advance(customer_id):
    """Get customer's advance balance"""
    from app.models_supabase import User
    
    balance = User.get_advance_balance(customer_id)
    return jsonify({'advance_balance': balance})


@bp.route('/master-panel/save', methods=['POST'])
@login_required
@admin_required
def master_panel_save_sales():
    """Save all batch sales - EXACTLY LIKE add_sale route with email support"""
    from app.utils import generate_invoice_number
    from app.brevo_service import send_invoice_email
    from app.config import Config

    data = request.get_json()
    customers_data = data.get('customers', [])

    if not customers_data:
        return jsonify({'success': False, 'error': 'No sales data provided'})

    results = []
    errors = []

    for customer_entry in customers_data:
        try:
            customer_name = (customer_entry.get('customer_name') or '').strip()
            customer_id = customer_entry.get('customer_id')
            items = customer_entry.get('items', [])
            advance_used = float(customer_entry.get('advance_used', 0) or 0)
            cash_paid = float(customer_entry.get('cash_paid', 0) or 0)
            email = customer_entry.get('email', '')
            send_email_flag = customer_entry.get('send_email', False)  # NEW: get email flag

            # ========== BYPRODUCT EXCHANGE LOGIC (SAME AS ADD_SALE) ==========
            exchange_mustard_cake = customer_entry.get('exchange_mustard_cake', False)
            exchange_rice_bran = customer_entry.get('exchange_rice_bran', False)

            # Apply byproduct exchange to line items
            sale_items = apply_byproduct_exchange_to_line_items(
                items, exchange_mustard_cake, exchange_rice_bran
            )

            # Build sale note
            sale_note = build_byproduct_note(exchange_mustard_cake, exchange_rice_bran)
            # =============================================

            # Resolve or create customer (SAME AS ADD_SALE)
            customer_id_final = None
            if customer_id and str(customer_id).isdigit():
                customer_id_final = int(customer_id)
                user_data = User.get_by_id(customer_id_final)
                if user_data:
                    customer_name = user_data.get('name')
                    if email and not user_data.get('email'):
                        User.update(customer_id_final, {'email': email})
            else:
                user_data = User.get_by_username(customer_name)
                if user_data:
                    customer_id_final = user_data.get('id')
                    customer_name = user_data.get('name')
                    if email and not user_data.get('email'):
                        User.update(customer_id_final, {'email': email})
                else:
                    new_user = User.create({
                        'name': customer_name,
                        'username': customer_name,
                        'email': email if email else None,
                        'role': 'customer',
                        'is_active': True
                    })
                    if new_user:
                        customer_id_final = new_user.get('id')
                        customer_name = new_user.get('name')

            # Calculate total amount from sale items
            total_amount = sum(float(item.get('subtotal', 0)) for item in sale_items)

            # Validate advance usage (SAME AS ADD_SALE)
            if advance_used > 0 and customer_id_final:
                available_balance = User.get_advance_balance(customer_id_final)
                if advance_used > available_balance:
                    errors.append(f'Insufficient advance balance for {customer_name}. Available: Rs.{available_balance:,.2f}')
                    continue
                if advance_used > total_amount:
                    errors.append(f'Advance cannot exceed total for {customer_name} (Rs.{total_amount:,.2f})')
                    continue

            # Prepare sale data (SAME AS ADD_SALE)
            sale_data = {
                'customer_id': customer_id_final,
                'customer_name': customer_name if customer_name else 'Walk-in Customer',
                'invoice_number': generate_invoice_number(),
                'total_amount': float(total_amount),
                'paid_amount': float(cash_paid),
                'created_by': current_user.id if current_user.id else None,
                'date': get_nepal_time().isoformat(),
                'notes': sale_note
            }

            # Format sale items (SAME AS ADD_SALE)
            sale_items_formatted = []
            for item in sale_items:
                sale_items_formatted.append({
                    'product_name': item.get('product_name'),
                    'quantity': float(item.get('quantity', 0)),
                    'unit': item.get('unit', 'Kg'),
                    'rate': float(item.get('rate', 0)),
                    'subtotal': float(item.get('subtotal', 0))
                })

            # Create sale (SAME AS ADD_SALE)
            sale = Sale.create(sale_data, sale_items_formatted, advance_used)

            # NEW: Send email if requested
            email_sent = False
            if sale and send_email_flag and email:
                try:
                    # Prepare sale data for email template
                    sale_for_email = sale.copy()
                    sale_for_email['customer_name'] = customer_name
                    sale_for_email['customer_email'] = email
                    sale_for_email['items'] = sale_items_formatted
                    sale_for_email['notes'] = sale_note
                    
                    # Calculate due amount
                    due_amount = sale.get('due_amount', 0)
                    if due_amount == 0 and cash_paid + advance_used > total_amount:
                        due_amount = 0  # Overpayment becomes advance
                    
                    subject = f"Invoice from {Config.BUSINESS_NAME} - #{sale.get('invoice_number')}"
                    
                    html_content = render_template(
                        'admin/invoice_email.html',
                        sale=sale_for_email,
                        business_name=Config.BUSINESS_NAME,
                        total_amount=total_amount,
                        paid_amount=cash_paid,
                        due_amount=due_amount
                    )
                    
                    email_sent = send_invoice_email(email, subject, html_content)
                    print(f"Email sent to {email}: {email_sent}")
                    
                except Exception as e:
                    print(f"Email error for {customer_name} ({email}): {e}")
                    email_sent = False

            if sale:
                results.append({
                    'customer': customer_name,
                    'invoice': sale.get('invoice_number'),
                    'total': total_amount,
                    'advance_used': advance_used,
                    'cash_paid': cash_paid,
                    'due_amount': sale.get('due_amount', 0),
                    'advance_credit': sale.get('advance_amount', 0),
                    'payment_status': sale.get('payment_status', 'partial'),
                    'email_sent': email_sent  # NEW: track email status
                })
            else:
                errors.append(f"Failed to create sale for {customer_name}")

        except Exception as e:
            print(f"Error processing customer {customer_entry.get('customer_name')}: {e}")
            errors.append(f"Error for {customer_entry.get('customer_name')}: {str(e)}")
            continue

    if errors and not results:
        return jsonify({'success': False, 'errors': errors, 'results': results})

    if errors:
        return jsonify({
            'success': True,
            'errors': errors,
            'results': results,
            'message': f'Created {len(results)} sale(s) with {len(errors)} error(s)'
        })

    return jsonify({
        'success': True,
        'message': f'Successfully created {len(results)} sale(s)',
        'results': results
    })
# ============================================
# EXCEL EXPORT / IMPORT - BATCH SALES
# ============================================

SALES_EXCEL_COLUMNS = [
    'Customer Name',
    'Email',
    'Product Name',
    'Quantity',
    'Rate',
    'Unit',
    'Total Amount',
    'Advance Used',
    'Cash Paid',
    'Exchange Mustard Cake',
    'Exchange Rice Bran'
]


def _normalize_sales_unit(unit):
    if not unit or str(unit) == 'nan':
        return 'Kg'
    value = str(unit).strip()
    lower = value.lower()
    if lower in ('kg', 'kgs', 'kilogram', 'kilograms'):
        return 'Kg'
    if lower in ('liter', 'litre', 'l', 'ltr'):
        return 'Liter'
    if lower in ('piece', 'pieces', 'pcs', 'pc'):
        return 'Piece'
    if value in ('Kg', 'Liter', 'Piece'):
        return value
    return 'Kg'


def _due_or_advance_label(sale):
    due = float(sale.get('due_amount') or 0)
    advance_credit = float(sale.get('advance_amount') or 0)
    if due > 0:
        return f'Due: {due:.2f}'
    if advance_credit > 0:
        return f'Advance: {advance_credit:.2f}'
    return 'Paid'


def _get_excel_product_name(row):
    for column in ('Product Name', 'Product'):
        if column in row.index:
            value = row.get(column)
            if value is not None and str(value).strip() and str(value) != 'nan':
                return str(value).strip()
    return ''


def _validate_sales_excel_columns(df):
    missing = []
    required = ['Customer Name', 'Product Name', 'Quantity', 'Rate']
    for col in required:
        if col not in df.columns:
            missing.append(col)
    return missing


def _get_customer_payment_values(group, df):
    # SUM Advance Used from all rows in the group
    advance_used = 0.0
    if 'Advance Used' in df.columns:
        for val in group['Advance Used']:
            if pd.notna(val) and val:
                advance_used += float(val)

    # SUM Cash Paid from all rows in the group
    cash_paid = 0.0
    if 'Cash Paid' in df.columns:
        for val in group['Cash Paid']:
            if pd.notna(val) and val:
                cash_paid += float(val)
    elif 'Total Paid' in df.columns:
        total_paid = 0.0
        for val in group['Total Paid']:
            if pd.notna(val) and val:
                total_paid += float(val)
        cash_paid = max(0.0, total_paid - advance_used)
    
    # Exchange flags from first row (only need once per sale)
    exchange_mustard_cake = False
    if 'Exchange Mustard Cake' in df.columns:
        val = str(group['Exchange Mustard Cake'].iloc[0] or '').lower()
        exchange_mustard_cake = val in ('yes', 'true', '1', 'on')
    
    exchange_rice_bran = False
    if 'Exchange Rice Bran' in df.columns:
        val = str(group['Exchange Rice Bran'].iloc[0] or '').lower()
        exchange_rice_bran = val in ('yes', 'true', '1', 'on')
    
    return advance_used, cash_paid, exchange_mustard_cake, exchange_rice_bran


@bp.route('/export-sales-excel')
@login_required
@admin_required
def export_sales_excel():
    """Export all sales to Excel with customer and item details"""
    import pandas as pd
    import io
    
    all_sales = Sale.get_all_with_items_bulk(limit=10000)

    customer_ids = {s['customer_id'] for s in all_sales if s.get('customer_id')}
    customer_map = {}
    if customer_ids:
        cust_response = supabase.table("users").select("id, name, email").in_("id", list(customer_ids)).execute()
        customer_map = {c['id']: c for c in cust_response.data}

    export_data = []
    
    for sale in all_sales:
        items = sale.get('items', [])
        
        customer_name = sale.get('customer_name', 'Walk-in Customer')
        customer_email = ''
        if sale.get('customer_id') and sale['customer_id'] in customer_map:
            customer = customer_map[sale['customer_id']]
            customer_name = customer.get('name', customer_name)
            customer_email = customer.get('email', '')
        
        advance_used = float(sale.get('advance_used') or 0)
        cash_paid = float(sale.get('paid_amount') or 0)
        
        # Parse exchange from notes
        note = sale.get('notes', '')
        exchange_mustard_cake = 'mustard cake' in note.lower()
        exchange_rice_bran = 'rice bran' in note.lower()

        for item in items:
            export_data.append({
                'Customer Name': customer_name,
                'Email': customer_email,
                'Product Name': item.get('product_name', ''),
                'Quantity': item.get('quantity', 0),
                'Rate': item.get('rate', 0),
                'Unit': _normalize_sales_unit(item.get('unit', 'Kg')),
                'Total Amount': item.get('subtotal', 0),
                'Advance Used': advance_used,
                'Cash Paid': cash_paid,
                'Exchange Mustard Cake': 'Yes' if exchange_mustard_cake else 'No',
                'Exchange Rice Bran': 'Yes' if exchange_rice_bran else 'No'
            })
    
    if not export_data:
        export_data = [{'Message': 'No sales data available'}]
    
    df = pd.DataFrame(export_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Sales Data', index=False)
        
        worksheet = writer.sheets['Sales Data']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    output.seek(0)
    
    filename = f"sales_export_{get_nepal_time().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@bp.route('/import-sales-excel', methods=['POST'])
@login_required
@admin_required
def import_sales_excel():
    """Import sales from Excel file (preview or save)"""
    import pandas as pd

    preview_only = request.form.get('preview', '').lower() in ('1', 'true', 'yes')

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})

    file = request.files['file']

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})

    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'Please upload an Excel file (.xlsx or .xls)'})

    try:
        df = pd.read_excel(file)
        
        missing_columns = _validate_sales_excel_columns(df)
        if missing_columns:
            return jsonify({
                'success': False,
                'error': f'Missing columns: {", ".join(missing_columns)}'
            })

        import_results = []
        errors = []
        preview_customers = []

        grouped = df.groupby('Customer Name')

        for customer_name, group in grouped:
            customer_name = str(customer_name).strip()
            if not customer_name or customer_name == 'nan':
                customer_name = 'Walk-in Customer'
            
            # Get customer email from first row
            customer_email = None
            if 'Email' in df.columns:
                customer_email = str(group['Email'].iloc[0]) if group['Email'].iloc[0] not in (None, 'nan') else None
            
            # Find or create customer
            existing = User.get_by_username(customer_name)
            if existing:
                customer_id = existing.get('id')
                customer_name = existing.get('name')
            else:
                new_user = User.create({
                    'name': customer_name,
                    'username': customer_name,
                    'email': customer_email,
                    'role': 'customer',
                    'is_active': True
                })
                if new_user:
                    customer_id = new_user.get('id')
                    customer_name = new_user.get('name')
                else:
                    errors.append(f"Failed to create customer: {customer_name}")
                    continue
            
            # Build items from group
            items = []
            total_amount = 0
            
            for _, row in group.iterrows():
                product = _get_excel_product_name(row)
                if not product:
                    continue

                quantity = float(row.get('Quantity', 0) or 0)
                rate = float(row.get('Rate', 0) or 0)
                unit = _normalize_sales_unit(row.get('Unit', 'Kg'))

                if 'Total Amount' in row.index and row.get('Total Amount') not in (None, '') and str(row.get('Total Amount')) != 'nan':
                    subtotal = float(row.get('Total Amount') or 0)
                else:
                    subtotal = quantity * rate
                total_amount += subtotal

                items.append({
                    'product_name': product,
                    'quantity': quantity,
                    'unit': unit,
                    'rate': rate,
                    'subtotal': subtotal
                })
            
            if not items:
                errors.append(f"No valid items for {customer_name}")
                continue

            advance_used, cash_paid, exchange_mustard_cake, exchange_rice_bran = _get_customer_payment_values(group, df)

            if preview_only:
                advance_balance = User.get_advance_balance(customer_id) if customer_id else 0
                preview_customers.append({
                    'customer_id': customer_id,
                    'customer_name': customer_name,
                    'email': customer_email,
                    'items': items,
                    'advance_used': advance_used,
                    'cash_paid': cash_paid,
                    'advance_balance': advance_balance,
                    'exchange_mustard_cake': exchange_mustard_cake,
                    'exchange_rice_bran': exchange_rice_bran
                })
                continue

            # Apply byproduct exchange
            items = apply_byproduct_exchange_to_line_items(items, exchange_mustard_cake, exchange_rice_bran)
            sale_note = build_byproduct_note(exchange_mustard_cake, exchange_rice_bran)

            if advance_used > 0:
                available = User.get_advance_balance(customer_id)
                if advance_used > available:
                    errors.append(f"Insufficient advance for {customer_name}. Available: Rs.{available:,.2f}")
                    continue
                if advance_used > total_amount:
                    errors.append(f"Advance exceeds total for {customer_name}. Total: Rs.{total_amount:,.2f}")
                    continue
            
            sale_data = {
                'customer_id': customer_id,
                'customer_name': customer_name,
                'invoice_number': generate_invoice_number(),
                'total_amount': total_amount,
                'paid_amount': cash_paid,
                'created_by': current_user.id,
                'date': get_nepal_time().isoformat(),
                'notes': sale_note
            }
            
            sale = Sale.create(sale_data, items, advance_used)
            
            if sale:
                import_results.append({
                    'customer': customer_name,
                    'invoice': sale.get('invoice_number'),
                    'total': total_amount,
                    'items': len(items)
                })
            else:
                errors.append(f"Failed to create sale for {customer_name}")
        
        if preview_only:
            if errors and not preview_customers:
                return jsonify({'success': False, 'error': '; '.join(errors[:5])})
            return jsonify({
                'success': True,
                'preview': True,
                'message': f'Loaded {len(preview_customers)} customer(s) from Excel. Review and click Save All.',
                'customers': preview_customers,
                'errors': errors
            })

        if errors and not import_results:
            return jsonify({'success': False, 'error': '; '.join(errors[:5]), 'errors': errors})

        if errors:
            return jsonify({
                'success': True,
                'message': f'Imported {len(import_results)} sale(s) with {len(errors)} error(s)',
                'results': import_results,
                'errors': errors
            })

        return jsonify({
            'success': True,
            'message': f'Successfully imported {len(import_results)} sale(s)!',
            'results': import_results
        })

    except Exception as e:
        return jsonify({'success': False, 'error': f'Error importing file: {str(e)}'})


@bp.route('/download-sales-template')
@login_required
@admin_required
def download_sales_template():
    """Download sample Excel template for sales import"""
    import pandas as pd
    import io
    
    sample_data = [
        {
            'Customer Name': 'Ram Bahadur',
            'Email': 'ram@example.com',
            'Product Name': 'Mustard Oil Extraction',
            'Quantity': 10,
            'Rate': 10,
            'Unit': 'Kg',
            'Total Amount': 100,
            'Advance Used': 0,
            'Cash Paid': 100,
            'Exchange Mustard Cake': 'No',
            'Exchange Rice Bran': 'No'
        },
        {
            'Customer Name': 'Ram Bahadur',
            'Email': 'ram@example.com',
            'Product Name': 'Wheat Flour',
            'Quantity': 5,
            'Rate': 80,
            'Unit': 'Kg',
            'Total Amount': 400,
            'Advance Used': 0,
            'Cash Paid': 100,
            'Exchange Mustard Cake': 'No',
            'Exchange Rice Bran': 'No'
        },
        {
            'Customer Name': 'Sita Sharma',
            'Email': 'sita@example.com',
            'Product Name': 'Mustard Oil Extraction',
            'Quantity': 20,
            'Rate': 10,
            'Unit': 'Kg',
            'Total Amount': 200,
            'Advance Used': 50,
            'Cash Paid': 150,
            'Exchange Mustard Cake': 'Yes',
            'Exchange Rice Bran': 'No'
        }
    ]
    
    df = pd.DataFrame(sample_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Sales Template', index=False)
        
        instructions = pd.DataFrame({
            'Instructions': [
                '1. Customer Name: Required - rows with same name become one sale',
                '2. Email: Optional - customer email for invoice',
                '3. Product Name: Required - product for each line item',
                '4. Quantity: Required - number of units',
                '5. Rate: Required - price per unit (0 for byproduct exchange)',
                '6. Unit: Optional - Kg, Liter, Piece, Quintal (default Kg)',
                '7. Total Amount: Optional - line total (auto-calculated if blank)',
                '8. Advance Used: Optional - amount deducted from customer advance balance',
                '9. Cash Paid: Optional - cash payment amount',
                '10. Exchange Mustard Cake: Yes/No - makes Mustard Oil Extraction FREE',
                '11. Exchange Rice Bran: Yes/No - makes Others service FREE'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='sales_import_template.xlsx'
    )

# ============================================
# BATCH SALE ROLLBACK / UNDO FEATURE
# ============================================

@bp.route('/master-panel/save-with-rollback', methods=['POST'])
@login_required
@admin_required
def master_panel_save_with_rollback():
    """Save batch sales with rollback capability"""
    from app.utils import generate_invoice_number
    from app.brevo_service import send_invoice_email
    from app.config import Config

    data = request.get_json()
    customers_data = data.get('customers', [])

    if not customers_data:
        return jsonify({'success': False, 'error': 'No sales data provided'})

    # Generate unique batch ID for this save operation
    batch_id = str(uuid.uuid4())
    created_sales = []
    errors = []
    results = []

    # Create batch history record
    batch_history = {
        'batch_id': batch_id,
        'user_id': current_user.id,
        'total_customers': len(customers_data),
        'status': 'active'
    }
    
    try:
        supabase.table("batch_sales_history").insert(batch_history).execute()
    except Exception as e:
        print(f"Warning: Could not create batch history: {e}")

    for customer_entry in customers_data:
        try:
            customer_name = (customer_entry.get('customer_name') or '').strip()
            customer_id = customer_entry.get('customer_id')
            items = customer_entry.get('items', [])
            advance_used = float(customer_entry.get('advance_used', 0) or 0)
            cash_paid = float(customer_entry.get('cash_paid', 0) or 0)
            email = customer_entry.get('email', '')
            send_email_flag = customer_entry.get('send_email', False)

            # Byproduct exchange logic
            exchange_mustard_cake = customer_entry.get('exchange_mustard_cake', False)
            exchange_rice_bran = customer_entry.get('exchange_rice_bran', False)
            
            sale_items = apply_byproduct_exchange_to_line_items(
                items, exchange_mustard_cake, exchange_rice_bran
            )
            sale_note = build_byproduct_note(exchange_mustard_cake, exchange_rice_bran)

            # Resolve or create customer
            customer_id_final = None
            if customer_id and str(customer_id).isdigit():
                customer_id_final = int(customer_id)
                user_data = User.get_by_id(customer_id_final)
                if user_data:
                    customer_name = user_data.get('name')
                    if email and not user_data.get('email'):
                        User.update(customer_id_final, {'email': email})
            else:
                user_data = User.get_by_username(customer_name)
                if user_data:
                    customer_id_final = user_data.get('id')
                    customer_name = user_data.get('name')
                    if email and not user_data.get('email'):
                        User.update(customer_id_final, {'email': email})
                else:
                    new_user = User.create({
                        'name': customer_name,
                        'username': customer_name,
                        'email': email if email else None,
                        'role': 'customer',
                        'is_active': True
                    })
                    if new_user:
                        customer_id_final = new_user.get('id')
                        customer_name = new_user.get('name')

            total_amount = sum(float(item.get('subtotal', 0)) for item in sale_items)

            # Validate advance usage
            if advance_used > 0 and customer_id_final:
                available_balance = User.get_advance_balance(customer_id_final)
                if advance_used > available_balance:
                    errors.append(f'Insufficient advance balance for {customer_name}')
                    continue
                if advance_used > total_amount:
                    errors.append(f'Advance cannot exceed total for {customer_name}')
                    continue

            # Prepare sale data
            sale_data = {
                'customer_id': customer_id_final,
                'customer_name': customer_name if customer_name else 'Walk-in Customer',
                'invoice_number': generate_invoice_number(),
                'total_amount': float(total_amount),
                'paid_amount': float(cash_paid),
                'created_by': current_user.id if current_user.id else None,
                'date': get_nepal_time().isoformat(),
                'notes': sale_note
            }

            # Format sale items
            sale_items_formatted = []
            for item in sale_items:
                sale_items_formatted.append({
                    'product_name': item.get('product_name'),
                    'quantity': float(item.get('quantity', 0)),
                    'unit': item.get('unit', 'Kg'),
                    'rate': float(item.get('rate', 0)),
                    'subtotal': float(item.get('subtotal', 0))
                })

            # CREATE SNAPSHOT BEFORE SAVING (for rollback)
            snapshot_data = {
                'batch_id': batch_id,
                'sale_data': sale_data,
                'sale_items_data': sale_items_formatted,
                'sale_id': None
            }
            
            # Create sale
            sale = Sale.create(sale_data, sale_items_formatted, advance_used)

            if sale:
                # Update snapshot with sale_id
                snapshot_data['sale_id'] = sale.get('id')
                supabase.table("batch_sale_snapshots").insert(snapshot_data).execute()
                
                created_sales.append(sale.get('id'))
                
                # Send email if requested
                email_sent = False
                if send_email_flag and email:
                    try:
                        sale_for_email = sale.copy()
                        sale_for_email['customer_name'] = customer_name
                        sale_for_email['customer_email'] = email
                        sale_for_email['items'] = sale_items_formatted
                        
                        subject = f"Invoice from {Config.BUSINESS_NAME} - #{sale.get('invoice_number')}"
                        html_content = render_template(
                            'admin/invoice_email.html',
                            sale=sale_for_email,
                            business_name=Config.BUSINESS_NAME,
                            total_amount=total_amount,
                            paid_amount=cash_paid,
                            due_amount=sale.get('due_amount', 0)
                        )
                        email_sent = send_invoice_email(email, subject, html_content)
                    except Exception as e:
                        print(f"Email error: {e}")
                
                results.append({
                    'customer': customer_name,
                    'invoice': sale.get('invoice_number'),
                    'total': total_amount,
                    'sale_id': sale.get('id'),
                    'email_sent': email_sent
                })
            else:
                errors.append(f"Failed to create sale for {customer_name}")

        except Exception as e:
            print(f"Error: {e}")
            errors.append(str(e))
            continue

    # Update batch history with total amount
    total_sales_amount = sum(r.get('total', 0) for r in results)
    try:
        supabase.table("batch_sales_history").update({
            'total_amount': total_sales_amount
        }).eq('batch_id', batch_id).execute()
    except Exception as e:
        print(f"Warning: Could not update batch history: {e}")

    response_data = {
        'success': len(results) > 0,
        'batch_id': batch_id,
        'results': results,
        'errors': errors,
        'total_sales': len(results),
        'total_amount': total_sales_amount
    }

    if errors:
        response_data['message'] = f'Created {len(results)} sale(s) with {len(errors)} error(s)'
    else:
        response_data['message'] = f'Successfully created {len(results)} sale(s)'

    return jsonify(response_data)


@bp.route('/master-panel/rollback/<batch_id>', methods=['POST'])
@login_required
@admin_required
def rollback_batch_sales(batch_id):
    """Rollback/undo a batch of sales"""
    from app.models_supabase import User
    
    try:
        # Get batch history
        batch_response = supabase.table("batch_sales_history")\
            .select("*")\
            .eq('batch_id', batch_id)\
            .execute()
        
        if not batch_response.data:
            return jsonify({'success': False, 'error': 'Batch not found'})
        
        batch = batch_response.data[0]
        
        if batch.get('status') == 'rolled_back':
            return jsonify({'success': False, 'error': 'This batch has already been rolled back'})
        
        # Get all snapshots for this batch
        snapshots_response = supabase.table("batch_sale_snapshots")\
            .select("*")\
            .eq('batch_id', batch_id)\
            .execute()
        
        if not snapshots_response.data:
            return jsonify({'success': False, 'error': 'No snapshots found for this batch'})
        
        rolled_back_sales = []
        rollback_errors = []
        
        for snapshot in snapshots_response.data:
            sale_id = snapshot.get('sale_id')
            if not sale_id:
                continue
            
            try:
                # Get the sale before deletion (for advance refund)
                sale = Sale.get_by_id(sale_id)
                
                if sale:
                    customer_id = sale.get('customer_id')
                    advance_used = sale.get('advance_used', 0)
                    
                    # Refund advance back to customer
                    if customer_id and advance_used > 0:
                        User.update_advance_balance(customer_id, advance_used, "add")
                        
                        # Record refund transaction
                        transaction_data = {
                            'customer_id': customer_id,
                            'sale_id': sale_id,
                            'amount': advance_used,
                            'type': 'rollback_refund',
                            'notes': f'Refunded due to batch rollback (Batch: {batch_id})',
                            'date': get_nepal_time().isoformat()
                        }
                        supabase.table("advance_transactions").insert(transaction_data).execute()
                    
                    # Delete sale items
                    supabase.table("sale_items").delete().eq("sale_id", sale_id).execute()
                    
                    # Delete the sale
                    supabase.table("sales").delete().eq("id", sale_id).execute()
                    
                    rolled_back_sales.append(sale_id)
                    
            except Exception as e:
                rollback_errors.append(f"Failed to rollback sale {sale_id}: {str(e)}")
        
        # Update batch status
        supabase.table("batch_sales_history").update({
            'status': 'rolled_back',
            'rolled_back_at': get_nepal_time().isoformat(),
            'rolled_back_by': current_user.id,
            'rollback_reason': request.json.get('reason', 'Manual rollback') if request.json else 'Manual rollback'
        }).eq('batch_id', batch_id).execute()
        
        # Log the rollback
        log_data = {
            'batch_id': batch_id,
            'rolled_back_by': current_user.id,
            'reason': request.json.get('reason', 'Manual rollback') if request.json else 'Manual rollback',
            'affected_sales': rolled_back_sales
        }
        supabase.table("batch_rollback_log").insert(log_data).execute()
        
        return jsonify({
            'success': True,
            'message': f'Successfully rolled back {len(rolled_back_sales)} sales',
            'rolled_back_sales': rolled_back_sales,
            'errors': rollback_errors
        })
        
    except Exception as e:
        print(f"Rollback error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@bp.route('/master-panel/batch-history')
@login_required
@admin_required
def get_batch_history():
    """Get list of all batches for rollback selection"""
    try:
        response = supabase.table("batch_sales_history")\
            .select("*, users!batch_sales_history_user_id_fkey(name)")\
            .order('created_at', desc=True)\
            .limit(50)\
            .execute()
        
        batches = []
        for batch in response.data:
            batches.append({
                'batch_id': batch.get('batch_id'),
                'created_at': batch.get('created_at'),
                'total_customers': batch.get('total_customers'),
                'total_amount': batch.get('total_amount', 0),
                'status': batch.get('status', 'active'),
                'user_name': batch.get('users', {}).get('name', 'Unknown') if batch.get('users') else 'Unknown'
            })
        
        return jsonify({'success': True, 'batches': batches})
        
    except Exception as e:
        print(f"Error fetching batch history: {e}")
        return jsonify({'success': False, 'error': str(e)})