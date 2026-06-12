from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models_supabase import User
from app.login_user import LoginUser
from werkzeug.security import generate_password_hash, check_password_hash
import random
from datetime import datetime, timedelta

from app.brevo_service import send_reset_email

bp = Blueprint('auth', __name__, url_prefix='/auth')

# OTP store with expiration
otp_store = {}
otp_request_tracker = {}  # {username: [timestamps]}

# Rate limit constants
MAX_OTP_REQUESTS = 3
OTP_WINDOW_HOURS = 1
OTP_EXPIRY_MINUTES = 5


def cleanup_expired_otps():
    """Remove expired OTPs from memory"""
    now = datetime.now()
    expired_keys = []
    
    for username, data in otp_store.items():
        if data.get('expires_at') and data['expires_at'] < now:
            expired_keys.append(username)
    
    for key in expired_keys:
        del otp_store[key]
        print(f"Cleaned up expired OTP for: {key}")
    
    return len(expired_keys)


def cleanup_old_request_tracker():
    """Remove old rate limiting entries"""
    now = datetime.now()
    cutoff = now - timedelta(hours=OTP_WINDOW_HOURS)
    expired_users = []
    
    for username, timestamps in otp_request_tracker.items():
        # Remove old timestamps
        otp_request_tracker[username] = [ts for ts in timestamps if ts > cutoff]
        # If no timestamps left, remove the user entry
        if not otp_request_tracker[username]:
            expired_users.append(username)
    
    for username in expired_users:
        del otp_request_tracker[username]


def is_rate_limited(username):
    """Check if user has exceeded OTP request limit (3 per hour)"""
    now = datetime.now()
    
    if username not in otp_request_tracker:
        otp_request_tracker[username] = []
    
    # Clean up old requests (older than 1 hour)
    cutoff = now - timedelta(hours=OTP_WINDOW_HOURS)
    otp_request_tracker[username] = [
        ts for ts in otp_request_tracker[username] 
        if ts > cutoff
    ]
    
    # Check if limit exceeded
    if len(otp_request_tracker[username]) >= MAX_OTP_REQUESTS:
        oldest = otp_request_tracker[username][0]
        reset_minutes = int((cutoff - oldest).total_seconds() / 60) + 1
        return True, reset_minutes
    
    return False, 0


def record_otp_request(username):
    """Record an OTP request for rate limiting"""
    if username not in otp_request_tracker:
        otp_request_tracker[username] = []
    otp_request_tracker[username].append(datetime.now())


@bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('customer.dashboard'))
    return redirect(url_for('auth.login'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    # Get the user_type from URL (admin or customer)
    user_type = request.args.get('type', 'customer')
    
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('customer.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        login_type = request.form.get('login_type', 'customer')
        
        try:
            # Get user from Supabase
            user_data = User.find_by_username_or_email(username)
            
            if user_data and user_data.get('is_active', True):
                # Verify password
                if check_password_hash(user_data['password_hash'], password):
                    user = LoginUser(user_data)
                    
                    # Check if trying to login as admin but user is customer
                    if login_type == 'admin' and user.role != 'admin':
                        flash('This account is not an admin account. Please use Customer Login.', 'danger')
                        return redirect(url_for('auth.login', type='admin'))
                    
                    # Check if trying to login as customer but user is admin
                    if login_type == 'customer' and user.role == 'admin':
                        flash('This is an admin account. Please use Admin Login.', 'danger')
                        return redirect(url_for('auth.login', type='customer'))
                    
                    login_user(user)
                    flash('Login successful', 'success')
                    
                    if user.role == 'admin':
                        return redirect(url_for('admin.dashboard'))
                    return redirect(url_for('customer.dashboard'))
                else:
                    flash('Invalid credentials', 'danger')
            else:
                flash('Invalid credentials', 'danger')
                
        except Exception as e:
            print(f"Login error: {e}")
            flash('Login failed. Please try again.', 'danger')
    
    return render_template('auth/login.html', user_type=user_type)


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Check if passwords match
        if new_password != confirm_password:
            flash('New passwords do not match!', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # Check password length
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long!', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # Verify old password
        if not current_user.check_password(old_password):
            flash('Current password is incorrect!', 'danger')
            return redirect(url_for('auth.change_password'))
        
        # Update password in Supabase
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
    
    # Use separate templates based on role
    if current_user.role == 'admin':
        return render_template('auth/admin_change_password.html')
    else:
        return render_template('auth/customer_change_password.html')
    

    
@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    # Clean up expired OTPs on every request
    cleanup_expired_otps()
    cleanup_old_request_tracker()
    
    # Get user type from URL
    user_type = request.args.get('type', 'customer')
    
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')
        forgot_type = request.form.get('forgot_type', 'customer')
        
        if action == 'send_otp':
            # Get user from Supabase
            user_data = User.get_by_username(username)
            
            if not user_data:
                flash('User not found', 'danger')
                return redirect(url_for('auth.forgot_password', type=forgot_type))
            
            # RATE LIMIT CHECK
            is_limited, reset_minutes = is_rate_limited(username)
            if is_limited:
                flash(f'Too many OTP requests. Please wait {reset_minutes} minutes before trying again.', 'danger')
                return redirect(url_for('auth.forgot_password', type=forgot_type))
            
            # Get user role
            user_role = user_data.get('role')
            
            # STRICT CHECK: Admin can only reset admin passwords
            if forgot_type == 'admin' and user_role != 'admin':
                flash('You can only reset ADMIN passwords from this page. Please use Customer Forgot Password.', 'danger')
                return redirect(url_for('auth.forgot_password', type='customer'))
            
            # STRICT CHECK: Customer can only reset customer passwords
            if forgot_type == 'customer' and user_role == 'admin':
                flash('You can only reset CUSTOMER passwords from this page. Please use Admin Forgot Password.', 'danger')
                return redirect(url_for('auth.forgot_password', type='admin'))
            
            otp = str(random.randint(100000, 999999))
            
            # Store OTP with expiration
            otp_store[username] = {
                'otp': otp,
                'expires_at': datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES),
                'attempts': 0
            }
            
            # Record this request for rate limiting
            record_otp_request(username)
            
            # Calculate remaining requests
            remaining = MAX_OTP_REQUESTS - len([ts for ts in otp_request_tracker.get(username, []) if ts > datetime.now() - timedelta(hours=OTP_WINDOW_HOURS)])
            
            # IMPORTANT: Send OTP to different emails based on user type
            if user_role == 'admin':
                # Admin OTP goes to admin email
                recipient_email = 'adarshoilbusiness@gmail.com'
                flash(f'OTP sent to admin email: adarshoilbusiness@gmail.com ({remaining} requests remaining this hour)', 'info')
            else:
                # Customer OTP goes to customer's registered email
                recipient_email = user_data.get('email')
                if not recipient_email:
                    flash('No email registered for this account. Please contact admin.', 'danger')
                    return redirect(url_for('auth.forgot_password', type=forgot_type))
                flash(f'OTP sent to your registered email! ({remaining} requests remaining this hour)', 'success')
            
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
                        <p>This OTP is valid for <strong>{OTP_EXPIRY_MINUTES} minutes</strong>.</p>
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
                    return redirect(url_for('auth.forgot_password', type=forgot_type))
            
            return render_template('auth/forgot_password.html', username=username, user_type=forgot_type)
        
        elif action == 'reset_password':
            # Clean up expired OTPs before checking
            cleanup_expired_otps()
            
            otp = request.form.get('otp')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if new_password != confirm_password:
                flash('Passwords do not match!', 'danger')
                return render_template('auth/forgot_password.html', username=username, user_type=forgot_type)
            
            if len(new_password) < 6:
                flash('Password must be at least 6 characters long!', 'danger')
                return render_template('auth/forgot_password.html', username=username, user_type=forgot_type)
            
            # Check if OTP exists and is not expired
            stored_data = otp_store.get(username)
            if not stored_data:
                flash('OTP expired or not found. Please request a new OTP.', 'danger')
                return redirect(url_for('auth.forgot_password', type=forgot_type))
            
            # Check expiration
            if stored_data.get('expires_at') < datetime.now():
                # Remove expired OTP
                del otp_store[username]
                flash('OTP has expired. Please request a new OTP.', 'danger')
                return redirect(url_for('auth.forgot_password', type=forgot_type))
            
            # Check OTP attempts (max 5 wrong attempts)
            if stored_data.get('attempts', 0) >= 5:
                del otp_store[username]
                flash('Too many failed attempts. Please request a new OTP.', 'danger')
                return redirect(url_for('auth.forgot_password', type=forgot_type))
            
            # Verify OTP
            if stored_data.get('otp') != otp:
                stored_data['attempts'] = stored_data.get('attempts', 0) + 1
                remaining_attempts = 5 - stored_data['attempts']
                flash(f'Wrong OTP. {remaining_attempts} attempts remaining.', 'danger')
                return render_template('auth/forgot_password.html', username=username, user_type=forgot_type)
            
            # Verify user role again before resetting password
            user_data = User.get_by_username(username)
            user_role = user_data.get('role') if user_data else None
            
            # Final security check
            if forgot_type == 'admin' and user_role != 'admin':
                flash('Security error: Cannot reset customer password from admin page.', 'danger')
                return redirect(url_for('auth.forgot_password', type='customer'))
            
            if forgot_type == 'customer' and user_role == 'admin':
                flash('Security error: Cannot reset admin password from customer page.', 'danger')
                return redirect(url_for('auth.forgot_password', type='admin'))
            
            # Update password in Supabase
            new_hash = generate_password_hash(new_password)
            result = User.update_password_by_username(username, new_hash)
            
            if result:
                # Clean up
                otp_store.pop(username, None)
                otp_request_tracker.pop(username, None)
                
                flash('Password reset successful! Please login with your new password.', 'success')
                if forgot_type == 'admin':
                    return redirect(url_for('auth.login', type='admin'))
                else:
                    return redirect(url_for('auth.login', type='customer'))
            else:
                flash('Failed to reset password. Please try again.', 'danger')
    
    return render_template('auth/forgot_password.html', username=None, user_type=user_type)