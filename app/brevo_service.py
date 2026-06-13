import os
import requests
from typing import Optional

# Get configuration from environment variables
BREVO_API_KEY = os.getenv('BREVO_API_KEY')
BREVO_SENDER_EMAIL_INVOICE = os.getenv('BREVO_SENDER_EMAIL_INVOICE', 'invoice@adarshoilmill.com.np')
BREVO_SENDER_EMAIL_RESET = os.getenv('BREVO_SENDER_EMAIL_RESET', 'reset@adarshoilmill.com.np')
BREVO_SENDER_NAME = os.getenv('BREVO_SENDER_NAME', 'Adarsh Oil Mill')


def send_reset_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send password reset email - called from auth.py
    Matches your existing function signature exactly
    
    Args:
        to_email: Recipient email (admin or customer)
        subject: Email subject
        html_body: HTML content with OTP
    
    Returns:
        bool: True if sent successfully, False otherwise
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
        
        # Customer emails go to customer - use invoice sender
        if to_email == 'contact@adarshoilmill.com.np' or 'admin' in to_email.lower():
            sender_email = BREVO_SENDER_EMAIL_RESET
            sender_name = f"{BREVO_SENDER_NAME} - Password Reset"
        else:
            sender_email = BREVO_SENDER_EMAIL_INVOICE
            sender_name = f"{BREVO_SENDER_NAME} - Invoice"
        
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
        
        # Send email with timeout (Vercel max is 10-60 seconds)
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 201:
            print(f"✅ Reset email sent to {to_email}")
            return True
        else:
            print(f"❌ Reset email failed: {response.status_code} - {response.text[:200]}")
            return False
            
    except requests.Timeout:
        print(f"❌ Reset email timeout for {to_email}")
        return False
    except Exception as e:
        print(f"❌ Reset email error: {str(e)}")
        return False


def send_invoice_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send invoice email - for future use
    Matches pattern of send_reset_email
    
    Args:
        to_email: Customer email address
        subject: Email subject
        html_body: HTML content of invoice
    
    Returns:
        bool: True if sent successfully
    """
    if not BREVO_API_KEY:
        print("❌ BREVO_API_KEY not configured")
        return False
    
    if not to_email:
        print("❌ No recipient email")
        return False
    
    try:
        url = "https://api.brevo.com/v3/smtp/email"
        
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        }
        
        data = {
            "sender": {
                "name": f"{BREVO_SENDER_NAME} - Invoice",
                "email": BREVO_SENDER_EMAIL_INVOICE
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
            print(f"✅ Invoice email sent to {to_email}")
            return True
        else:
            print(f"❌ Invoice email failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Invoice email error: {str(e)}")
        return False


# For backward compatibility with any other files that might use this
def send_email_via_brevo(to_email: str, subject: str, html_body: str, email_type: str = "invoice", sender_name: str = "Adarsh Oil Mill") -> bool:
    """
    Generic email sender - maintains compatibility
    """
    if email_type == "reset":
        return send_reset_email(to_email, subject, html_body)
    else:
        return send_invoice_email(to_email, subject, html_body)


# Deprecated but kept for compatibility - NO THREADING on Vercel
def send_email_in_background(to_email: str, subject: str, html_body: str, email_type: str = "invoice") -> bool:
    """
    NOTE: This function is now synchronous on Vercel
    Threading is not supported - emails will send immediately
    """
    print("⚠️ send_email_in_background is now synchronous on Vercel")
    return send_email_via_brevo(to_email, subject, html_body, email_type)