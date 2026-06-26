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