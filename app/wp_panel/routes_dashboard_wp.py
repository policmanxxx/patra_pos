# app/wp_panel/routes.py
from flask import Blueprint, render_template, redirect, url_for,request
from . import wp_panel_bp 
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Transaksi, Menu, WajibPajak
from sqlalchemy import func
from datetime import datetime, date


@wp_panel_bp.route('/panel')
@login_required
def index():
    if getattr(current_user, 'is_admin', False) or getattr(current_user, 'role', None) == 'admin':
        return redirect(url_for('admin_bp.index'))
    if not current_user.wp_id:
        return "Akses Ditolak: Anda bukan Wajib Pajak", 403

    wp_aktif = WajibPajak.query.get(current_user.wp_id)
    wp_id_string = str(current_user.wp_id)

    # --- LOGIKA FILTER TANGGAL ---
    hari_ini = date.today()
    # Default: Tanggal 1 bulan ini
    default_start = hari_ini.replace(day=1).strftime('%Y-%m-%d')
    # Default: Hari ini
    default_end = hari_ini.strftime('%Y-%m-%d')

    # Tangkap request dari URL (misal: ?start_date=2026-06-01)
    start_date_str = request.args.get('start_date', default_start)
    end_date_str = request.args.get('end_date', default_end)

    # Konversi string ke format datetime agar query akurat (mencakup jam 23:59:59 di hari terakhir)
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # --- EKSEKUSI QUERY DENGAN FILTER TANGGAL ---
    
    # 1. Hitung Total Pendapatan Bersih (DPP)
    total_dpp = db.session.query(func.sum(Transaksi.total_dpp))\
        .filter_by(wp_id=wp_id_string)\
        .filter(Transaksi.waktu_transaksi >= start_date)\
        .filter(Transaksi.waktu_transaksi <= end_date).scalar() or 0
        
    # 2. Hitung Titipan PBJT
    total_pbjt = db.session.query(func.sum(Transaksi.total_pbjt))\
        .filter_by(wp_id=wp_id_string)\
        .filter(Transaksi.waktu_transaksi >= start_date)\
        .filter(Transaksi.waktu_transaksi <= end_date).scalar() or 0
        
    # 3. Total Struk
    total_trx = Transaksi.query.filter_by(wp_id=wp_id_string)\
        .filter(Transaksi.waktu_transaksi >= start_date)\
        .filter(Transaksi.waktu_transaksi <= end_date).count()

    # 4. Transaksi Terakhir (Sesuai rentang tanggal)
    recent_trx = Transaksi.query.filter_by(wp_id=wp_id_string)\
        .filter(Transaksi.waktu_transaksi >= start_date)\
        .filter(Transaksi.waktu_transaksi <= end_date)\
        .order_by(Transaksi.waktu_transaksi.desc()).limit(10).all()

    return render_template(
        'wp_panel/dashboard.html', 
        wp_aktif=wp_aktif,
        total_dpp=total_dpp,
        total_pbjt=total_pbjt, 
        total_trx=total_trx,
        recent_trx=recent_trx,
        start_date=start_date_str,
        end_date=end_date_str
    )