from flask import Blueprint
ui_pos_bp = Blueprint('ui_pos_bp', __name__)

# Import sub-modul agar route terbaca
from . import routes_kasir