from flask import Blueprint
admin_bp = Blueprint('admin_bp', __name__)

# Import sub-modul agar route terbaca
from . import routes_dashboard, routes_wp, routes_user, routes_menu,routes_riwayat,routes_laporan,routes_indikator,routes_analisis