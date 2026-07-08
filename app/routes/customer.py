from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from flask_login import login_required, current_user
from app.models_supabase import User
from app.supabase_client import supabase
from app.brevo_service import send_reset_email
from app.config import Config
import random
from datetime import datetime, timedelta
import re
import json
from app.brevo_service import send_reset_email, BREVO_API_KEY

bp = Blueprint('customer', __name__, url_prefix='/customer')


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_customer_summary(customer_id):
    """
    Get customer financial summary including:
    - Total purchases
    - Total payments
    - Pending due
    - Advance balance
    """
    try:
        # Get all sales for this customer
        sales_response = supabase.table("sales")\
            .select("total_amount, paid_amount, due_amount, advance_used, advance_amount")\
            .eq("customer_id", customer_id)\
            .execute()
        
        sales_data = sales_response.data or []
        
        # Calculate totals from sales
        total_purchases = sum(float(s.get('total_amount', 0)) for s in sales_data)
        total_paid = sum(float(s.get('paid_amount', 0)) for s in sales_data)
        pending_due = sum(float(s.get('due_amount', 0)) for s in sales_data)
        advance_balance = sum(float(s.get('advance_amount', 0)) for s in sales_data)
        
        # Also get direct payments for better accuracy
        payments_response = supabase.table("payments")\
            .select("amount")\
            .eq("customer_id", customer_id)\
            .execute()
        
        payments_data = payments_response.data or []
        total_payments = sum(float(p.get('amount', 0)) for p in payments_data)
        
        # If no payments found, use paid_amount from sales
        if total_payments == 0:
            total_payments = total_paid
        
        # Get total number of sales
        total_sales = len(sales_data)
        
        return {
            'total_purchases': total_purchases,
            'total_payments': total_payments,
            'pending_due': pending_due,
            'advance_balance': advance_balance,
            'total_sales': total_sales
        }
        
    except Exception as e:
        print(f"Error getting customer summary: {e}")
        return {
            'total_purchases': 0,
            'total_payments': 0,
            'pending_due': 0,
            'advance_balance': 0,
            'total_sales': 0
        }


def verify_otp(username, otp, purpose):
    """
    Reusable OTP verification function
    """
    try:
        response = supabase.table("otp_requests")\
            .select("*")\
            .eq("username", username)\
            .eq("purpose", purpose)\
            .gte("expires_at", datetime.now().isoformat())\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        
        if not response.data:
            return False, "OTP expired or not found. Please request a new OTP."
        
        stored_data = response.data[0]
        
        if stored_data.get('attempts', 0) >= 5:
            supabase.table("otp_requests").delete().eq("id", stored_data['id']).execute()
            return False, "Too many failed attempts. Please request a new OTP."
        
        if stored_data.get('otp') != otp:
            supabase.table("otp_requests").update({"attempts": stored_data.get('attempts', 0) + 1}).eq("id", stored_data['id']).execute()
            remaining = 5 - (stored_data.get('attempts', 0) + 1)
            return False, f"Wrong OTP. {remaining} attempts remaining."
        
        # OTP verified - delete it
        supabase.table("otp_requests").delete().eq("id", stored_data['id']).execute()
        return True, "OTP verified successfully"
        
    except Exception as e:
        print(f"Error verifying OTP: {e}")
        return False, "Error verifying OTP. Please try again."


# ============================================
# ROUTES
# ============================================

@bp.route('/dashboard')
@login_required
def dashboard():
    """Customer dashboard with invoices and stats"""
    
    if current_user.role != 'customer':
        flash('Access denied. Customer only.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # Get page number for pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    # Get sales for customer with pagination
    try:
        sales_response = supabase.table("sales")\
            .select("*", count="exact")\
            .eq("customer_id", current_user.id)\
            .order("date", desc=True)\
            .range(offset, offset + per_page - 1)\
            .execute()
        
        sales_data = sales_response.data or []
        total_count = sales_response.count or 0
        
        # Get items for each sale
        for sale in sales_data:
            items_response = supabase.table("sale_items")\
                .select("*")\
                .eq("sale_id", sale['id'])\
                .execute()
            sale['items'] = items_response.data or []
            
    except Exception as e:
        print(f"Error fetching sales: {e}")
        sales_data = []
        total_count = 0
    
    # Get customer summary
    summary = get_customer_summary(current_user.id)
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if is_ajax:
        # Render only the invoice cards for AJAX requests
        html = render_template('customer/invoice.html', recent_sales=sales_data)
        return jsonify({
            'success': True,
            'html': html,
            'sales_count': total_count,
            'total_purchases': summary['total_purchases'],
            'total_payments': summary['total_payments'],
            'pending_due': summary['pending_due'],
            'advance_balance': summary['advance_balance'],
            'has_more': len(sales_data) >= per_page and offset + per_page < total_count,
            'total_pages': (total_count + per_page - 1) // per_page
        })
    
    return render_template('customer/dashboard.html',
                         recent_sales=sales_data,
                         total_sales_count=total_count,
                         total_purchases=summary['total_purchases'],
                         total_payments=summary['total_payments'],
                         pending_due=summary['pending_due'],
                         advance_balance=summary['advance_balance'],
                         total_pages=(total_count + per_page - 1) // per_page)


@bp.route('/invoice/<sale_id>')
@login_required
def view_invoice(sale_id):
    """View a specific invoice"""
    
    if current_user.role != 'customer':
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # Get sale with customer ownership check
    try:
        sale_response = supabase.table("sales")\
            .select("*")\
            .eq("id", sale_id)\
            .eq("customer_id", current_user.id)\
            .execute()
        
        if not sale_response.data:
            flash('Invoice not found or access denied.', 'danger')
            return redirect(url_for('customer.dashboard'))
        
        sale = sale_response.data[0]
        
        # Get sale items
        items_response = supabase.table("sale_items")\
            .select("*")\
            .eq("sale_id", sale_id)\
            .execute()
        
        sale['items'] = items_response.data or []
        
    except Exception as e:
        print(f"❌ Error fetching invoice: {e}")
        flash('Error loading invoice.', 'danger')
        return redirect(url_for('customer.dashboard'))
    
    # Calculate advance balance
    advance_balance = sale.get('advance_amount', 0)
    
    return render_template('customer/invoice.html', 
                         sale=sale,
                         business_name="Adarsh Oil Mill",
                         current_user=current_user,
                         advance_balance=advance_balance)


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Customer profile management - update email"""
    
    # Only allow customers
    if current_user.role != 'customer':
        flash('This page is for customers only.', 'warning')
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if action == 'update_email':
            new_email = request.form.get('email', '').strip()
            confirm_email = request.form.get('confirm_email', '').strip()
            
            # Validation
            if not new_email:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Email is required'})
                flash('Email is required', 'danger')
                return redirect(url_for('customer.profile'))
            
            if new_email != confirm_email:
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Emails do not match'})
                flash('Emails do not match', 'danger')
                return redirect(url_for('customer.profile'))
            
            # Validate email format
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, new_email):
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Invalid email format'})
                flash('Invalid email format', 'danger')
                return redirect(url_for('customer.profile'))
            
            # Check if email already exists (for other users)
            try:
                existing_response = supabase.table("users")\
                    .select("id")\
                    .ilike("email", new_email)\
                    .execute()
                
                if existing_response.data:
                    existing_user = existing_response.data[0]
                    if existing_user['id'] != current_user.id:
                        if is_ajax:
                            return jsonify({'success': False, 'error': 'Email already registered'})
                        flash('Email already registered', 'danger')
                        return redirect(url_for('customer.profile'))
            except Exception as e:
                print(f"Error checking email: {e}")
            
            # Update email in database
            try:
                response = supabase.table("users")\
                    .update({"email": new_email})\
                    .eq("id", current_user.id)\
                    .execute()
                
                if response.data:
                    # Update current_user email
                    current_user.email = new_email
                    
                    if is_ajax:
                        return jsonify({
                            'success': True, 
                            'message': 'Email updated successfully!',
                            'email': new_email
                        })
                    
                    flash('Email updated successfully!', 'success')
                    return redirect(url_for('customer.profile'))
                else:
                    if is_ajax:
                        return jsonify({'success': False, 'error': 'Failed to update email'})
                    flash('Failed to update email', 'danger')
                    return redirect(url_for('customer.profile'))
                    
            except Exception as e:
                print(f"Error updating email: {e}")
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Database error. Please try again.'})
                flash('Database error. Please try again.', 'danger')
                return redirect(url_for('customer.profile'))
    
    # GET request - show profile page
    return render_template('customer/customer_profile.html', user=current_user)


@bp.route('/profile/send-verification', methods=['POST'])
@login_required
def send_email_verification():
    """Send verification OTP for email change"""
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Content-Type must be application/json'}), 415
    
    if current_user.role != 'customer':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid JSON data'}), 400
    
    new_email = data.get('email', '').strip()
    
    if not new_email:
        return jsonify({'success': False, 'error': 'Email is required'})
    
    # Validate email format
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, new_email):
        return jsonify({'success': False, 'error': 'Invalid email format'})
    
    # Check if email already exists
    try:
        existing_response = supabase.table("users")\
            .select("id")\
            .ilike("email", new_email)\
            .execute()
        
        if existing_response.data:
            existing_user = existing_response.data[0]
            if existing_user['id'] != current_user.id:
                return jsonify({'success': False, 'error': 'Email already registered'})
    except Exception as e:
        print(f"❌ Error checking email: {e}")
        return jsonify({'success': False, 'error': 'Database error'}), 500
    
    # Check if email is same as current
    if new_email == current_user.email:
        return jsonify({'success': False, 'error': 'This is already your current email'})
    
    # Generate OTP
    otp = str(random.randint(100000, 999999))
    expires_at = (datetime.now() + timedelta(minutes=5)).isoformat()
    
    # Store OTP with metadata
    try:
        # Delete any existing OTPs for this purpose
        supabase.table("otp_requests")\
            .delete()\
            .eq("username", current_user.username)\
            .eq("purpose", "email_verification")\
            .execute()
        
        # Store metadata as JSON string
        metadata_json = json.dumps({"new_email": new_email})
        
        insert_result = supabase.table("otp_requests").insert({
            "username": current_user.username,
            "otp": otp,
            "expires_at": expires_at,
            "attempts": 0,
            "purpose": "email_verification",
            "metadata": metadata_json
        }).execute()
        
        print(f"✅ OTP stored: {insert_result.data}")
        
    except Exception as e:
        print(f"❌ Error storing OTP: {e}")
        return jsonify({'success': False, 'error': f'Failed to generate OTP: {str(e)}'}), 500
    
    # ============================================
    # DECIDE WHERE TO SEND THE OTP
    # ============================================
    # Check if user has an existing email
    has_current_email = current_user.email and current_user.email.strip()
    
    # If user has current email, send OTP to current email (OLD email)
    # If user has NO current email, send OTP to new email
    target_email = current_user.email if has_current_email else new_email
    
    print(f"📧 Sending OTP to: {target_email} (Current email exists: {has_current_email})")
    
    # Send OTP email
    subject = "Email Verification OTP - Adarsh Oil Mill"
    
    if has_current_email:
        # Sending to old/current email
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Email Verification OTP</title>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 16px; }}
                .header {{ text-align: center; padding-bottom: 20px; border-bottom: 2px solid #0C5B3F; }}
                .otp-box {{ background: #f0fdf4; padding: 25px; text-align: center; border-radius: 12px; margin: 25px 0; }}
                .otp-code {{ font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #0C5B3F; }}
                .expiry-note {{ color: #dc2626; font-size: 12px; margin-top: 10px; }}
                .warning {{ background: #fef3c7; padding: 12px; border-radius: 8px; color: #92400e; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="color: #0C5B3F;">Email Change Verification</h2>
                </div>
                <p>Hello <strong>{current_user.username}</strong>,</p>
                <p>You requested to change your email address from:</p>
                <p style="font-weight: 600; color: #0C5B3F;">{current_user.email}</p>
                <p>To:</p>
                <p style="font-weight: 600; color: #0C5B3F;">{new_email}</p>
                <div class="warning">
                    ⚠️ If you didn't request this, please ignore this email.
                </div>
                <div class="otp-box">
                    <div class="otp-code">{otp}</div>
                </div>
                <p>This OTP is valid for <strong>5 minutes</strong>.</p>
                <p class="expiry-note">🔒 Do not share this OTP with anyone.</p>
                <hr>
                <p style="font-size: 12px; color: #888;">Adarsh Oil Mill | Mainapokhar, Bardiya, Nepal</p>
            </div>
        </body>
        </html>
        """
    else:
        # No current email - sending to new email
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Email Verification OTP</title>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 16px; }}
                .header {{ text-align: center; padding-bottom: 20px; border-bottom: 2px solid #0C5B3F; }}
                .otp-box {{ background: #f0fdf4; padding: 25px; text-align: center; border-radius: 12px; margin: 25px 0; }}
                .otp-code {{ font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #0C5B3F; }}
                .expiry-note {{ color: #dc2626; font-size: 12px; margin-top: 10px; }}
                .warning {{ background: #fef3c7; padding: 12px; border-radius: 8px; color: #92400e; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="color: #0C5B3F;">Email Verification</h2>
                </div>
                <p>Hello <strong>{current_user.username}</strong>,</p>
                <p>You are setting up your email address:</p>
                <p style="font-weight: 600; color: #0C5B3F;">{new_email}</p>
                <div class="warning">
                    ⚠️ If you didn't request this, please ignore this email.
                </div>
                <div class="otp-box">
                    <div class="otp-code">{otp}</div>
                </div>
                <p>This OTP is valid for <strong>5 minutes</strong>.</p>
                <p class="expiry-note">🔒 Do not share this OTP with anyone.</p>
                <hr>
                <p style="font-size: 12px; color: #888;">Adarsh Oil Mill | Mainapokhar, Bardiya, Nepal</p>
            </div>
        </body>
        </html>
        """
    
    try:
        from app.brevo_service import send_reset_email
        
        email_sent = send_reset_email(target_email, subject, html_body, email_type='verification')
        
        if email_sent:
            return jsonify({
                'success': True,
                'message': f'Verification OTP sent to {target_email}',
                'sent_to': target_email
            })
        else:
            if not BREVO_API_KEY:
                error_msg = "Email service not configured. Please contact support."
            else:
                error_msg = "Failed to send verification email. Please try again later."
            
            return jsonify({'success': False, 'error': error_msg}), 500
            
    except Exception as e:
        print(f"❌ Exception sending email: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Email error: {str(e)}'}), 500


@bp.route('/profile/verify-email', methods=['POST'])
@login_required
def verify_email_otp():
    """Verify OTP and update email"""
    
    # Check if JSON request
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Content-Type must be application/json'}), 415
    
    if current_user.role != 'customer':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid JSON data'}), 400
    
    otp = data.get('otp', '').strip()
    
    if not otp:
        return jsonify({'success': False, 'error': 'OTP is required'})
    
    new_email = None
    otp_record = None
    
    try:
        # Get the OTP record
        response = supabase.table("otp_requests")\
            .select("*")\
            .eq("username", current_user.username)\
            .eq("purpose", "email_verification")\
            .gte("expires_at", datetime.now().isoformat())\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        
        print(f"🔍 OTP record found: {response.data}")
        
        if not response.data:
            return jsonify({'success': False, 'error': 'OTP expired or not found. Please request a new OTP.'})
        
        otp_record = response.data[0]
        
        # Parse metadata - it's stored as JSON string
        metadata = otp_record.get('metadata')
        print(f"📦 Raw metadata: {metadata} (type: {type(metadata)})")
        
        if metadata:
            # If metadata is a string, try to parse it as JSON
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                    print(f"📦 Parsed metadata: {metadata}")
                except json.JSONDecodeError:
                    print(f"❌ Failed to parse metadata as JSON")
                    return jsonify({'success': False, 'error': 'Invalid metadata format'})
            
            # Now metadata should be a dict
            if isinstance(metadata, dict):
                new_email = metadata.get('new_email')
                print(f"📧 Email from metadata: {new_email}")
        
        if not new_email:
            return jsonify({'success': False, 'error': 'No pending email change found. Please request a new OTP.'})
        
        # Check attempts
        if otp_record.get('attempts', 0) >= 5:
            supabase.table("otp_requests").delete().eq("id", otp_record['id']).execute()
            return jsonify({'success': False, 'error': 'Too many failed attempts. Please request a new OTP.'})
        
        # Verify OTP
        if otp_record.get('otp') != otp:
            # Increment attempts
            supabase.table("otp_requests").update({
                "attempts": otp_record.get('attempts', 0) + 1
            }).eq("id", otp_record['id']).execute()
            remaining = 5 - (otp_record.get('attempts', 0) + 1)
            return jsonify({'success': False, 'error': f'Wrong OTP. {remaining} attempts remaining.'})
        
        # OTP is correct! Delete it
        supabase.table("otp_requests").delete().eq("id", otp_record['id']).execute()
        
    except Exception as e:
        print(f"❌ Error in OTP verification: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'Error verifying OTP. Please try again.'})
    
    # Update the email
    try:
        response = supabase.table("users")\
            .update({"email": new_email})\
            .eq("id", current_user.id)\
            .execute()
        
        if response.data:
            # Update current_user email
            current_user.email = new_email
            
            # Clean up any remaining OTPs
            supabase.table("otp_requests")\
                .delete()\
                .eq("username", current_user.username)\
                .eq("purpose", "email_verification")\
                .execute()
            
            return jsonify({
                'success': True,
                'message': 'Email updated successfully!',
                'email': new_email
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to update email'})
            
    except Exception as e:
        print(f"❌ Error updating email: {e}")
        return jsonify({'success': False, 'error': 'Database error. Please try again.'})



@bp.route('/profile/send-password-otp', methods=['POST'])
@login_required
def send_password_otp():
    """Send OTP for password change to user's email"""
    
    if current_user.role != 'customer':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    # Check if user has email
    if not current_user.email or not current_user.email.strip():
        return jsonify({'success': False, 'error': 'No email registered. OTP not required.'})
    
    # Generate OTP
    otp = str(random.randint(100000, 999999))
    expires_at = datetime.now() + timedelta(minutes=5)
    
    # Store OTP in session
    session['password_change_otp'] = otp
    session['password_change_otp_expiry'] = expires_at.isoformat()
    session['password_otp_verified'] = False
    
    # Send OTP email
    subject = "Password Change OTP - Adarsh Oil Mill"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Password Change OTP</title>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .container {{ max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 16px; }}
            .header {{ text-align: center; padding-bottom: 20px; border-bottom: 2px solid #0C5B3F; }}
            .otp-box {{ background: #f0fdf4; padding: 25px; text-align: center; border-radius: 12px; margin: 25px 0; }}
            .otp-code {{ font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #0C5B3F; }}
            .expiry-note {{ color: #dc2626; font-size: 12px; margin-top: 10px; }}
            .warning {{ background: #fef3c7; padding: 12px; border-radius: 8px; color: #92400e; margin: 15px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2 style="color: #0C5B3F;">Password Change Request</h2>
            </div>
            <p>Hello <strong>{current_user.username}</strong>,</p>
            <p>You requested to change your password.</p>
            <div class="warning">
                ⚠️ If you didn't request this, please ignore this email.
            </div>
            <div class="otp-box">
                <div class="otp-code">{otp}</div>
            </div>
            <p>This OTP is valid for <strong>5 minutes</strong>.</p>
            <p class="expiry-note">🔒 Do not share this OTP with anyone.</p>
            <hr>
            <p style="font-size: 12px; color: #888;">Adarsh Oil Mill | Mainapokhar, Bardiya, Nepal</p>
        </div>
    </body>
    </html>
    """
    
    try:
        from app.brevo_service import send_reset_email
        email_sent = send_reset_email(current_user.email, subject, html_body, email_type='verification')
        
        if email_sent:
            return jsonify({
                'success': True,
                'message': 'OTP sent to your registered email'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to send OTP email'}), 500
            
    except Exception as e:
        print(f"❌ Error sending OTP: {e}")
        return jsonify({'success': False, 'error': 'Error sending OTP'}), 500


@bp.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    """Change password - OTP verified AND password changed in one step"""
    
    if current_user.role != 'customer':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    # Get JSON data
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Content-Type must be application/json'}), 415
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid JSON data'}), 400
    
    old_password = data.get('old_password', '').strip()
    new_password = data.get('new_password', '').strip()
    otp = data.get('otp', '').strip()
    
    # Validate inputs
    if not old_password or not new_password:
        return jsonify({'success': False, 'error': 'All fields are required'})
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'})
    
    # Get user from database
    try:
        user_data = User.get_by_id(current_user.id)
        
        if not user_data:
            return jsonify({'success': False, 'error': 'User not found'})
        
        # Verify old password
        stored_password_hash = user_data.get('password_hash', '')
        
        if not stored_password_hash:
            return jsonify({'success': False, 'error': 'No password set for this account'})
        
        from werkzeug.security import check_password_hash
        if not check_password_hash(stored_password_hash, old_password):
            return jsonify({'success': False, 'error': 'Current password is incorrect'})
        
        # Check if user has email registered
        has_email = current_user.email and current_user.email.strip()
        
        # If email exists, verify OTP
        if has_email:
            # Get pending OTP from session
            pending_otp = session.get('password_change_otp')
            otp_expiry = session.get('password_change_otp_expiry')
            
            # Check if OTP was sent
            if not pending_otp or not otp_expiry:
                return jsonify({'success': False, 'error': 'Please request OTP verification first'})
            
            # Check if OTP expired
            try:
                expiry_time = datetime.fromisoformat(otp_expiry)
                if datetime.now() > expiry_time:
                    session.pop('password_change_otp', None)
                    session.pop('password_change_otp_expiry', None)
                    return jsonify({'success': False, 'error': 'OTP expired. Please request a new one'})
            except Exception as e:
                print(f"Error checking expiry: {e}")
                return jsonify({'success': False, 'error': 'Invalid OTP session'})
            
            # Verify OTP
            if not otp:
                return jsonify({'success': False, 'error': 'OTP is required for verification'})
            
            if otp != pending_otp:
                return jsonify({'success': False, 'error': 'Invalid OTP. Please try again'})
            
            # OTP is correct! Clear it from session
            session.pop('password_change_otp', None)
            session.pop('password_change_otp_expiry', None)
        
        # If no email OR OTP is verified, update password
        from werkzeug.security import generate_password_hash
        new_password_hash = generate_password_hash(new_password)
        
        # Update password in database
        updated_user = User.update_password(current_user.id, new_password_hash)
        
        if updated_user:
            return jsonify({
                'success': True,
                'message': 'Password changed successfully!'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to update password'})
            
    except Exception as e:
        print(f"❌ Error changing password: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500