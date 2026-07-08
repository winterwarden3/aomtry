from app.supabase_client import supabase
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import pytz
# ============================================
# USER MODEL (COMPLETE WITH ADVANCE BALANCE)
# ============================================
class User:
    table_name = "users"
    
    @staticmethod
    def get_by_username(username):
        try:
            response = supabase.table(User.table_name).select("*").eq("username", username).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting user: {e}")
            return None
    
    @staticmethod
    def get_by_id(user_id):
        try:
            response = supabase.table(User.table_name).select("*").eq("id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting user: {e}")
            return None
    
    @staticmethod
    def get_all_customers():
        try:
            response = supabase.table(User.table_name).select("*").eq("role", "customer").order("created_at", desc=True).execute()
            return response.data
        except Exception as e:
            print(f"Error getting customers: {e}")
            return []
    
    @staticmethod
    def get_customers_paginated(page=1, per_page=10, search=""):
        try:
            offset = (page - 1) * per_page
            query = supabase.table(User.table_name).select("*", count="exact").eq("role", "customer")
            if search:
                query = query.ilike("name", f"%{search}%")
            response = query.range(offset, offset + per_page - 1).order("created_at", desc=True).execute()
            return response.data, response.count
        except Exception as e:
            print(f"Error getting customers: {e}")
            return [], 0
    
    @staticmethod
    def get_total_spending(customer_id):
        agg = Sale.get_aggregates_by_customer([customer_id])
        return agg.get(customer_id, {}).get('total_spending', 0)

    @staticmethod
    def get_total_due(customer_id):
        agg = Sale.get_aggregates_by_customer([customer_id])
        return agg.get(customer_id, {}).get('total_due', 0)

    @staticmethod
    def get_customer_list_stats():
        """Single query: advance totals and active/inactive counts for all customers."""
        try:
            response = supabase.table(User.table_name)\
                .select("advance_balance, is_active")\
                .eq("role", "customer")\
                .execute()
            total_advance_balance = 0.0
            total_customers_with_advance = 0
            active_customers_count = 0
            inactive_customers_count = 0
            for row in response.data:
                balance = float(row.get('advance_balance', 0) or 0)
                total_advance_balance += balance
                if balance > 0:
                    total_customers_with_advance += 1
                if row.get('is_active', True):
                    active_customers_count += 1
                else:
                    inactive_customers_count += 1
            return {
                'total_advance_balance': total_advance_balance,
                'total_customers_with_advance': total_customers_with_advance,
                'active_customers_count': active_customers_count,
                'inactive_customers_count': inactive_customers_count,
            }
        except Exception as e:
            print(f"Error getting customer list stats: {e}")
            return {
                'total_advance_balance': 0,
                'total_customers_with_advance': 0,
                'active_customers_count': 0,
                'inactive_customers_count': 0,
            }

    @staticmethod
    def enrich_customers_with_sales_stats(customers):
        """Attach total_spending and total_due in one bulk sales query."""
        if not customers:
            return customers
        customer_ids = [c['id'] for c in customers]
        aggregates = Sale.get_aggregates_by_customer(customer_ids)
        for customer in customers:
            stats = aggregates.get(customer['id'], {'total_spending': 0, 'total_due': 0})
            customer['total_spending'] = stats['total_spending']
            customer['total_due'] = stats['total_due']
            customer['advance_balance'] = float(customer.get('advance_balance', 0) or 0)
        return customers

    @staticmethod
    def get_customers_for_dues():
        """All customers with fields needed for dues page — one query."""
        try:
            response = supabase.table(User.table_name)\
                .select("id, name, email, phone, advance_balance")\
                .eq("role", "customer")\
                .execute()
            return response.data
        except Exception as e:
            print(f"Error getting customers for dues: {e}")
            return []
    
    @staticmethod
    def create(data):
        try:
            if 'password_hash' not in data:
                data['password_hash'] = generate_password_hash('1234')
            if 'advance_balance' not in data:
                data['advance_balance'] = 0
            if 'is_active' not in data:      # ← ADD THIS
              data['is_active'] = True
            response = supabase.table(User.table_name).insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    @staticmethod
    def update(user_id, data):
        try:
            response = supabase.table(User.table_name).update(data).eq("id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating user: {e}")
            return None
    
    @staticmethod
    def update_password_by_username(username, password_hash):
        try:
            response = supabase.table(User.table_name).update({"password_hash": password_hash}).eq("username", username).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating password: {e}")
            return None
    
    @staticmethod
    def count_customers():
        try:
            response = supabase.table(User.table_name).select("*", count="exact").eq("role", "customer").execute()
            return response.count
        except Exception as e:
            print(f"Error counting customers: {e}")
            return 0
    
    @staticmethod
    def count_new_customers_since(date):
        try:
            response = supabase.table(User.table_name).select("*", count="exact").eq("role", "customer").gte("created_at", date.isoformat()).execute()
            return response.count
        except Exception as e:
            print(f"Error counting new customers: {e}")
            return 0
    
    @staticmethod
    def search(query):
        try:
            response = supabase.table(User.table_name).select("*").eq("role", "customer").ilike("name", f"%{query}%").limit(10).execute()
            return response.data
        except Exception as e:
            print(f"Error searching customers: {e}")
            return []

    @staticmethod
    def update_password(user_id, password_hash):
        try:
            response = supabase.table(User.table_name).update({"password_hash": password_hash}).eq("id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating password: {e}")
            return None
    
    @staticmethod
    def delete(user_id):
        """Delete a user from the database"""
        try:
            supabase.table(User.table_name).delete().eq("id", user_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting user: {e}")
            return False
    
    @staticmethod
    def find_by_username_or_email(identifier, retry=True):
        """Find user by username or email with retry on first failure"""
        try:
            identifier = identifier.strip()
            
            # First try exact match on username
            response = supabase.table(User.table_name).select("*").eq("username", identifier).execute()
            if response.data:
                user = response.data[0]
                # Validate password_hash exists
                if user.get('password_hash'):
                    return user
                elif retry:
                    print(f"⚠️ password_hash missing for {identifier}, retrying...")
                    return User.find_by_username_or_email(identifier, retry=False)
                return user
            
            # Try case-insensitive match on name
            response = supabase.table(User.table_name).select("*").ilike("name", identifier).execute()
            if response.data:
                user = response.data[0]
                if user.get('password_hash'):
                    return user
                elif retry:
                    print(f"⚠️ password_hash missing for {identifier}, retrying...")
                    return User.find_by_username_or_email(identifier, retry=False)
                return user
            
            # Try email if it contains @
            if '@' in identifier:
                response = supabase.table(User.table_name).select("*").eq("email", identifier).execute()
                if response.data:
                    user = response.data[0]
                    if user.get('password_hash'):
                        return user
                    elif retry:
                        print(f"⚠️ password_hash missing for {identifier}, retrying...")
                        return User.find_by_username_or_email(identifier, retry=False)
                    return user
            
            return None
        except Exception as e:
            print(f"Error finding user: {e}")
            if retry:
                print(f"Retrying after error...")
                return User.find_by_username_or_email(identifier, retry=False)
            return None

    # ============================================
    # ADVANCE BALANCE METHODS - CONSISTENT
    # ============================================
    
    @staticmethod
    def get_advance_balance(customer_id):
        """Get customer's current advance balance (credit/wallet)"""
        try:
            response = supabase.table("users").select("advance_balance").eq("id", customer_id).execute()
            if response.data:
                return float(response.data[0].get('advance_balance', 0))
            return 0
        except Exception as e:
            print(f"Error getting advance balance: {e}")
            return 0

    @staticmethod
    def update_advance_balance(customer_id, amount, operation="add"):
        """
        Update customer's advance balance
        operation: 'add' (increase balance) or 'deduct' (decrease balance)
        """
        try:
            current = User.get_advance_balance(customer_id)
            
            if operation == "add":
                new_balance = current + amount
            elif operation == "deduct":
                new_balance = current - amount
            else:
                print(f"Invalid operation: {operation}")
                return None
            
            # Ensure balance doesn't go negative
            if new_balance < 0:
                new_balance = 0
            
            response = supabase.table("users").update({"advance_balance": new_balance}).eq("id", customer_id).execute()
            
            if response.data:
                print(f"✅ Advance balance: customer={customer_id}, {operation}={amount}, new_balance={new_balance}")
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error updating advance balance: {e}")
            return None

    @staticmethod
    def add_advance_deposit(customer_id, amount, notes=""):
        """Manually add advance balance to customer (deposit/refund)"""
        try:
            result = User.update_advance_balance(customer_id, amount, "add")
            
            if result:
                transaction_data = {
                    'customer_id': customer_id,
                    'amount': amount,
                    'type': 'deposit',
                    'notes': notes,
                    'date': datetime.now().isoformat()
                }
                supabase.table("advance_transactions").insert(transaction_data).execute()
                return result
            return None
        except Exception as e:
            print(f"Error adding advance deposit: {e}")
            return None

    @staticmethod
    def deduct_advance_balance(customer_id, amount, notes=""):
        """Manually deduct advance balance from customer (withdrawal)"""
        try:
            current = User.get_advance_balance(customer_id)
            
            if amount > current:
                print(f"Insufficient balance: {current} available, {amount} requested")
                return None
            
            result = User.update_advance_balance(customer_id, amount, "deduct")
            
            if result:
                transaction_data = {
                    'customer_id': customer_id,
                    'amount': amount,
                    'type': 'withdraw',
                    'notes': notes,
                    'date': datetime.now().isoformat()
                }
                supabase.table("advance_transactions").insert(transaction_data).execute()
                return result
            return None
        except Exception as e:
            print(f"Error deducting advance: {e}")
            return None

    @staticmethod
    def get_advance_transactions(customer_id, limit=50):
        """Get advance transaction history for a customer"""
        try:
            response = supabase.table("advance_transactions")\
                .select("*")\
                .eq("customer_id", customer_id)\
                .order("date", desc=True)\
                .limit(limit)\
                .execute()
            return response.data
        except Exception as e:
            print(f"Error getting advance transactions: {e}")
            return []
    
    @staticmethod
    def get_customer_advance_summary(customer_id):
        """Get complete advance summary for a customer"""
        try:
            current_balance = User.get_advance_balance(customer_id)
            
            deposit_response = supabase.table("advance_transactions")\
                .select("amount")\
                .eq("customer_id", customer_id)\
                .eq("type", "deposit")\
                .execute()
            total_deposited = sum(t.get('amount', 0) for t in deposit_response.data)
            
            redeem_response = supabase.table("advance_transactions")\
                .select("amount")\
                .eq("customer_id", customer_id)\
                .eq("type", "redeem")\
                .execute()
            total_redeemed = sum(t.get('amount', 0) for t in redeem_response.data)
            
            withdraw_response = supabase.table("advance_transactions")\
                .select("amount")\
                .eq("customer_id", customer_id)\
                .eq("type", "withdraw")\
                .execute()
            total_withdrawn = sum(t.get('amount', 0) for t in withdraw_response.data)
            
            return {
                'current_balance': current_balance,
                'total_deposited': total_deposited,
                'total_redeemed': total_redeemed,
                'total_withdrawn': total_withdrawn
            }
        except Exception as e:
            print(f"Error getting advance summary: {e}")
            return {
                'current_balance': 0,
                'total_deposited': 0,
                'total_redeemed': 0,
                'total_withdrawn': 0
            }
    
    @staticmethod
    def get_all_advance_balance_total():
        """Get total advance balance across all customers"""
        try:
            response = supabase.table("users").select("advance_balance").eq("role", "customer").execute()
            total = sum(float(u.get('advance_balance', 0)) for u in response.data)
            return total
        except Exception as e:
            print(f"Error getting total advance balance: {e}")
            return 0


# ============================================
# PRODUCT MODEL
# ============================================
class Product:
    table_name = "products"
    
    @staticmethod
    def get_all():
        try:
            response = supabase.table(Product.table_name).select("*").order("id").execute()
            return response.data
        except Exception as e:
            print(f"Error getting products: {e}")
            return []
    
    @staticmethod
    def get_by_id(product_id):
        try:
            response = supabase.table(Product.table_name).select("*").eq("id", product_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting product: {e}")
            return None
    
    @staticmethod
    def create(data):
        try:
            response = supabase.table(Product.table_name).insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating product: {e}")
            return None
    
    @staticmethod
    def update(product_id, data):
        try:
            response = supabase.table(Product.table_name).update(data).eq("id", product_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating product: {e}")
            return None
    
    @staticmethod
    def delete(product_id):
        try:
            supabase.table(Product.table_name).delete().eq("id", product_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting product: {e}")
            return False


# ============================================
# SALE MODEL (UPDATED WITH ADVANCE SUPPORT)
# ============================================
class Sale:
    table_name = "sales"

    @staticmethod
    def _batch_attach_items(sales):
        """Attach sale_items to sales in a single query."""
        if not sales:
            return sales
        sale_ids = [s['id'] for s in sales]
        try:
            items_response = supabase.table("sale_items").select("*").in_("sale_id", sale_ids).execute()
            items_by_sale = {}
            for item in items_response.data:
                sid = item['sale_id']
                items_by_sale.setdefault(sid, []).append(item)
            for sale in sales:
                sale['items'] = items_by_sale.get(sale['id'], [])
        except Exception as e:
            print(f"Error batch-fetching sale items: {e}")
            for sale in sales:
                sale['items'] = []
        return sales

    @staticmethod
    def get_aggregates_by_customer(customer_ids=None):
        """Sum total_amount and due_amount per customer in one query."""
        try:
            query = supabase.table(Sale.table_name)\
                .select("customer_id, total_amount, due_amount")\
                .not_.is_("customer_id", "null")
            if customer_ids:
                query = query.in_("customer_id", customer_ids)
            response = query.execute()
            aggregates = {}
            for row in response.data:
                cid = row.get('customer_id')
                if cid is None:
                    continue
                if cid not in aggregates:
                    aggregates[cid] = {'total_spending': 0.0, 'total_due': 0.0}
                aggregates[cid]['total_spending'] += float(row.get('total_amount', 0) or 0)
                aggregates[cid]['total_due'] += float(row.get('due_amount', 0) or 0)
            return aggregates
        except Exception as e:
            print(f"Error getting sales aggregates: {e}")
            return {}

    @staticmethod
    def get_sales_totals_for_dues():
        """All per-customer sale totals for dues page — one query."""
        try:
            response = supabase.table(Sale.table_name)\
                .select("customer_id, total_amount, paid_amount, advance_used, due_amount")\
                .not_.is_("customer_id", "null")\
                .execute()
            return response.data
        except Exception as e:
            print(f"Error getting sales for dues: {e}")
            return []

    @staticmethod
    def get_unpaid_by_customer(customer_id):
        """Unpaid sales for one customer — single filtered query."""
        try:
            response = supabase.table(Sale.table_name)\
                .select("*")\
                .eq("customer_id", customer_id)\
                .gt("due_amount", 0)\
                .order("date")\
                .execute()
            return response.data or []
        except Exception as e:
            print(f"Error getting unpaid sales: {e}")
            return []

    @staticmethod
    def get_by_customer(customer_id, page=1, per_page=50, with_items=True):
        """Sales for one customer with optional items (2 queries max, not N+1)."""
        try:
            offset = (page - 1) * per_page
            select_cols = '*, sale_items(*)' if with_items else '*'
            try:
                response = supabase.table(Sale.table_name)\
                    .select(select_cols, count="exact")\
                    .eq("customer_id", customer_id)\
                    .order("date", desc=True)\
                    .range(offset, offset + per_page - 1)\
                    .execute()
                sales = response.data or []
                if with_items:
                    for sale in sales:
                        sale['items'] = sale.pop('sale_items', None) or []
                return sales, response.count
            except Exception:
                response = supabase.table(Sale.table_name)\
                    .select("*", count="exact")\
                    .eq("customer_id", customer_id)\
                    .order("date", desc=True)\
                    .range(offset, offset + per_page - 1)\
                    .execute()
                sales = response.data or []
                if with_items:
                    Sale._batch_attach_items(sales)
                return sales, response.count
        except Exception as e:
            print(f"Error getting customer sales: {e}")
            return [], 0

    @staticmethod
    def get_by_id_with_items(sale_id):
        """Single sale with items (1–2 queries)."""
        try:
            try:
                response = supabase.table(Sale.table_name)\
                    .select('*, sale_items(*)')\
                    .eq("id", sale_id)\
                    .execute()
                if response.data:
                    sale = response.data[0]
                    sale['items'] = sale.pop('sale_items', None) or []
                    return sale
            except Exception:
                pass
            sale = Sale.get_by_id(sale_id)
            if sale:
                sale['items'] = Sale.get_items(sale_id)
            return sale
        except Exception as e:
            print(f"Error getting sale with items: {e}")
            return None

    @staticmethod
    def get_items_by_date_range(start_datetime, end_datetime):
        """Sale line items for sales in a date range — 2 queries total."""
        try:
            sales_response = supabase.table(Sale.table_name)\
                .select("id, customer_id, total_amount, date")\
                .gte("date", start_datetime)\
                .lte("date", end_datetime)\
                .execute()
            sales = sales_response.data or []
            if not sales:
                return [], []
            sale_ids = [s['id'] for s in sales]
            items_response = supabase.table("sale_items")\
                .select("sale_id, product_name, subtotal")\
                .in_("sale_id", sale_ids)\
                .execute()
            return sales, items_response.data or []
        except Exception as e:
            print(f"Error getting items by date range: {e}")
            return [], []

    @staticmethod
    def count_all_payment_statuses():
        """Count sales by payment_status in one query."""
        try:
            response = supabase.table(Sale.table_name).select("payment_status").execute()
            paid = 0
            pending = 0
            advance = 0
            for row in response.data:
                status = row.get('payment_status', '')
                if status == 'paid':
                    paid += 1
                elif status == 'advance':
                    advance += 1
                elif status in ('partial', 'credit'):
                    pending += 1
            return {'paid': paid, 'pending': pending, 'advance': advance}
        except Exception as e:
            print(f"Error counting payment statuses: {e}")
            return {'paid': 0, 'pending': 0, 'advance': 0}
    
    @staticmethod
    def get_all_paginated(page=1, per_page=10, search=""):
        try:
            offset = (page - 1) * per_page
            
            if search and search.strip():
                search_term = search.strip()
                
                response = supabase.table(Sale.table_name)\
                    .select("*", count="exact")\
                    .ilike("invoice_number", f"%{search_term}%")\
                    .order("date", desc=True)\
                    .range(offset, offset + per_page - 1)\
                    .execute()
                
                cust_response = supabase.table(Sale.table_name)\
                    .select("*", count="exact")\
                    .ilike("customer_name", f"%{search_term}%")\
                    .order("date", desc=True)\
                    .execute()
                
                combined = {}
                for sale in response.data:
                    combined[sale['id']] = sale
                for sale in cust_response.data:
                    combined[sale['id']] = sale
                
                all_results = list(combined.values())
                total = len(all_results)
                paginated = all_results[offset:offset + per_page]
                return paginated, total
            else:
                response = supabase.table(Sale.table_name)\
                    .select("*", count="exact")\
                    .range(offset, offset + per_page - 1)\
                    .order("date", desc=True)\
                    .execute()
                return response.data, response.count
                
        except Exception as e:
            print(f"Error getting sales: {e}")
            return [], 0
    
    @staticmethod
    def get_by_id(sale_id):
        try:
            response = supabase.table(Sale.table_name).select("*").eq("id", sale_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting sale: {e}")
            return None
    
    @staticmethod
    def get_items(sale_id):
        try:
            response = supabase.table("sale_items").select("*").eq("sale_id", sale_id).execute()
            return response.data
        except Exception as e:
            print(f"Error getting sale items: {e}")
            return []
    
    @staticmethod
    def get_total_by_date_range(start_date, end_date):
        try:
            response = supabase.table(Sale.table_name).select("total_amount").gte("date", start_date).lte("date", end_date).execute()
            return sum(s.get("total_amount", 0) for s in response.data)
        except Exception as e:
            print(f"Error getting sales total: {e}")
            return 0
    
    @staticmethod
    def get_count_by_date_range(start_date, end_date):
        try:
            response = supabase.table(Sale.table_name).select("*", count="exact").gte("date", start_date).lte("date", end_date).execute()
            return response.count
        except Exception as e:
            print(f"Error getting sales count: {e}")
            return 0
    
    @staticmethod
    def get_recent(limit=5):
        try:
            response = supabase.table(Sale.table_name).select("*").order("date", desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            print(f"Error getting recent sales: {e}")
            return []
    
    @staticmethod
    def count_by_status(status):
        try:
            if isinstance(status, list):
                response = supabase.table(Sale.table_name).select("id", count="exact").in_("payment_status", status).execute()
            else:
                response = supabase.table(Sale.table_name).select("id", count="exact").eq("payment_status", status).execute()
            return response.count
        except Exception as e:
            print(f"Error counting by status: {e}")
            return 0
    
    @staticmethod
    def get_all_with_items(page=1, per_page=10, search=""):
        sales_data, total = Sale.get_all_paginated(page, per_page, search)
        if not sales_data:
            return [], 0
        Sale._batch_attach_items(sales_data)
        return sales_data, total

    @staticmethod
    def get_all_with_items_bulk(limit=10000):
        """Fetch many sales with items in 2 queries (for exports)."""
        try:
            response = supabase.table(Sale.table_name)\
                .select("*")\
                .order("date", desc=True)\
                .limit(limit)\
                .execute()
            sales = response.data or []
            Sale._batch_attach_items(sales)
            return sales
        except Exception as e:
            print(f"Error bulk-fetching sales with items: {e}")
            return []
    
    @staticmethod
    def create(data, items, advance_used=0):
        """
        Create sale with advance balance redemption support
        """
        try:
            cash_paid = data.get('paid_amount', 0)
            total_paid = cash_paid + advance_used
            total_amount = data.get('total_amount', 0)
            customer_id = data.get('customer_id')
            
            # Calculate payment status
            if total_paid >= total_amount:
                if total_paid > total_amount:
                    new_advance = total_paid - total_amount
                    payment_status = 'advance'
                    due_amount = 0
                    advance_amount = new_advance
                else:
                    payment_status = 'paid'
                    due_amount = 0
                    advance_amount = 0
            else:
                payment_status = 'partial'
                due_amount = total_amount - total_paid
                advance_amount = 0
            
            # Handle advance balance changes
            if advance_used > 0 and customer_id:
                # DEDUCT advance when customer uses it
                User.update_advance_balance(customer_id, advance_used, "deduct")
            
            # Create sale record
            sale_data = {
                'customer_id': customer_id,
                'customer_name': data.get('customer_name', 'Walk-in Customer'),
                'invoice_number': data.get('invoice_number'),
                'total_amount': total_amount,
                'paid_amount': cash_paid,
                'advance_used': advance_used,
                'due_amount': due_amount,
                'advance_amount': advance_amount,
                'payment_status': payment_status,
                'created_by': data.get('created_by'),
                'date': data.get('date'),
                'notes': data.get('notes', '') or ''
            }
            
            sale_response = supabase.table(Sale.table_name).insert(sale_data).execute()
            if not sale_response.data:
                return None
            sale = sale_response.data[0]
            
            # Create sale items
            for item in items:
                item['sale_id'] = sale['id']
                supabase.table("sale_items").insert(item).execute()
            
            # Record advance transaction if advance was used
            if advance_used > 0 and customer_id:
                transaction_data = {
                    'customer_id': customer_id,
                    'sale_id': sale['id'],
                    'amount': advance_used,
                    'type': 'redeem',
                    'notes': f'Redeemed for invoice {sale["invoice_number"]}',
                    'date': datetime.now().isoformat()
                }
                supabase.table("advance_transactions").insert(transaction_data).execute()
            
            # If overpayment created new advance, ADD to balance
            if advance_amount > 0 and customer_id:
                User.update_advance_balance(customer_id, advance_amount, "add")
                
                transaction_data = {
                    'customer_id': customer_id,
                    'sale_id': sale['id'],
                    'amount': advance_amount,
                    'type': 'deposit',
                    'notes': f'Overpayment from invoice {sale["invoice_number"]}',
                    'date': datetime.now().isoformat()
                }
                supabase.table("advance_transactions").insert(transaction_data).execute()
            
            return sale
        except Exception as e:
            print(f"Error creating sale: {e}")
            return None
    
    @staticmethod
    def update(sale_id, data):
        try:
            response = supabase.table(Sale.table_name).update(data).eq("id", sale_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating sale: {e}")
            return None

    @staticmethod
    def update_items(item_updates):
        """Update rate/subtotal for sale line items."""
        try:
            for item in item_updates:
                item_id = item.get('id')
                if not item_id:
                    continue
                supabase.table("sale_items").update({
                    'rate': item.get('rate', 0),
                    'subtotal': item.get('subtotal', 0)
                }).eq("id", item_id).execute()
            return True
        except Exception as e:
            print(f"Error updating sale items: {e}")
            return False
    
    @staticmethod
    def delete(sale_id):
        try:
            supabase.table("sale_items").delete().eq("sale_id", sale_id).execute()
            supabase.table(Sale.table_name).delete().eq("id", sale_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting sale: {e}")
            return False


# ============================================
# EXPENSE MODEL
# ============================================
class Expense:
    table_name = "expenses"
    
    @staticmethod
    def get_all_paginated(page=1, per_page=10, category=None):
        try:
            offset = (page - 1) * per_page
            query = supabase.table(Expense.table_name).select("*", count="exact")
            if category:
                query = query.eq("category", category)
            response = query.range(offset, offset + per_page - 1).order("date", desc=True).execute()
            return response.data, response.count
        except Exception as e:
            print(f"Error getting expenses: {e}")
            return [], 0
    
    @staticmethod
    def get_by_id(expense_id):
        try:
            response = supabase.table(Expense.table_name).select("*").eq("id", expense_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting expense: {e}")
            return None
    
    @staticmethod
    def get_total_by_date_range(start_date, end_date):
        try:
            response = supabase.table(Expense.table_name).select("amount").gte("date", start_date).lte("date", end_date).execute()
            return sum(e.get("amount", 0) for e in response.data)
        except Exception as e:
            print(f"Error getting expenses total: {e}")
            return 0
    
    @staticmethod
    def get_count_by_date_range(start_date, end_date):
        try:
            response = supabase.table(Expense.table_name).select("*", count="exact").gte("date", start_date).lte("date", end_date).execute()
            return response.count
        except Exception as e:
            print(f"Error getting expenses count: {e}")
            return 0
    
    @staticmethod
    def get_recent(limit=5):
        try:
            response = supabase.table(Expense.table_name).select("*").order("date", desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            print(f"Error getting recent expenses: {e}")
            return []
    
    @staticmethod
    def get_categories():
        try:
            response = supabase.table(Expense.table_name).select("category").execute()
            categories = list(set(e.get("category") for e in response.data if e.get("category")))
            return categories
        except Exception as e:
            print(f"Error getting categories: {e}")
            return []
    
    @staticmethod
    def create(data):
        try:
            response = supabase.table(Expense.table_name).insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating expense: {e}")
            return None
    
    @staticmethod
    def update(expense_id, data):
        try:
            response = supabase.table(Expense.table_name).update(data).eq("id", expense_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating expense: {e}")
            return None
    
    @staticmethod
    def delete(expense_id):
        try:
            supabase.table(Expense.table_name).delete().eq("id", expense_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting expense: {e}")
            return False


# ============================================
# PAYMENT MODEL
# ============================================
class Payment:
    table_name = "payments"
    
    @staticmethod
    def get_by_sale_id(sale_id):
        try:
            if not sale_id or sale_id == 'None':
                return []
            response = supabase.table(Payment.table_name).select("*").eq("sale_id", sale_id).order("date", desc=True).execute()
            return response.data
        except Exception as e:
            print(f"Error getting payments: {e}")
            return []
    
    @staticmethod
    def get_by_customer_id(customer_id):
        try:
            response = supabase.table(Payment.table_name).select("*").eq("customer_id", customer_id).order("date", desc=True).execute()
            print(f"Found {len(response.data)} payments for customer {customer_id}")
            return response.data
        except Exception as e:
            print(f"Error getting customer payments: {e}")
            return []
    
    @staticmethod
    def get_total_paid_by_customer(customer_id):
        try:
            response = supabase.table(Payment.table_name).select("amount").eq("customer_id", customer_id).execute()
            total = sum(p.get("amount", 0) for p in response.data)
            return total
        except Exception as e:
            print(f"Error getting total paid: {e}")
            return 0
    
    @staticmethod
    def get_total_paid_by_sale(sale_id):
        try:
            response = supabase.table(Payment.table_name).select("amount").eq("sale_id", sale_id).execute()
            total = sum(p.get("amount", 0) for p in response.data)
            return total
        except Exception as e:
            print(f"Error getting total paid by sale: {e}")
            return 0
    
    @staticmethod
    def create(data):
        try:
            if 'date' not in data:
                data['date'] = datetime.now().isoformat()
            
            response = supabase.table(Payment.table_name).insert(data).execute()
            print(f"Payment created: {response.data}")
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating payment: {e}")
            return None
    
    @staticmethod
    def delete(payment_id):
        try:
            supabase.table(Payment.table_name).delete().eq("id", payment_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting payment: {e}")
            return False
        


@staticmethod
def get_by_email(email):
    """Get user by email"""
    try:
        response = supabase.table("users")\
            .select("*")\
            .ilike("email", email)\
            .execute()
        
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error getting user by email: {e}")
        return None


    @staticmethod
    def count_sales(customer_id):
        """Count total sales for a customer - for delete validation"""
        try:
            response = supabase.table("sales")\
                .select("id", count="exact")\
                .eq("customer_id", customer_id)\
                .execute()
            return response.count or 0
        except Exception as e:
            print(f"Error counting sales for customer {customer_id}: {e}")
            return 0
        
# ============================================
# NOTICE MODEL (UPDATED WITH IMAGE SUPPORT)
# ============================================

class Notice:
    """Notice/Announcement model for Supabase"""
    
    @staticmethod
    def get_active_notices():
        """Get all active notices that should be displayed"""
        try:
            now = datetime.now().isoformat()
            
            response = supabase.table("notices")\
                .select("*")\
                .eq("is_active", True)\
                .execute()
            
            # Filter manually to handle NULL dates properly
            active_notices = []
            for notice in response.data:
                show_from = notice.get('show_from')
                show_until = notice.get('show_until')
                
                show = True
                if show_from and show_from > now:
                    show = False
                if show_until and show_until < now:
                    show = False
                
                if show:
                    active_notices.append(notice)
            
            return active_notices
        except Exception as e:
            print(f"Error fetching notices: {e}")
            return []
    
    @staticmethod
    def get_all_notices_paginated(page=1, per_page=10):
        """Get all notices with pagination for admin panel"""
        try:
            offset = (page - 1) * per_page
            response = supabase.table("notices")\
                .select("*", count="exact")\
                .order("created_at", desc=True)\
                .range(offset, offset + per_page - 1)\
                .execute()
            
            total = response.count or 0
            return response.data if response.data else [], total
        except Exception as e:
            print(f"Error fetching notices: {e}")
            return [], 0
    
    @staticmethod
    def get_by_id(notice_id):
        """Get a single notice by ID"""
        try:
            response = supabase.table("notices")\
                .select("*")\
                .eq("id", notice_id)\
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error fetching notice: {e}")
            return None
    
    @staticmethod
    def create(notice_data):
        """Create a new notice with image support"""
        try:
            # Remove None values so Supabase uses defaults
            clean_data = {k: v for k, v in notice_data.items() if v is not None}
            clean_data['created_at'] = datetime.now().isoformat()
            clean_data['updated_at'] = datetime.now().isoformat()
            
            # Ensure image fields are included
            if 'image_url' not in clean_data:
                clean_data['image_url'] = None
            if 'image_public_id' not in clean_data:
                clean_data['image_public_id'] = None
            if 'image_alt_text' not in clean_data:
                clean_data['image_alt_text'] = None
            
            response = supabase.table("notices").insert(clean_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating notice: {e}")
            return None
    
    @staticmethod
    def update(notice_id, notice_data):
        """Update an existing notice with image support"""
        try:
            # Remove None values
            clean_data = {k: v for k, v in notice_data.items() if v is not None}
            clean_data['updated_at'] = datetime.now().isoformat()
            
            response = supabase.table("notices")\
                .update(clean_data)\
                .eq("id", notice_id)\
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error updating notice: {e}")
            return None
    
    @staticmethod
    def delete(notice_id):
        """Delete a notice and its image from Cloudinary"""
        try:
            # Get notice to check if it has an image
            notice = Notice.get_by_id(notice_id)
            
            # Delete image from Cloudinary if exists
            if notice and notice.get('image_public_id'):
                try:
                    from app.cloudinary_client import delete_image_from_cloudinary
                    delete_image_from_cloudinary(notice.get('image_public_id'))
                except Exception as e:
                    print(f"Error deleting image from Cloudinary: {e}")
            
            response = supabase.table("notices")\
                .delete()\
                .eq("id", notice_id)\
                .execute()
            return True if response.data else False
        except Exception as e:
            print(f"Error deleting notice: {e}")
            return False
    
    @staticmethod
    def toggle_status(notice_id):
        """Toggle notice active status"""
        try:
            notice = Notice.get_by_id(notice_id)
            if not notice:
                return False
            
            new_status = not notice.get('is_active', True)
            response = supabase.table("notices")\
                .update({
                    'is_active': new_status,
                    'updated_at': datetime.now().isoformat()
                })\
                .eq("id", notice_id)\
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error toggling notice: {e}")
            return False
        
# ============================================
# NEWSLETTER MODEL
# ============================================

class Newsletter:
    """Newsletter subscriber and campaign management"""
    
    @staticmethod
    def subscribe(email, name=None, source='footer', customer_id=None):
        """Subscribe a user to newsletter"""
        try:
            # Check if already subscribed
            existing = supabase.table("newsletter_subscribers")\
                .select("*")\
                .eq("email", email)\
                .execute()
            
            if existing.data:
                # Update existing subscriber
                subscriber = existing.data[0]
                update_data = {
                    'is_active': True,
                    'source': source
                }
                if name:
                    update_data['name'] = name
                if customer_id:
                    update_data['customer_id'] = customer_id
                
                response = supabase.table("newsletter_subscribers")\
                    .update(update_data)\
                    .eq("id", subscriber['id'])\
                    .execute()
                
                return response.data[0] if response.data else None
            
            # Create new subscriber
            data = {
                'email': email,
                'name': name,
                'source': source,
                'customer_id': customer_id,
                'is_active': True
            }
            
            response = supabase.table("newsletter_subscribers")\
                .insert(data)\
                .execute()
            
            return response.data[0] if response.data else None
            
        except Exception as e:
            print(f"Error subscribing to newsletter: {e}")
            return None
    
    @staticmethod
    def unsubscribe(email):
        """Unsubscribe a user from newsletter"""
        try:
            response = supabase.table("newsletter_subscribers")\
                .update({'is_active': False})\
                .eq("email", email)\
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error unsubscribing: {e}")
            return None
    
    @staticmethod
    def get_all_subscribers(active_only=True, page=1, per_page=50, search=""):
        """Get all subscribers with pagination"""
        try:
            offset = (page - 1) * per_page
            query = supabase.table("newsletter_subscribers").select("*", count="exact")
            
            if active_only:
                query = query.eq("is_active", True)
            
            if search:
                query = query.ilike("email", f"%{search}%")
            
            response = query.range(offset, offset + per_page - 1)\
                .order("subscribed_at", desc=True)\
                .execute()
            
            return response.data, response.count
        except Exception as e:
            print(f"Error getting subscribers: {e}")
            return [], 0
    
    @staticmethod
    def get_subscriber_by_email(email):
        """Get subscriber by email"""
        try:
            response = supabase.table("newsletter_subscribers")\
                .select("*")\
                .eq("email", email)\
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting subscriber: {e}")
            return None
    
    @staticmethod
    def sync_from_customer(customer_id):
        """Sync customer email to newsletter"""
        try:
            from app.models_supabase import User
            customer = User.get_by_id(customer_id)
            if not customer or not customer.get('email'):
                return None
            
            email = customer.get('email')
            name = customer.get('name')
            
            # Check if already subscribed
            existing = supabase.table("newsletter_subscribers")\
                .select("*")\
                .eq("email", email)\
                .execute()
            
            if existing.data:
                # Update existing
                response = supabase.table("newsletter_subscribers")\
                    .update({
                        'name': name,
                        'customer_id': customer_id,
                        'is_active': True,
                        'source': 'customer_sync'
                    })\
                    .eq("id", existing.data[0]['id'])\
                    .execute()
                return response.data[0] if response.data else None
            else:
                # Create new
                return Newsletter.subscribe(
                    email=email,
                    name=name,
                    source='customer_sync',
                    customer_id=customer_id
                )
                
        except Exception as e:
            print(f"Error syncing customer to newsletter: {e}")
            return None
    
    @staticmethod
    def get_total_subscribers():
        """Get total active subscribers count"""
        try:
            response = supabase.table("newsletter_subscribers")\
                .select("id", count="exact")\
                .eq("is_active", True)\
                .execute()
            return response.count or 0
        except Exception as e:
            print(f"Error counting subscribers: {e}")
            return 0
    
    @staticmethod
    def get_new_subscribers_since(date):
        """Get new subscribers since date"""
        try:
            response = supabase.table("newsletter_subscribers")\
                .select("id", count="exact")\
                .eq("is_active", True)\
                .gte("subscribed_at", date.isoformat())\
                .execute()
            return response.count or 0
        except Exception as e:
            print(f"Error counting new subscribers: {e}")
            return 0