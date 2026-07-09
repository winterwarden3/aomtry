from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
from app.brevo_service import send_email_via_brevo
from app.models_supabase import Product
from app.config import Config
load_dotenv()

bp = Blueprint('public', __name__, url_prefix='')

@bp.route('/')
def index():
    """Redirect root to home page"""
    return redirect(url_for('public.home'))

@bp.route('/home')
def home():
    """Homepage - Public landing page with products from database"""
    all_products = Product.get_all()
    featured_products = all_products[:3] if all_products else []
    return render_template('pages/home.html', products=featured_products)

@bp.route('/about')
def about():
    """About Us page"""
    return render_template('pages/about.html')

@bp.route('/products')
def products():
    """Products & Services page - Shows all products from Supabase"""
    all_products = Product.get_all()
    
    # Group products by category
    categories = {}
    for product in all_products:
        cat = product.get('category', 'Other')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(product)
    
    return render_template('pages/products.html', products=all_products, categories=categories)

@bp.route('/privacy-policy')
def privacy_policy():
    """Privacy Policy page"""
    return render_template('pages/privacy_policy.html')

@bp.route('/terms-of-service')
def terms_of_service():
    """Terms of Service page"""
    return render_template('pages/terms_of_service.html')

@bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        message = request.form.get('message', '').strip()
        
        # Check if it's an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # VALIDATION
        if not name or not email or not message:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Please fill all required fields'})
            flash('Please fill all required fields', 'danger')
            return redirect(url_for('public.contact'))
        
        # Email validation
        if '@' not in email or '.' not in email:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Please enter a valid email address'})
            flash('Please enter a valid email address', 'danger')
            return redirect(url_for('public.contact'))
        
        # SAVE TO SUPABASE
        from app.supabase_client import supabase
        
        try:
            supabase.table("contact_messages").insert({
                "Name": name,
                "Email": email,
                "Phone": phone,
                "Message": message,
                "Date": datetime.now().isoformat()
            }).execute()
            print(f"✅ Contact message saved from {email}")
        except Exception as e:
            print(f"❌ Error saving contact message: {e}")
            if is_ajax:
                return jsonify({'success': False, 'error': 'Failed to save message. Please try again.'})
        
        # SEND EMAIL NOTIFICATION
        business_email = os.getenv('BREVO_TO_EMAIL', 'contact@adarshoilmill.com.np')
        subject = f"New Contact Message from {name}"
        html_body = f"""
        <h2>New Contact Form Submission</h2>
        <p><strong>Name:</strong> {name}</p>
        <p><strong>Email:</strong> {email}</p>
        <p><strong>Phone:</strong> {phone if phone else 'Not provided'}</p>
        <p><strong>Message:</strong></p>
        <p>{message}</p>
        <hr>
        <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """
        
        email_sent = send_email_via_brevo(business_email, subject, html_body)
        
        # Prepare success message
        success_msg = 'Thank you! Your message has been sent successfully. We will contact you soon.'
        
        # Return JSON response for AJAX requests (NO REDIRECT)
        if is_ajax:
            return jsonify({
                'success': True, 
                'message': success_msg
            })
        
        # Regular form submission (non-AJAX) - fallback
        flash(success_msg, 'success')
        return redirect(url_for('public.contact'))
    
    # GET request - show contact page
    return render_template('pages/contact.html')

@bp.route('/unsubscribe/<string:email>')
def unsubscribe(email):
    """Unsubscribe page - GET request"""
    try:
        from app.models_supabase import Newsletter
        
        # Get subscriber
        subscriber = Newsletter.get_subscriber_by_email(email)
        
        if subscriber:
            return render_template('unsubscribe.html', 
                                 email=email, 
                                 exists=True,
                                 business_name=Config.BUSINESS_NAME)
        else:
            return render_template('unsubscribe.html', 
                                 email=email, 
                                 exists=False,
                                 business_name=Config.BUSINESS_NAME)
            
    except Exception as e:
        print(f"Error loading unsubscribe: {e}")
        return render_template('unsubscribe.html', 
                             email=email, 
                             exists=False,
                             error=True,
                             business_name=Config.BUSINESS_NAME)


@bp.route('/unsubscribe/confirm/<string:email>', methods=['POST'])
def unsubscribe_confirm(email):
    """Confirm unsubscribe - POST request"""
    try:
        from app.models_supabase import Newsletter
        
        result = Newsletter.unsubscribe(email)
        
        if result:
            return render_template('unsubscribe.html', 
                                 email=email, 
                                 confirmed=True,
                                 success=True,
                                 business_name=Config.BUSINESS_NAME)
        else:
            return render_template('unsubscribe.html', 
                                 email=email, 
                                 confirmed=True,
                                 success=False,
                                 business_name=Config.BUSINESS_NAME)
            
    except Exception as e:
        print(f"Error unsubscribing: {e}")
        return render_template('unsubscribe.html', 
                             email=email, 
                             confirmed=True,
                             success=False,
                             error=str(e),
                             business_name=Config.BUSINESS_NAME)


@bp.route('/unsubscribe/success')
def unsubscribe_success():
    """Unsubscribe success page"""
    return render_template('unsubscribe.html', 
                         confirmed=True,
                         success=True,
                         business_name=Config.BUSINESS_NAME)

@bp.route('/unsubscribe', methods=['GET', 'POST'])
def unsubscribe_generic():
    """Generic unsubscribe page where user enters their email"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if email:
            return redirect(url_for('public.unsubscribe', email=email))
        flash('Please enter your email address', 'warning')
    
    return render_template('unsubscribe_generic.html', business_name=Config.BUSINESS_NAME)