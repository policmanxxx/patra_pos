from flask import Flask
from .extensions import db,login_manager
from dotenv import load_dotenv
import os

def create_app():
    app = Flask(__name__)
    
    # Ambil dari environment variable
    database_url = os.getenv('DATABASE_URL')
    secret_key = os.getenv('SECRET_KEY')

    
    if not database_url:
        raise RuntimeError("Variabel DATABASE_URL tidak ditemukan di file .env atau environment server!")

    app.config['SECRET_KEY'] = secret_key or 'rahasia-default-hanya-untuk-lokal'
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Inisialisasi ekstensi
    db.init_app(app)
    login_manager.init_app(app) 
    login_manager.login_view = 'auth_bp.login'
    from app.models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        # Karena kita menggunakan UUID, kita langsung gunakan user_id
        return User.query.get(user_id)
    # Mendaftarkan Blueprint tes
    from .api_pos.routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')
  

    # Mendaftarkan Blueprint Dashboard Admin
    from .bpkpd_dashboard import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Mendaftarkan Blueprint UI Kasir (Akses Utama)
    from .ui_pos import ui_pos_bp
    app.register_blueprint(ui_pos_bp)

    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp)

    from .wp_panel import wp_panel_bp
    app.register_blueprint(wp_panel_bp, url_prefix='/wp')

    @app.route('/ping')
    def ping():
        return {"status": "ok", "message": "Server POS Wajib Pajak Berjalan Lancar"}

    return app