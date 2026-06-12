from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app import db 

class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)

    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(20), default='customer')

    phone = db.Column(db.String(20))
    address = db.Column(db.Text)

    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# =========================
# SALE MODEL
# =========================
class Sale(db.Model):
    __tablename__ = 'sale'
    
    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    invoice_number = db.Column(db.String(50))

    total_amount = db.Column(db.Float)
    paid_amount = db.Column(db.Float)
    due_amount = db.Column(db.Float)
    advance_amount = db.Column(db.Float, default=0)

    payment_status = db.Column(db.String(20))
    date = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    customer = db.relationship('User', foreign_keys=[customer_id], backref='sales')
    items = db.relationship('SaleItem', backref='sale', lazy=True, cascade='all, delete-orphan')


# =========================
# SALE ITEM MODEL
# =========================
class SaleItem(db.Model):
    __tablename__ = 'sale_item'
    
    id = db.Column(db.Integer, primary_key=True)

    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'))

    product_name = db.Column(db.String(100))
    quantity = db.Column(db.Float)
    unit = db.Column(db.String(20))
    rate = db.Column(db.Float)
    subtotal = db.Column(db.Float)


# =========================
# PAYMENT MODEL
# =========================
class Payment(db.Model):
    __tablename__ = 'payment'

    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    received_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'))

    amount = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(50))

    date = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# EXPENSE MODEL
# =========================
class Expense(db.Model):
    __tablename__ = 'expense'

    id = db.Column(db.Integer, primary_key=True)

    category = db.Column(db.String(100))
    description = db.Column(db.Text)
    amount = db.Column(db.Float)
    payment_mode = db.Column(db.String(50))

    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    date = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# PRODUCT MODEL
# =========================
class Product(db.Model):
    __tablename__ = 'product'

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))
    category = db.Column(db.String(50))
    unit = db.Column(db.String(20))
    rate = db.Column(db.Float)

    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)