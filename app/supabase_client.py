import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ============================================
# SUPABASE CLIENT INITIALIZATION
# ============================================

# Get environment variables (matching config.py)
supabase_url = os.getenv("SUPABASE_URL")
supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Validate required variables
if not supabase_url:
    raise ValueError("SUPABASE_URL environment variable is required")

if not supabase_anon_key:
    raise ValueError("SUPABASE_ANON_KEY environment variable is required")

# Initialize clients
supabase: Client = create_client(supabase_url, supabase_anon_key)

# Admin client with service role key (for operations that bypass RLS)
if supabase_service_key:
    supabase_admin: Client = create_client(supabase_url, supabase_service_key)
else:
    supabase_admin = None
    print("⚠️ SUPABASE_SERVICE_ROLE_KEY not set - admin operations will use anon key")

# ============================================
# HEALTH CHECK (Optional - for debugging)
# ============================================

def check_supabase_connection():
    """Verify Supabase connection is working"""
    try:
        # Simple query to test connection
        response = supabase.table("users").select("count").limit(1).execute()
        print("✅ Supabase connection successful")
        return True
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        return False

# ============================================
# MIGRATION NOTE (Not automatic on Vercel)
# ============================================

# IMPORTANT: Tables must be created manually in Supabase SQL editor
# Run this SQL in Supabase to create required tables:
#
# CREATE TABLE IF NOT EXISTS users (
#     id SERIAL PRIMARY KEY,
#     username VARCHAR(100) UNIQUE NOT NULL,
#     email VARCHAR(200),
#     password_hash VARCHAR(255) NOT NULL,
#     role VARCHAR(50) DEFAULT 'customer',
#     name VARCHAR(200),
#     phone VARCHAR(50),
#     address TEXT,
#     advance_balance DECIMAL(10,2) DEFAULT 0,
#     is_active BOOLEAN DEFAULT true,
#     created_at TIMESTAMP DEFAULT NOW()
# );
#
# CREATE TABLE IF NOT EXISTS products (
#     id SERIAL PRIMARY KEY,
#     name VARCHAR(200) NOT NULL,
#     description TEXT,
#     price DECIMAL(10,2),
#     category VARCHAR(100),
#     image_url TEXT,
#     stock INT DEFAULT 0,
#     created_at TIMESTAMP DEFAULT NOW()
# );
#
# CREATE TABLE IF NOT EXISTS sales (
#     id SERIAL PRIMARY KEY,
#     invoice_number VARCHAR(50) UNIQUE,
#     customer_id INT REFERENCES users(id),
#     customer_name VARCHAR(200),
#     total_amount DECIMAL(10,2),
#     paid_amount DECIMAL(10,2) DEFAULT 0,
#     advance_used DECIMAL(10,2) DEFAULT 0,
#     due_amount DECIMAL(10,2) DEFAULT 0,
#     advance_amount DECIMAL(10,2) DEFAULT 0,
#     payment_status VARCHAR(50),
#     notes TEXT,
#     created_by INT,
#     date TIMESTAMP DEFAULT NOW()
# );
#
# CREATE TABLE IF NOT EXISTS sale_items (
#     id SERIAL PRIMARY KEY,
#     sale_id INT REFERENCES sales(id),
#     product_id INT REFERENCES products(id),
#     product_name VARCHAR(200),
#     quantity INT,
#     price DECIMAL(10,2),
#     total DECIMAL(10,2)
# );
#
# CREATE TABLE IF NOT EXISTS expenses (
#     id SERIAL PRIMARY KEY,
#     category VARCHAR(100),
#     amount DECIMAL(10,2),
#     description TEXT,
#     date TIMESTAMP DEFAULT NOW()
# );
#
# CREATE TABLE IF NOT EXISTS payments (
#     id SERIAL PRIMARY KEY,
#     sale_id INT REFERENCES sales(id),
#     customer_id INT REFERENCES users(id),
#     amount DECIMAL(10,2),
#     method VARCHAR(50),
#     date TIMESTAMP DEFAULT NOW()
# );
#
# CREATE TABLE IF NOT EXISTS advance_transactions (
#     id SERIAL PRIMARY KEY,
#     customer_id INT REFERENCES users(id),
#     sale_id INT REFERENCES sales(id),
#     amount DECIMAL(10,2),
#     type VARCHAR(50),
#     notes TEXT,
#     date TIMESTAMP DEFAULT NOW()
# );

def init_supabase_table():
    """
    DEPRECATED: Tables must be created manually in Supabase.
    This function now only checks connection and prints migration guide.
    """
    print("=" * 50)
    print("SUPABASE SETUP INSTRUCTIONS")
    print("=" * 50)
    print("Please run the SQL queries above in Supabase SQL editor")
    print("=" * 50)
    
    # Just check connection
    return check_supabase_connection()