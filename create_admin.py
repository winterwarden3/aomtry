# create_admin.py
# For Flask with Werkzeug password hashing

import sys
import getpass
from app.supabase_client import supabase
from werkzeug.security import generate_password_hash

def create_admin():
    print("=" * 50)
    print("CREATE ADMIN USER")
    print("=" * 50)
    
    # Get admin details
    username = input("Enter admin username: ").strip()
    name = input("Enter admin full name: ").strip()
    email = input("Enter admin email: ").strip()
    password = getpass.getpass("Enter admin password: ").strip()
    confirm_password = getpass.getpass("Confirm password: ").strip()
    
    # Validate
    if not username or not name or not email or not password:
        print("❌ All fields are required!")
        return False
    
    if password != confirm_password:
        print("❌ Passwords do not match!")
        return False
    
    if len(password) < 6:
        print("❌ Password must be at least 6 characters!")
        return False
    
    # Check if user already exists
    try:
        response = supabase.table("users").select("id").eq("username", username).execute()
        if response.data:
            print(f"❌ Username '{username}' already exists!")
            return False
        
        response = supabase.table("users").select("id").eq("email", email).execute()
        if response.data:
            print(f"❌ Email '{email}' already exists!")
            return False
    except Exception as e:
        print(f"❌ Error checking existing user: {e}")
        return False
    
    # Hash password using Werkzeug
    try:
        password_hash = generate_password_hash(password)
    except Exception as e:
        print(f"❌ Error hashing password: {e}")
        return False
    
    # Create admin user
    try:
        admin_data = {
            'name': name,
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'role': 'admin',
            'is_active': True,
            'advance_balance': 0,
            'created_at': 'NOW()'
        }
        
        response = supabase.table("users").insert(admin_data).execute()
        
        if response.data:
            print("\n" + "=" * 50)
            print("✅ ADMIN USER CREATED SUCCESSFULLY!")
            print("=" * 50)
            print(f"Username: {username}")
            print(f"Name: {name}")
            print(f"Email: {email}")
            print(f"Role: admin")
            print("=" * 50)
            return True
        else:
            print("❌ Failed to create admin user!")
            return False
            
    except Exception as e:
        print(f"❌ Error creating admin: {e}")
        return False

if __name__ == "__main__":
    create_admin()