from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user
from datetime import datetime, timedelta
import pytz
# import threading - REMOVED - NOT COMPATIBLE WITH VERCEL
from app.models_supabase import Sale, Expense
from app.brevo_service import send_invoice_email as brevo_send_invoice

# Nepal timezone constant
NEPAL_TZ = pytz.timezone('Asia/Kathmandu')

# REMOVED: _invoice_lock = threading.Lock() - Not needed on Vercel


# =========================
# ADMIN ACCESS
# =========================
def admin_required(f):
    """Decorator to restrict access to admin users only"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Access denied. Admin only.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


# =========================
# INVOICE GENERATOR (VERCEL-SAFE - NO THREADING)
# =========================
def generate_invoice_number(offset: int = 0) -> str:
    """Generate unique invoice number - with batch offset support"""
    from datetime import datetime
    from app.supabase_client import supabase
    
    now = datetime.now(NEPAL_TZ)
    prefix = f"INV{now.strftime('%Y%m%d')}"
    
    # Retry up to 3 times if we get a duplicate
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Get the highest invoice number for today
            response = supabase.table("sales")\
                .select("invoice_number")\
                .ilike("invoice_number", f"{prefix}%")\
                .order("invoice_number", desc=True)\
                .limit(1)\
                .execute()
            
            if response.data:
                last_invoice = response.data[0].get('invoice_number', '')
                try:
                    last_number = int(last_invoice[-4:])
                except (ValueError, IndexError):
                    last_number = 0
            else:
                last_number = 0
            
            # Apply offset for batch
            new_number = last_number + 1 + offset
            invoice_number = f"{prefix}{new_number:04d}"
            
            # Verify uniqueness
            check_response = supabase.table("sales")\
                .select("invoice_number")\
                .eq("invoice_number", invoice_number)\
                .execute()
            
            if not check_response.data:
                return invoice_number
            else:
                # Duplicate found, retry with next number
                print(f"⚠️ Duplicate invoice number {invoice_number}, retrying...")
                continue
                
        except Exception as e:
            print(f"Error generating invoice: {e}")
            # Fallback: use timestamp
            import time
            timestamp = int(time.time() * 1000)
            return f"{prefix}{timestamp}"[-12:]
    
    # Final fallback after retries
    import time
    timestamp = int(time.time() * 1000)
    return f"{prefix}{timestamp}"[-12:]


# =========================
# TODAY STATS
# =========================
def get_today_stats() -> dict:
    """Get today's sales, expenses, and profit"""
    today = datetime.now(NEPAL_TZ).date()
    start = datetime(today.year, today.month, today.day, 0, 0, 0)
    end = datetime(today.year, today.month, today.day, 23, 59, 59)
    
    start_str = start.isoformat()
    end_str = end.isoformat()
    
    sales = Sale.get_total_by_date_range(start_str, end_str)
    expenses = Expense.get_total_by_date_range(start_str, end_str)
    
    return {
        "sales": sales,
        "expenses": expenses,
        "profit": sales - expenses,
        "payments": 0
    }


# =========================
# MONTHLY STATS
# =========================
def get_monthly_stats() -> dict:
    """Get current month's sales, expenses, and profit"""
    now_nepal = datetime.now(NEPAL_TZ)
    start = datetime(now_nepal.year, now_nepal.month, 1, 0, 0, 0)
    end = now_nepal
    
    start_str = start.isoformat()
    end_str = end.isoformat()
    
    sales = Sale.get_total_by_date_range(start_str, end_str)
    expenses = Expense.get_total_by_date_range(start_str, end_str)
    
    return {
        "sales": sales,
        "expenses": expenses,
        "profit": sales - expenses
    }


# =========================
# PENDING DUES
# =========================
def get_pending_dues() -> float:
    """Calculate total pending dues from all sales"""
    try:
        from app.supabase_client import supabase
        response = supabase.table("sales")\
            .select("due_amount")\
            .in_("payment_status", ["partial", "credit"])\
            .execute()
        
        total_dues = sum(s.get('due_amount', 0) for s in response.data)
        return total_dues
    except Exception as e:
        print(f"Error getting pending dues: {e}")
        # Fallback: direct query for positive due amounts
        try:
            from app.supabase_client import supabase
            response = supabase.table("sales")\
                .select("due_amount")\
                .gt("due_amount", 0)\
                .execute()
            return sum(s.get('due_amount', 0) for s in response.data)
        except:
            return 0


# =========================
# WEEKLY SALES
# =========================
def get_weekly_sales_data() -> dict:
    """Get sales data for last 7 days for chart display"""
    data = []
    labels = []
    
    for i in range(6, -1, -1):
        date = datetime.now(NEPAL_TZ).date() - timedelta(days=i)
        start = datetime(date.year, date.month, date.day, 0, 0, 0)
        end = datetime(date.year, date.month, date.day, 23, 59, 59)
        
        sales = Sale.get_total_by_date_range(start.isoformat(), end.isoformat())
        data.append(float(sales))
        labels.append(date.strftime("%d %b"))
    
    return {"labels": labels, "data": data}


# =========================
# MONTHLY SALES (12 MONTHS)
# =========================
def get_monthly_sales_data() -> dict:
    """Get sales data for last 12 months for chart display"""
    data = []
    labels = []
    now = datetime.now(NEPAL_TZ)
    
    for i in range(11, -1, -1):
        month = now.month - i
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        
        start = datetime(year, month, 1, 0, 0, 0)
        if month == 12:
            end = datetime(year + 1, 1, 1, 0, 0, 0)
        else:
            end = datetime(year, month + 1, 1, 0, 0, 0)
        
        sales = Sale.get_total_by_date_range(start.isoformat(), end.isoformat())
        data.append(float(sales))
        labels.append(start.strftime("%b %y"))
    
    return {"labels": labels, "data": data}


# =========================
# CUSTOMER SUMMARY
# =========================
def get_customer_summary(customer_id: int) -> dict:
    """Get customer purchase summary in one aggregated query."""
    from app.models_supabase import Sale
    agg = Sale.get_aggregates_by_customer([customer_id])
    stats = agg.get(customer_id, {'total_spending': 0, 'total_due': 0})
    total_purchases = stats['total_spending']
    pending_dues = stats['total_due']
    
    return {
        "total_purchases": total_purchases,
        "total_payments": total_purchases - pending_dues,
        "pending_dues": pending_dues
    }


# =========================
# FORMAT CURRENCY
# =========================
def format_currency(amount: float) -> str:
    """Format amount as Nepali Rupees"""
    return f"Rs.{amount:,.2f}"


# =========================
# PAYMENT CHANNEL DATA
# =========================
def get_payment_channel_data() -> dict:
    """Get payment distribution by channel"""
    from app.supabase_client import supabase
    
    try:
        response = supabase.table("payments")\
            .select("payment_mode, amount")\
            .execute()
        
        channel_totals = {
            "Cash": 0,
            "Khalti": 0,
            "Bank": 0,
            "Others": 0
        }
        
        for payment in response.data:
            mode = payment.get('payment_mode', 'Others')
            if mode not in channel_totals:
                mode = 'Others'
            channel_totals[mode] += payment.get('amount', 0)
        
        # Filter out zero-value channels
        labels = [k for k, v in channel_totals.items() if v > 0]
        data = [v for k, v in channel_totals.items() if v > 0]
        
        if not labels:  # If all zeros, show placeholder
            labels = ["Cash", "Khalti", "Bank", "Others"]
            data = [0, 0, 0, 0]
        
        return {"labels": labels, "data": data}
    except Exception as e:
        print(f"Error getting payment data: {e}")
        return {"labels": ["Cash", "Khalti", "Bank", "Others"], "data": [0, 0, 0, 0]}


# =========================
# CALCULATE PAYMENT STATUS
# =========================
def calculate_payment_status(paid: float, total: float) -> str:
    """Calculate payment status based on paid vs total amount"""
    paid = float(paid or 0)
    total = float(total or 0)
    
    if total == 0:
        return "paid"
    
    if paid <= 0:
        return "credit"
    elif paid < total:
        return "partial"
    elif paid == total:
        return "paid"
    else:  # paid > total
        return "advance"


# =========================
# SEND INVOICE EMAIL
# =========================
def send_invoice_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send email using Brevo API - Vercel safe (no threading)"""
    try:
        result = brevo_send_invoice(to_email, subject, html_body)
        if result:
            print(f"✅ EMAIL SENT TO: {to_email}")
        else:
            print(f"❌ EMAIL FAILED TO: {to_email}")
        return result
    except Exception as e:
        print(f"❌ EMAIL ERROR: {e}")
        return False
    

def get_nepal_time():
    """Return current datetime in Nepal timezone (UTC+5:45)"""
    return datetime.now(NEPAL_TZ)


# =========================
# BYPRODUCT EXCHANGE - FIXED
# =========================

def is_mustard_extraction_product(product_name):
    """
    Check if product is Mustard Oil Extraction OR Aalas Oil Extraction
    FIXED: Now checks BOTH products
    """
    if not product_name:
        return False
    name = product_name.lower().strip()
    return name == 'mustard oil extraction' or name == 'aalas oil extraction'


def is_others_product(product_name):
    """
    Legacy function - kept for backward compatibility
    Only checks for 'Others'
    """
    if not product_name:
        return False
    name = product_name.lower().strip()
    return name == 'others'


def is_others_or_dalbanai_product(product_name):
    """
    Check if product is Others OR Dal Banai (for Rice Bran Exchange)
    FIXED: NEW function - checks both Others AND Dal Banai
    """
    if not product_name:
        return False
    name = product_name.lower().strip()
    return name == 'others' or name == 'dal banai'


def build_byproduct_note(exchange_mustard_cake=False, exchange_rice_bran=False):
    """
    Build sale notes from exchange flags
    FIXED: Now mentions Aalas Oil and Dal Banai
    """
    notes = []
    if exchange_mustard_cake:
        notes.append('Mustard Cake Exchange: Mustard Oil Extraction + Aalas Oil Extraction FREE')
    if exchange_rice_bran:
        notes.append('Rice Bran Exchange: Dal Banai + Others FREE')
    return ' | '.join(notes) if notes else ''


def parse_exchange_from_note(note):
    """
    Parse exchange flags from sale notes
    FIXED: Now properly parses the new note format
    """
    if not note:
        return False, False
    
    note_lower = note.lower()
    exchange_mustard_cake = 'mustard cake exchange' in note_lower
    exchange_rice_bran = 'rice bran exchange' in note_lower
    
    return exchange_mustard_cake, exchange_rice_bran


def apply_byproduct_exchange_to_line_items(items, exchange_mustard_cake=False, exchange_rice_bran=False):
    """
    Apply byproduct exchange rules to line items.
    
    FIXED: Now properly handles:
        - MUSTARD CAKE EXCHANGE (J = YES):
            - Mustard Oil Extraction → FREE (quantity=10, rate=0)
            - Aalas Oil Extraction → FREE (quantity=10, rate=0)
        
        - RICE BRAN EXCHANGE (K = YES):
            - Dal Banai → FREE (quantity=10, rate=0)
            - Others → FREE (quantity=10, rate=0)
            - Rice Bran → NOT affected (remains normal product)
    """
    if not items:
        return items
    
    updated = []
    for item in items:
        row = dict(item)
        product = row.get('product_name', '')
        qty = float(row.get('quantity', 0) or 0)
        rate = float(row.get('rate', 0) or 0)
        unit = row.get('unit', 'Kg')
        
        # MUSTARD CAKE EXCHANGE: Affects Mustard Oil Extraction AND Aalas Oil Extraction
        if exchange_mustard_cake and is_mustard_extraction_product(product):
            qty = 10
            rate = 0
            unit = 'Kg'  # Both products use Kg
        
        # RICE BRAN EXCHANGE: Affects Dal Banai AND Others (NOT Rice Bran)
        if exchange_rice_bran and is_others_or_dalbanai_product(product):
            qty = 10
            rate = 0
            unit = 'Kg'
        
        row['quantity'] = qty
        row['rate'] = rate
        row['unit'] = unit
        row['subtotal'] = round(qty * rate, 2)
        updated.append(row)
    
    return updated


# ============================================
# PAGINATION CLASS (Reusable)
# ============================================

class Pagination:
    """Reusable pagination class for all list views"""
    
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = max(1, -(-total // per_page))  # Ceiling division
    
    def iter_pages(self, left_edge=1, left_current=2, right_current=2, right_edge=1):
        """Generate page numbers for pagination display"""
        return range(1, self.pages + 1)
    
    @property
    def has_prev(self):
        return self.page > 1
    
    @property
    def has_next(self):
        return self.page < self.pages
    
    @property
    def prev_num(self):
        return max(1, self.page - 1)
    
    @property
    def next_num(self):
        return min(self.pages, self.page + 1)
    

# =========================
# TIME FORMATTING FUNCTIONS
# =========================

def format_time_ago(date_val):
    """
    Format UTC datetime to Nepal time relative time string
    Used for recent activities display
    """
    if not date_val:
        return "Unknown"
    try:
        import pytz
        from datetime import datetime
        
        nepal_tz = pytz.timezone('Asia/Kathmandu')
        now = datetime.now(nepal_tz)
        
        # Parse the date value
        if isinstance(date_val, str):
            # Handle different date formats (UTC from Supabase)
            if 'T' in date_val:
                date_val = date_val.replace('T', ' ').replace('Z', '').split('.')[0]
            
            # Parse as naive datetime (assume UTC)
            naive_date = datetime.strptime(date_val[:19], '%Y-%m-%d %H:%M:%S')
            
            # Make it timezone-aware as UTC
            utc_tz = pytz.timezone('UTC')
            date_utc = utc_tz.localize(naive_date)
            
            # Convert to Nepal time
            date = date_utc.astimezone(nepal_tz)
        else:
            # If it's already a datetime object
            date = date_val
            if date.tzinfo is None:
                # Assume UTC if no timezone
                utc_tz = pytz.timezone('UTC')
                date = utc_tz.localize(date)
            # Convert to Nepal time
            date = date.astimezone(nepal_tz)
        
        # Calculate difference
        diff = now - date
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            mins = int(seconds // 60)
            return f"{mins} minute{'s' if mins > 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif seconds < 604800:  # 7 days
            days = int(seconds // 86400)
            return f"{days} day{'s' if days > 1 else ''} ago"
        else:
            # Return formatted date for older entries
            return date.strftime('%b %d, %Y')
            
    except Exception as e:
        print(f"Error formatting time: {e}")
        return str(date_val)[:10] if date_val else "Unknown"


def format_nepal_date(date_string):
    """
    Convert UTC datetime string to Nepal date only (YYYY-MM-DD)
    """
    if not date_string:
        return '-'
    
    try:
        if isinstance(date_string, str):
            if 'T' in date_string:
                date_string = date_string.replace('T', ' ').replace('Z', '').split('.')[0]
            naive_date = datetime.strptime(date_string[:19], '%Y-%m-%d %H:%M:%S')
            utc_tz = pytz.timezone('UTC')
            date_utc = utc_tz.localize(naive_date)
            nepal_tz = pytz.timezone('Asia/Kathmandu')
            nepal_date = date_utc.astimezone(nepal_tz)
            return nepal_date.strftime('%Y-%m-%d')
        else:
            return date_string.strftime('%Y-%m-%d') if date_string else '-'
    except Exception as e:
        print(f"Error formatting date: {e}")
        return str(date_string)[:10] if date_string else '-'