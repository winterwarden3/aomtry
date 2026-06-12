# app/login_user.py
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

class LoginUser(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['id']
        self.username = user_data['username']
        self.name = user_data.get('name', '')
        self.email = user_data.get('email', '')
        self.role = user_data.get('role', 'customer')
        self._is_active = user_data.get('is_active', True)
        self.password_hash = user_data.get('password_hash', '')
    
    @property
    def is_active(self):
        return self._is_active
    
    @is_active.setter
    def is_active(self, value):
        self._is_active = value
    
    def get_id(self):
        return str(self.id)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)