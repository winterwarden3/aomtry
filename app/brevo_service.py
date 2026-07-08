import os
import requests
from typing import Optional

# Get configuration from environment variables
BREVO_API_KEY = os.getenv('BREVO_API_KEY')
BREVO_SENDER_EMAIL_INVOICE = os.getenv('BREVO_SENDER_EMAIL_INVOICE', 'invoice@adarshoilmill.com.np')
BREVO_SENDER_EMAIL_RESET = os.getenv('BREVO_SENDER_EMAIL_RESET', 'reset@adarshoilmill.com.np')
BREVO_SENDER_EMAIL_VERIFICATION = os.getenv('BREVO_SENDER_EMAIL_VERIFICATION', 'verify@adarshoilmill.com.np')
BREVO_SENDER_NAME = os.getenv('BREVO_SENDER_NAME', 'Adarsh Oil Mill')


def get_base_url():
    """Get base URL from environment"""
    return os.getenv('BASE_URL')


def send_reset_email(to_email: str, subject: str, html_body: str, email_type: str = "reset") -> bool:
    """
    Send email via Brevo - supports reset, verification, and invoice emails
    """
    if not BREVO_API_KEY:
        print("❌ BREVO_API_KEY not configured")
        return False
    
    if not to_email or '@' not in to_email:
        print(f"❌ Invalid recipient email: {to_email}")
        return False
    
    try:
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
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 201:
            print(f"✅ Email sent successfully to {to_email}")
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
    """Send invoice email"""
    return send_reset_email(to_email, subject, html_body, "invoice")


def send_email_via_brevo(to_email: str, subject: str, html_body: str, email_type: str = "invoice", sender_name: str = "Adarsh Oil Mill") -> bool:
    """Generic email sender"""
    if email_type == "reset":
        return send_reset_email(to_email, subject, html_body, "reset")
    elif email_type == "verification":
        return send_reset_email(to_email, subject, html_body, "verification")
    else:
        return send_invoice_email(to_email, subject, html_body)


def send_email_in_background(to_email: str, subject: str, html_body: str, email_type: str = "invoice") -> bool:
    """Deprecated - synchronous on Vercel"""
    print("⚠️ send_email_in_background is now synchronous on Vercel")
    return send_email_via_brevo(to_email, subject, html_body, email_type)


# ============================================
# NEWSLETTER EMAIL FUNCTIONS
# ============================================

def send_newsletter_welcome_email(email, name=None):
    """Send welcome email to new newsletter subscriber with unsubscribe link"""
    try:
        from app.config import Config
        
        base_url = get_base_url()
        unsubscribe_url = f"{base_url}/unsubscribe/{email}"
        print(f"🔗 Unsubscribe URL: {unsubscribe_url}")
        
        contact_name = name or 'Valued Customer'
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
                        <li>Latest updates and announcements</li>
                        <li>Special offers and promotions</li>
                        <li>Upcoming events and news</li>
                        <li>New product launches</li>
                    </ul>
                    
                    <p style="text-align: center; margin: 30px 0;">
                        <a href="{base_url}" class="btn">Visit Our Website</a>
                    </p>
                    
                    <p>We promise to keep you updated with valuable content and never spam your inbox.</p>
                    
                    <p>Best regards,<br>
                    <strong>{Config.BUSINESS_NAME} Team</strong></p>
                </div>
                
                <div class="footer">
                    <p>{Config.BUSINESS_NAME}<br>Mainapokhar, Bardiya, Nepal</p>
                    <p>
                        <a href="{unsubscribe_url}" style="color: #888; text-decoration: underline;">
                            Unsubscribe
                        </a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
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


# ============================================
# 🔑 FIXED: Personalized Unsubscribe + BCC (Privacy Protected)
# ============================================

def send_newsletter_campaign(subject, content, recipient_emails, from_name=None):
    """
    Send newsletter campaign with:
    ✅ Personalized unsubscribe link for each recipient
    ✅ BCC - all recipients hidden from each other (privacy protected)
    ✅ List-Unsubscribe header for one-click unsubscribe
    
    Args:
        subject: Email subject
        content: HTML email content (use {{ unsubscribe_url }} placeholder)
        recipient_emails: List of email addresses
        from_name: Sender name (optional)
    
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
        
        url = "https://api.brevo.com/v3/smtp/email"
        base_url = get_base_url()
        
        sent_count = 0
        
        # 🔑 Send each email individually with BCC for privacy
        for email in recipient_emails:
            try:
                # 🔑 Generate personalized unsubscribe URL for this recipient
                unsubscribe_url = f"{base_url}/unsubscribe/{email}"
                
                # 🔑 Replace placeholder with personalized URL
                if '{{ unsubscribe_url }}' in content:
                    personalized_content = content.replace('{{ unsubscribe_url }}', unsubscribe_url)
                else:
                    # If no placeholder, append unsubscribe link to bottom
                    unsubscribe_html = f"""
                    <div style="text-align: center; padding: 20px 0; margin-top: 30px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #888;">
                        <p>You received this email because you subscribed to our newsletter.</p>
                        <p>
                            <a href="{unsubscribe_url}" style="color: #0C5B3F; text-decoration: underline;">
                                Unsubscribe
                            </a>
                        </p>
                    </div>
                    """
                    personalized_content = content + unsubscribe_html
                
                # Replace email placeholder if exists
                personalized_content = personalized_content.replace('{{ email }}', email)
                
                # 🔑 CRITICAL: Use BCC to hide recipient
                # Send to a dummy address (yourself) and BCC the actual recipient
                payload = {
                    "sender": {
                        "name": "Adarsh Oil Mill - Newsletter",
                        "email": Config.MAIL_DEFAULT_SENDER
                    },

                    "bcc": [
                        {
                            "email": email,
                            "name": "Customer"
                        }
                    ],
                    "subject": subject,
                    "htmlContent": personalized_content,
                    "headers": {
                        "List-Unsubscribe": f"<{unsubscribe_url}>",
                        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"
                    }
                }
                
                headers = {
                    "accept": "application/json",
                    "api-key": Config.BREVO_API_KEY,
                    "content-type": "application/json"
                }
                
                response = requests.post(url, json=payload, headers=headers)
                
                if response.status_code == 201:
                    sent_count += 1
                    print(f"✅ Sent to {email} (BCC - hidden)")
                else:
                    print(f"❌ Failed to send to {email}: {response.text}")
                    
            except Exception as e:
                print(f"❌ Error sending to {email}: {e}")
                continue
        
        return {
            'success': True,
            'sent_count': sent_count,
            'message': f'Newsletter sent to {sent_count} of {len(recipient_emails)} subscribers (BCC - all hidden)'
        }
            
    except Exception as e:
        print(f"❌ Error sending newsletter: {e}")
        return {'success': False, 'message': str(e)}