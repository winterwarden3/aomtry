import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask Security
    SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
    
    # ============================================
    # SUPABASE CONFIGURATION (NO SQLALCHEMY)
    # ============================================
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY')
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    
    # ============================================
    # CLOUDINARY CONFIGURATION
    # ============================================
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')
    
    # ============================================
    # BREVO EMAIL CONFIGURATION
    # ============================================
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
    BREVO_SENDER_EMAIL_INVOICE = os.environ.get('BREVO_SENDER_EMAIL_INVOICE', 'invoice@adarshoilmill.com.np')
    BREVO_SENDER_EMAIL_RESET = os.environ.get('BREVO_SENDER_EMAIL_RESET', 'reset@adarshoilmill.com.np')
    BREVO_SENDER_NAME = os.environ.get('BREVO_SENDER_NAME', 'Adarsh Oil Mill')
    
    # ============================================
    # BUSINESS SETTINGS
    # ============================================
    BUSINESS_NAME = "Adarsh Oil Mill"
    CURRENCY = "Rs."
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@adarshoilmill.com.np')
    
    # ============================================
    # OTP & RATE LIMITING CONSTANTS
    # ============================================
    MAX_OTP_REQUESTS = int(os.environ.get('MAX_OTP_REQUESTS', 3))
    OTP_WINDOW_HOURS = int(os.environ.get('OTP_WINDOW_HOURS', 1))
    OTP_EXPIRY_MINUTES = int(os.environ.get('OTP_EXPIRY_MINUTES', 5))
    
    # Login attempt constants
    MAX_LOGIN_ATTEMPTS = int(os.environ.get('MAX_LOGIN_ATTEMPTS', 5))
    LOCKOUT_MINUTES = int(os.environ.get('LOCKOUT_MINUTES', 15))
    
    # ============================================
    # FLASK SETTINGS
    # ============================================
    # Session settings for production
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # ============================================
    # UPLOAD SETTINGS (Cloudinary handles this)
    # ============================================
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # ============================================
    # DEVELOPMENT vs PRODUCTION
    # ============================================
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        required = [
            'SUPABASE_URL',
            'SUPABASE_ANON_KEY',
            'SUPABASE_SERVICE_ROLE_KEY',
            'CLOUDINARY_CLOUD_NAME',
            'CLOUDINARY_API_KEY',
            'CLOUDINARY_API_SECRET',
            'SECRET_KEY'
        ]
        
        missing = []
        for key in required:
            if not getattr(cls, key, None):
                missing.append(key)
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        return True

# For backward compatibility - but print warning
if hasattr(Config, 'SQLALCHEMY_DATABASE_URI'):
    import warnings
    warnings.warn("SQLALCHEMY_DATABASE_URI is deprecated and will be ignored. Using Supabase instead.")
    delattr(Config, 'SQLALCHEMY_DATABASE_URI')