from flask import Flask, render_template  # ← IMPORTANT: include render_template
from flask_login import LoginManager
from datetime import datetime
import os

login_manager = LoginManager()

# Absolute paths so templates/static resolve correctly when the app is
# imported from api/index.py on Vercel (cwd != package directory).
APP_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(APP_DIR, "templates")
STATIC_DIR = os.path.join(APP_DIR, "static")

def create_app():
    app = Flask(
        __name__,
        template_folder=TEMPLATE_DIR,
        static_folder=STATIC_DIR,
    )
    
    from app.config import Config
    app.config.from_object(Config)
    
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # ========== ERROR HANDLERS (INSIDE create_app) ==========
    @app.errorhandler(404)
    def page_not_found(e):
        from flask_login import current_user
        if current_user.is_authenticated and current_user.role == 'admin':
            return render_template('admin/404.html'), 404
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500
    
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html'), 403
    # =======================================================

    # Register context processors
    @app.context_processor
    def inject_globals():
        return {
            "business_name": Config.BUSINESS_NAME,
            "currency": Config.CURRENCY,
            "current_year": datetime.now().year
        }
    
    # Register template filters
    @app.template_filter("currency")
    def currency_filter(amount):
        from app.utils import format_currency
        return format_currency(amount)
    
    # Register blueprints
    from app.routes.public import bp as public_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.customer import bp as customer_bp
    from app.routes.admin_products import bp as admin_products_bp
    
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(admin_products_bp)
    
    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models_supabase import User
    from app.login_user import LoginUser
    
    user_data = User.get_by_id(int(user_id))
    if user_data:
        return LoginUser(user_data)
    return None