from flask import Blueprint
wp_panel_bp = Blueprint('wp_panel_bp', __name__)

# Import sub-modul agar route terbaca
from . import routes_dashboard_wp,routes_kelola_menu_wp,routes_profil,routes_laporan