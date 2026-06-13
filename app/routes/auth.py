from flask import Blueprint, jsonify, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models_supabase import User
from app.login_user import LoginUser
from werkzeug.security import generate_password_hash, check_password_hash
import random
from datetime import datetime, timedelta
from app.brevo_service import send_reset_email
from app.supabase_client import supabase
from app.config import Config

bp = Blueprint('auth', __name__, url_prefix='/auth')


# ============================================
# LOGIN ATTEMPT TRACKING (Database-based)
# ============================================

def get_recent_login_attempts(username, ip_address):
    """Get number of failed login attempts for this username OR IP in last LOCKOUT_MINUTES"""
    try:
        cutoff = (datetime.now() - timedelta(minutes=Config.LOCKOUT_MINUTES)).isoformat()
        
        # Check attempts for this specific username
        response = supabase.table("login_attempts")\
            .select("id", count="exact")\
            .eq("username", username)\
            .eq("success", False)\
            .gte("attempt_time", cutoff)\
            .execute()
        
        username_attempts = response.count or 0
        
        # Also check attempts from this IP address (regardless of username)
        ip_response = supabase.table("login_attempts")\
            .select("id", count="exact")\
            .eq("ip_address", ip_address)\
            .eq("success", False)\
            .gte("attempt_time", cutoff)\
            .execute()
        
        ip_attempts = ip_response.count or 0
        
        # Lock if either username OR IP has too many attempts
        total_attempts = max(username_attempts, ip_attempts)
        
        if total_attempts >= Config.MAX_LOGIN_ATTEMPTS:
            return True, total_attempts
        return False, total_attempts
    except Exception as e:
        print(f"Error checking login attempts: {e}")
        return False, 0


def record_login_attempt(username, ip_address, success):
    """Record a login attempt in database"""
    try:
        supabase.table("login_attempts").insert({
            "username": username,
            "ip_address": ip_address,
            "success": success,
            "attempt_time": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"Error recording login attempt: {e}")


def cleanup_old_login_attempts():
    """Remove login attempts older than 1 hour"""
    try:
        cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
        supabase.table("login_attempts").delete().lt("attempt_time", cutoff).execute()
    except Exception as e:
        print(f"Error cleaning login attempts: {e}")


# ============================================
# OTP FUNCTIONS (Database-based for Vercel)
# ============================================

def get_recent_otp_count(username):
    """Get number of OTP requests in last hour from database"""
    try:
        cutoff = (datetime.now() - timedelta(hours=Config.OTP_WINDOW_HOURS)).isoformat()
        response = supabase.table("otp_requests")\
            .select("id", count="exact")\
            .eq("username", username)\
            .gte("created_at", cutoff)\
            .execute()
        return response.count or 0
    except Exception as e:
        print(f"Count error: {e}")
        return 0


def verify_otp(username, otp, purpose):
    """
    Reusable OTP verification function
    
    Args:
        username: The username to verify OTP for
        otp: The OTP code entered by user
        purpose: Either 'forgot_password' or 'change_password'
    
    Returns:
        tuple: (success, message)
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

@bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('customer.dashboard'))
    return redirect(url_for('auth.login'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    # Clean up old login attempts
    cleanup_old_login_attempts()
    
    user_type = request.args.get('type', 'customer')
    
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('customer.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        login_type = request.form.get('login_type', 'customer')
        
        # Get client IP address
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        # Check login attempts FIRST
        is_locked, attempt_count = get_recent_login_attempts(username, ip_address)
        
        if is_locked:
            flash(f'Too many failed login attempts. Please wait {Config.LOCKOUT_MINUTES} minutes before trying again.', 'danger')
            return render_template('auth/login.html', user_type=user_type)
        
        try:
            user_data = User.find_by_username_or_email(username)
            
            if user_data and user_data.get('is_active', True):
                if check_password_hash(user_data['password_hash'], password):
                    user = LoginUser(user_data)
                    
                    # Role checks
                    if login_type == 'admin' and user.role != 'admin':
                        flash('This account is not an admin account. Please use Customer Login.', 'danger')
                        return redirect(url_for('auth.login', type='admin'))
                    
                    if login_type == 'customer' and user.role == 'admin':
                        flash('This is an admin account. Please use Admin Login.', 'danger')
                        return redirect(url_for('auth.login', type='customer'))
                    
                    # Record SUCCESSFUL attempt
                    record_login_attempt(username, ip_address, True)
                    
                    login_user(user)
                    flash('Login successful', 'success')
                    
                    if user.role == 'admin':
                        return redirect(url_for('admin.dashboard'))
                    return redirect(url_for('customer.dashboard'))
                else:
                    # Record FAILED attempt
                    record_login_attempt(username, ip_address, False)
                    
                    # Get remaining attempts
                    _, new_count = get_recent_login_attempts(username, ip_address)
                    remaining = Config.MAX_LOGIN_ATTEMPTS - new_count
                    
                    if remaining > 0:
                        flash(f'Invalid credentials. {remaining} attempt(s) remaining.', 'danger')
                        return render_template('auth/login.html', user_type=user_type, remaining_attempts=remaining)
                    else:
                        flash(f'Too many failed attempts. Account locked for {Config.LOCKOUT_MINUTES} minutes.', 'danger')
                        return render_template('auth/login.html', user_type=user_type)
            else:
                # User not found - still record attempt to prevent username enumeration
                record_login_attempt(username, ip_address, False)
                flash('Invalid credentials', 'danger')
                return render_template('auth/login.html', user_type=user_type)
                
        except Exception as e:
            print(f"Login error: {e}")
            flash('Login failed. Please try again.', 'danger')
            return render_template('auth/login.html', user_type=user_type)
    
    return render_template('auth/login.html', user_type=user_type)


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/change-password/send-otp', methods=['POST'])
@login_required
def send_change_password_otp():
    """Send OTP to admin's email before allowing password change"""
    
    # Only allow for admin users
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'OTP verification is only for admin accounts'}), 403
    
    data = request.get_json()
    old_password = data.get('old_password')
    
    # Verify old password first
    if not current_user.check_password(old_password):
        return jsonify({'success': False, 'error': 'Current password is incorrect'}), 401
    
    # Rate limit check
    username = current_user.username
    recent_count = get_recent_otp_count(username)
    if recent_count >= Config.MAX_OTP_REQUESTS:
        return jsonify({'success': False, 'error': f'Too many OTP requests. Please wait {Config.OTP_WINDOW_HOURS} hour.'}), 429
    
    # Generate OTP
    otp = str(random.randint(100000, 999999))
    expires_at = (datetime.now() + timedelta(minutes=Config.OTP_EXPIRY_MINUTES)).isoformat()
    
    # Store in database
    try:
        supabase.table("otp_requests").insert({
            "username": username,
            "otp": otp,
            "expires_at": expires_at,
            "attempts": 0,
            "purpose": "change_password"
        }).execute()
    except Exception as e:
        print(f"Error storing OTP: {e}")
        return jsonify({'success': False, 'error': 'Failed to generate OTP'}), 500
    
    # Send email to admin
    admin_email = current_user.email or Config.ADMIN_EMAIL
    subject = "Admin Password Change OTP - Adarsh Oil Mill"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Admin Password Change OTP</title>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .container {{ max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 16px; }}
            .header {{ text-align: center; padding-bottom: 20px; border-bottom: 2px solid #0C5B3F; }}
            .otp-box {{ background: #f0fdf4; padding: 25px; text-align: center; border-radius: 12px; margin: 25px 0; }}
            .otp-code {{ font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #0C5B3F; }}
            .warning {{ color: #dc2626; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2 style="color: #0C5B3F;">Admin Password Change Request</h2>
            </div>
            <p>Hello <strong>{username}</strong>,</p>
            <p>You requested to change your admin password.</p>
            <div class="otp-box">
                <div class="otp-code">{otp}</div>
            </div>
            <p>This OTP is valid for <strong>{Config.OTP_EXPIRY_MINUTES} minutes</strong>.</p>
            <p class="warning">⚠️ Do not share this OTP with anyone.</p>
            <p>If you didn't request this, please contact support immediately.</p>
            <hr>
            <p style="font-size: 12px; color: #888;">Adarsh Oil Mill | Mainapokhar, Bardiya, Nepal</p>
        </div>
    </body>
    </html>
    """
    
    email_sent = send_reset_email(admin_email, subject, html_body)
    if not email_sent:
        return jsonify({'success': False, 'error': 'Failed to send OTP email'}), 500
    
    # Return remaining requests info
    remaining = Config.MAX_OTP_REQUESTS - (recent_count + 1)
    return jsonify({
        'success': True, 
        'message': f'OTP sent to {admin_email}. {remaining} request(s) remaining.',
        'remaining': remaining
    })


@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        otp = request.form.get('otp')  # Only required for admin
        
        # Basic validations
        if new_password != confirm_password:
            flash('New passwords do not match!', 'danger')
            return redirect(url_for('auth.change_password'))
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long!', 'danger')
            return redirect(url_for('auth.change_password'))
        
        if not current_user.check_password(old_password):
            flash('Current password is incorrect!', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # ========== OTP VERIFICATION FOR ADMIN ONLY ==========
        if current_user.role == 'admin':
            if not otp:
                flash('OTP is required to change admin password!', 'danger')
                return redirect(url_for('auth.change_password'))
            
            # Verify OTP
            success, message = verify_otp(current_user.username, otp, "change_password")
            if not success:
                flash(message, 'danger')
                return redirect(url_for('auth.change_password'))
        
        # ========== UPDATE PASSWORD ==========
        new_hash = generate_password_hash(new_password)
        result = User.update_password(current_user.id, new_hash)
        
        if result:
            flash('Password changed successfully!', 'success')
            if current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('customer.dashboard'))
        else:
            flash('Failed to update password. Please try again.', 'danger')
            return redirect(url_for('auth.change_password'))
    
    # GET request - show appropriate form
    if current_user.role == 'admin':
        return render_template('auth/admin_change_password.html')
    else:
        return render_template('auth/customer_change_password.html')


@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    user_type = request.args.get('type', 'customer')
    
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')
        forgot_type = request.form.get('forgot_type', 'customer')
        
        if action == 'send_otp':
            user_data = User.get_by_username(username)
            
            if not user_data:
                flash('User not found', 'danger')
                return redirect(url_for('auth.forgot_password', type=forgot_type))
            
            # Rate limit check using database
            recent_count = get_recent_otp_count(username)
            if recent_count >= Config.MAX_OTP_REQUESTS:
                flash(f'Too many OTP requests. Please wait {Config.OTP_WINDOW_HOURS} hour before trying again.', 'danger')
                return redirect(url_for('auth.forgot_password', type=forgot_type))
            
            user_role = user_data.get('role')
            
            if forgot_type == 'admin' and user_role != 'admin':
                flash('You can only reset ADMIN passwords from this page. Please use Customer Forgot Password.', 'danger')
                return redirect(url_for('auth.forgot_password', type='customer'))
            
            if forgot_type == 'customer' and user_role == 'admin':
                flash('You can only reset CUSTOMER passwords from this page. Please use Admin Forgot Password.', 'danger')
                return redirect(url_for('auth.forgot_password', type='admin'))
            
            otp = str(random.randint(100000, 999999))
            expires_at = (datetime.now() + timedelta(minutes=Config.OTP_EXPIRY_MINUTES)).isoformat()
            
            # Store OTP in database with purpose
            try:
                supabase.table("otp_requests").insert({
                    "username": username,
                    "otp": otp,
                    "expires_at": expires_at,
                    "attempts": 0,
                    "purpose": "forgot_password"
                }).execute()
            except Exception as e:
                print(f"Error storing OTP: {e}")
                flash('Failed to generate OTP. Please try again.', 'danger')
                return redirect(url_for('auth.forgot_password', type=forgot_type))
            
            remaining = Config.MAX_OTP_REQUESTS - (recent_count + 1)
            
            # Send email
            if user_role == 'admin':
                recipient_email = 'admin@adarshoilmill.com.np'
                flash(f'OTP sent to admin email ({remaining} requests remaining)', 'info')
            else:
                recipient_email = user_data.get('email')
                if not recipient_email:
                    flash('No email registered. Please contact admin.', 'danger')
                    return redirect(url_for('auth.forgot_password', type=forgot_type))
                flash(f'OTP sent to your email! ({remaining} requests remaining)', 'success')
            
            if recipient_email:
                subject = "Password Reset OTP - Adarsh Oil Mill"
                html_body = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Password Reset OTP</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; }}
                        .container {{ max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 16px; }}
                        .header {{ text-align: center; padding-bottom: 20px; border-bottom: 2px solid #0C5B3F; }}
                        .otp-box {{ background: #f0fdf4; padding: 25px; text-align: center; border-radius: 12px; margin: 25px 0; }}
                        .otp-code {{ font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #0C5B3F; }}
                        .expiry-note {{ color: #dc2626; font-size: 12px; margin-top: 10px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h2 style="color: #0C5B3F;">Password Reset Request</h2>
                        </div>
                        <p>Hello <strong>{username}</strong>,</p>
                        <p>We received a request to reset your password.</p>
                        <div class="otp-box">
                            <div class="otp-code">{otp}</div>
                        </div>
                        <p>This OTP is valid for <strong>{Config.OTP_EXPIRY_MINUTES} minutes</strong>.</p>
                        <p class="expiry-note">⚠️ Do not share this OTP with anyone.</p>
                        <p>If you didn't request this, please ignore this email.</p>
                        <hr>
                        <p style="font-size: 12px; color: #888;">Adarsh Oil Mill | Mainapokhar, Bardiya, Nepal</p>
                    </div>
                </body>
                </html>
                """
                
                email_sent = send_reset_email(recipient_email, subject, html_body)
                if not email_sent:
                    flash('Failed to send OTP. Please try again.', 'danger')
            
            return render_template('auth/forgot_password.html', username=username, user_type=forgot_type)
        
        elif action == 'reset_password':
            otp = request.form.get('otp')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if new_password != confirm_password:
                flash('Passwords do not match!', 'danger')
                return render_template('auth/forgot_password.html', username=username, user_type=forgot_type)
            
            if len(new_password) < 6:
                flash('Password must be at least 6 characters long!', 'danger')
                return render_template('auth/forgot_password.html', username=username, user_type=forgot_type)
            
            # ========== VERIFY OTP USING REUSABLE FUNCTION ==========
            success, message = verify_otp(username, otp, "forgot_password")
            if not success:
                flash(message, 'danger')
                return redirect(url_for('auth.forgot_password', type=forgot_type))
            
            # Verify user role
            user_data = User.get_by_username(username)
            user_role = user_data.get('role') if user_data else None
            
            if forgot_type == 'admin' and user_role != 'admin':
                flash('Security error: Cannot reset customer password from admin page.', 'danger')
                return redirect(url_for('auth.forgot_password', type='customer'))
            
            if forgot_type == 'customer' and user_role == 'admin':
                flash('Security error: Cannot reset admin password from customer page.', 'danger')
                return redirect(url_for('auth.forgot_password', type='admin'))
            
            # Update password
            new_hash = generate_password_hash(new_password)
            result = User.update_password_by_username(username, new_hash)
            
            if result:
                # Clean up (verify_otp already deleted the OTP, but clean up any others)
                supabase.table("otp_requests").delete().eq("username", username).eq("purpose", "forgot_password").execute()
                flash('Password reset successful! Please login with your new password.', 'success')
                if forgot_type == 'admin':
                    return redirect(url_for('auth.login', type='admin'))
                else:
                    return redirect(url_for('auth.login', type='customer'))
            else:
                flash('Failed to reset password. Please try again.', 'danger')
    
    return render_template('auth/forgot_password.html', username=None, user_type=user_type)