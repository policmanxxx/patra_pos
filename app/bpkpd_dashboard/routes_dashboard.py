import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from . import admin_bp  # Import blueprint dari file utama
from flask import Blueprint, render_template, request, redirect, url_for, current_app
from app.extensions import db
from app.models import Transaksi, WajibPajak, Menu
from sqlalchemy import func
from flask_login import login_required

@admin_bp.route('/dashboard')
@login_required
def index():
    # Set zona waktu ke WIB (UTC+7) untuk keakuratan data "Hari Ini"
    wib_now = datetime.utcnow() + timedelta(hours=7)
    hari_ini = wib_now.date()
    awal_bulan = hari_ini.replace(day=1)

    # 1. Agregasi Data Harian (Omzet, PBJT, Jumlah Struk, dan WP Aktif Hari Ini)
    stats_hari_ini = db.session.query(
        func.sum(Transaksi.total_dpp).label('omzet'),
        func.sum(Transaksi.total_pbjt).label('pbjt'),
        func.count(Transaksi.id).label('trx_count'),
        func.count(func.distinct(Transaksi.wp_id)).label('wp_aktif')
    ).filter(func.date(Transaksi.waktu_transaksi + timedelta(hours=7)) == hari_ini).first()

    total_omzet_hari_ini = stats_hari_ini.omzet or 0
    total_pbjt_hari_ini = stats_hari_ini.pbjt or 0
    total_trx_hari_ini = stats_hari_ini.trx_count or 0
    wp_aktif_count = stats_hari_ini.wp_aktif or 0

    # 2. Menghitung Total Seluruh Wajib Pajak yang terdaftar dan aktif
    total_wp = WajibPajak.query.filter_by(is_active=True).count()

    # 3. Leaderboard: Top 5 Wajib Pajak Bulan Ini (Berdasarkan setoran PBJT)
    top_wp = db.session.query(
        WajibPajak.nama_usaha,
        WajibPajak.npwpd,
        func.sum(Transaksi.total_pbjt).label('total_pajak')
    ).join(Transaksi, WajibPajak.id == Transaksi.wp_id) \
     .filter(func.date(Transaksi.waktu_transaksi + timedelta(hours=7)) >= awal_bulan) \
     .group_by(WajibPajak.id, WajibPajak.nama_usaha, WajibPajak.npwpd) \
     .order_by(func.sum(Transaksi.total_pbjt).desc()) \
     .limit(5).all()

    # 4. Mengambil 10 transaksi terakhir (Log Raw)
    recent_trx = db.session.query(Transaksi, WajibPajak.nama_usaha)\
        .join(WajibPajak, Transaksi.wp_id == WajibPajak.id)\
        .order_by(Transaksi.waktu_transaksi.desc())\
        .limit(10).all()


    tujuh_hari_lalu = hari_ini - timedelta(days=6) # 6 hari ke belakang + hari ini = 7 hari

    # Buat kerangka daftar 7 hari terakhir beserta nilai default 0 (Penting agar grafik tidak bolong)
    labels_grafik = []
    data_dict = {}
    for i in range(7):
        tgl = tujuh_hari_lalu + timedelta(days=i)
        labels_grafik.append(tgl.strftime('%d %b')) # Contoh: '01 Jun'
        data_dict[tgl] = 0

    # Query ke database: Kelompokkan (Group By) total PBJT per tanggal
    tren_query = db.session.query(
        func.date(Transaksi.waktu_transaksi + timedelta(hours=7)).label('tanggal'),
        func.sum(Transaksi.total_pbjt).label('total_pbjt')
    ).filter(
        func.date(Transaksi.waktu_transaksi + timedelta(hours=7)) >= tujuh_hari_lalu
    ).group_by(
        func.date(Transaksi.waktu_transaksi + timedelta(hours=7))
    ).order_by('tanggal').all()

    # Isi kerangka tadi dengan data asli dari database
    for row in tren_query:
        if row.tanggal in data_dict:
            data_dict[row.tanggal] = float(row.total_pbjt)

    # Ambil nilai rupiahnya saja untuk dikirim ke grafik
    data_grafik = list(data_dict.values())

    # ==========================================

    # Tambahkan variabel labels_grafik dan data_grafik ke return render_template
    return render_template(
        'admin_bpkpd/dashboard.html', 
        total_omzet_hari_ini=total_omzet_hari_ini,
        total_pbjt_hari_ini=total_pbjt_hari_ini,
        total_trx_hari_ini=total_trx_hari_ini,
        wp_aktif_count=wp_aktif_count,
        total_wp=total_wp,
        top_wp=top_wp,
        recent_trx=recent_trx,
        labels_grafik=labels_grafik,
        data_grafik=data_grafik
    )    