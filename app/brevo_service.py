import os
import requests
from typing import Optional

# Get configuration from environment variables
BREVO_API_KEY = os.getenv('BREVO_API_KEY')
BREVO_SENDER_EMAIL_INVOICE = os.getenv('BREVO_SENDER_EMAIL_INVOICE', 'invoice@adarshoilmill.com.np')
BREVO_SENDER_EMAIL_RESET = os.getenv('BREVO_SENDER_EMAIL_RESET', 'reset@adarshoilmill.com.np')
BREVO_SENDER_EMAIL_VERIFICATION = os.getenv('BREVO_SENDER_EMAIL_VERIFICATION', 'verify@adarshoilmill.com.np')
BREVO_SENDER_NAME = os.getenv('BREVO_SENDER_NAME', 'Adarsh Oil Mill')


def send_reset_email(to_email: str, subject: str, html_body: str, email_type: str = "reset") -> bool:
    """
    Send email via Brevo - supports reset, verification, and invoice emails
    
    Args:
        to_email: Recipient email
        subject: Email subject
        html_body: HTML content
        email_type: 'reset', 'verification', or 'invoice'
    
    Returns:
        bool: True if sent successfully
    """
    # Validate API key
    if not BREVO_API_KEY:
        print("❌ BREVO_API_KEY not configured")
        return False
    
    # Validate recipient
    if not to_email or '@' not in to_email:
        print(f"❌ Invalid recipient email: {to_email}")
        return False
    
    try:
        # Select sender based on email type
        if email_type == "verification":
            sender_email = BREVO_SENDER_EMAIL_VERIFICATION
            sender_name = f"{BREVO_SENDER_NAME} - Verification"
        elif email_type == "reset":
            sender_email = BREVO_SENDER_EMAIL_RESET
            sender_name = f"{BREVO_SENDER_NAME} - Password Reset"
        else:
            sender_email = BREVO_SENDER_EMAIL_INVOICE
            sender_name = f"{BREVO_SENDER_NAME} - Invoice"
        
        print(f"📧 Sending {email_type} email from {sender_email} to {to_email}")
        
        url = "https://api.brevo.com/v3/smtp/email"
        
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        }
        
        data = {
            "sender": {
                "name": sender_name,
                "email": sender_email
            },
            "to": [
                {
                    "email": to_email,
                    "name": "Customer"
                }
            ],
            "subject": subject,
            "htmlContent": html_body
        }
        
        # Send email with timeout
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 201:
            print(f"✅ Email sent successfully to {to_email} from {sender_email}")
            return True
        else:
            print(f"❌ Email failed: {response.status_code} - {response.text[:200]}")
            return False
            
    except requests.Timeout:
        print(f"❌ Email timeout for {to_email}")
        return False
    except Exception as e:
        print(f"❌ Email error: {str(e)}")
        return False


def send_invoice_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send invoice email - uses INVOICE sender
    """
    return send_reset_email(to_email, subject, html_body, "invoice")


# Backward compatibility
def send_email_via_brevo(to_email: str, subject: str, html_body: str, email_type: str = "invoice", sender_name: str = "Adarsh Oil Mill") -> bool:
    """
    Generic email sender - maintains compatibility
    """
    if email_type == "reset":
        return send_reset_email(to_email, subject, html_body, "reset")
    elif email_type == "verification":
        return send_reset_email(to_email, subject, html_body, "verification")
    else:
        return send_invoice_email(to_email, subject, html_body)


# Deprecated but kept for compatibility
def send_email_in_background(to_email: str, subject: str, html_body: str, email_type: str = "invoice") -> bool:
    """
    NOTE: This function is now synchronous on Vercel
    Threading is not supported - emails will send immediately
    """
    print("⚠️ send_email_in_background is now synchronous on Vercel")
    return send_email_via_brevo(to_email, subject, html_body, email_type)


# ============================================
# NEWSLETTER EMAIL FUNCTIONS
# ============================================

def send_newsletter_welcome_email(email, name=None):
    """
    Send welcome email to new newsletter subscriber
    
    Args:
        email: Subscriber's email address
        name: Subscriber's name (optional)
    
    Returns:
        bool: True if sent successfully
    """
    try:
        from app.config import Config
        
        # Prepare contact name
        contact_name = name or 'Valued Customer'
        
        # Email subject and content
        subject = f"Welcome to {Config.BUSINESS_NAME} Newsletter!"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Welcome to Our Newsletter</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 16px; }}
                .header {{ text-align: center; padding-bottom: 20px; border-bottom: 2px solid #0C5B3F; }}
                .header h2 {{ color: #0C5B3F; margin: 0; }}
                .content {{ padding: 20px 0; }}
                .footer {{ text-align: center; font-size: 12px; color: #888; margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
                .btn {{ display: inline-block; padding: 12px 30px; background: #0C5B3F; color: white; text-decoration: none; border-radius: 8px; }}
                .unsubscribe {{ color: #888; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>📬 Welcome to Our Newsletter!</h2>
                    <p>{Config.BUSINESS_NAME}</p>
                </div>
                
                <div class="content">
                    <p>Dear <strong>{contact_name}</strong>,</p>
                    
                    <p>Thank you for subscribing to our newsletter! We're excited to have you on board.</p>
                    
                    <p>You'll now receive:</p>
                    <ul>
                        <li>📢 Latest updates and announcements</li>
                        <li>🛍️ Special offers and promotions</li>
                        <li>📅 Upcoming events and news</li>
                        <li>🌟 New product launches</li>
                    </ul>
                    
                    <p style="text-align: center; margin: 30px 0;">
                        <a href="#" class="btn">Visit Our Website</a>
                    </p>
                    
                    <p>We promise to keep you updated with valuable content and never spam your inbox.</p>
                    
                    <p>Best regards,<br>
                    <strong>{Config.BUSINESS_NAME} Team</strong></p>
                </div>
                
                <div class="footer">
                    <p>{Config.BUSINESS_NAME}<br>Mainapokhar, Bardiya, Nepal</p>
                    <p class="unsubscribe">
                        <a href="#" style="color: #888;">Unsubscribe</a> anytime.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send using Brevo API
        url = "https://api.brevo.com/v3/smtp/email"
        
        payload = {
            "sender": {
                "name": "Adarsh Oil Mill - Newsletter",
                "email": Config.MAIL_DEFAULT_SENDER
            },
            "to": [
                {
                    "email": email,
                    "name": contact_name
                }
            ],
            "subject": subject,
            "htmlContent": html_content
        }
        
        headers = {
            "accept": "application/json",
            "api-key": Config.BREVO_API_KEY,
            "content-type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 201:
            print(f"✅ Welcome email sent to {email}")
            return True
        else:
            print(f"❌ Failed to send welcome email: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending welcome email: {e}")
        return False


def send_newsletter_campaign(subject, content, recipient_emails, from_name=None):
    """
    Send newsletter campaign to multiple recipients
    
    Args:
        subject: Email subject
        content: HTML email content
        recipient_emails: List of email addresses
        from_name: Sender name (optional - not used, Brevo default is used)
    
    Returns:
        dict: {'success': True/False, 'sent_count': int, 'message': str}
    """
    try:
        from app.config import Config
        
        if not recipient_emails:
            return {'success': False, 'message': 'No recipients found'}
        
        # Limit to 500 recipients per batch (Brevo limit)
        if len(recipient_emails) > 500:
            recipient_emails = recipient_emails[:500]
        
        # Format recipients
        recipients = [{"email": email} for email in recipient_emails]
        
        # Send using Brevo API
        url = "https://api.brevo.com/v3/smtp/email"
        
        payload = {
            "sender": {
                "name": "Adarsh Oil Mill - Newsletter",
                "email": Config.MAIL_DEFAULT_SENDER
            },
            "to": recipients,
            "subject": subject,
            "htmlContent": content
        }
        
        headers = {
            "accept": "application/json",
            "api-key": Config.BREVO_API_KEY,
            "content-type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 201:
            return {
                'success': True,
                'sent_count': len(recipient_emails),
                'message': f'Newsletter sent to {len(recipient_emails)} subscribers'
            }
        else:
            return {
                'success': False,
                'message': f'Failed to send: {response.text}'
            }
            
    except Exception as e:
        print(f"❌ Error sending newsletter: {e}")
        return {'success': False, 'message': str(e)}