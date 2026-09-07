# app/wp_panel/routes_laporan_bulanan.py

import calendar
from datetime import datetime, date
from flask import render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models import Transaksi
from . import wp_panel_bp  # Import blueprint wp_panel

@wp_panel_bp.route('/laporan/bulanan')
@login_required
def laporan_bulanan():
    if not current_user.wp_id:
        return "Akses Ditolak", 403

    wp_id_string = str(current_user.wp_id)
    hari_ini = date.today()

    # 1. Ambil Parameter Bulan dan Tahun dari Dropdown (default bulan ini)
    selected_month = request.args.get('bulan', hari_ini.month, type=int)
    selected_year = request.args.get('tahun', hari_ini.year, type=int)

    # Validasi input
    if selected_month < 1 or selected_month > 12:
        selected_month = hari_ini.month

    # 2. Tentukan Rentang Tanggal 1 Bulan Penuh
    last_day = calendar.monthrange(selected_year, selected_month)[1]
    start_date = datetime(selected_year, selected_month, 1)
    end_date = datetime(selected_year, selected_month, last_day, 23, 59, 59)

    # 3. Query Rekapitulasi per Hari (Group By Date)
    daily_query = db.session.query(
        func.date(Transaksi.waktu_transaksi).label('tanggal'),
        func.count(Transaksi.id).label('total_trx'),
        func.sum(Transaksi.total_dpp).label('total_dpp'),
        func.sum(Transaksi.total_pbjt).label('total_pbjt')
    ).filter(
        Transaksi.wp_id == wp_id_string,
        Transaksi.status == 'Selesai', # Menghitung yang sudah selesai saja
        Transaksi.waktu_transaksi >= start_date,
        Transaksi.waktu_transaksi <= end_date
    ).group_by(
        func.date(Transaksi.waktu_transaksi)
    ).order_by('tanggal').all()

    # 4. Format Data untuk Template
    data_harian = []
    grand_total_trx = 0
    grand_total_dpp = 0.0
    grand_total_pbjt = 0.0

    for row in daily_query:
        tgl_str = str(row.tanggal) 
        try:
            tgl_obj = datetime.strptime(tgl_str, '%Y-%m-%d')
            tgl_tampil = tgl_obj.strftime('%d-%m-%Y')
        except:
            tgl_tampil = tgl_str

        trx = row.total_trx or 0
        dpp = float(row.total_dpp or 0)
        pbjt = float(row.total_pbjt or 0)
        bayar = dpp + pbjt

        data_harian.append({
            'tanggal_tampil': tgl_tampil,
            'tanggal_filter': tgl_str, 
            'total_trx': trx,
            'total_dpp': dpp,
            'total_pbjt': pbjt,
            'total_bayar': bayar
        })

        grand_total_trx += trx
        grand_total_dpp += dpp
        grand_total_pbjt += pbjt

    grand_total_bayar = grand_total_dpp + grand_total_pbjt

    # 5. Daftar bulan dan tahun untuk dropdown
    bulan_list = [
        (1, 'Januari'), (2, 'Februari'), (3, 'Maret'), (4, 'April'),
        (5, 'Mei'), (6, 'Juni'), (7, 'Juli'), (8, 'Agustus'),
        (9, 'September'), (10, 'Oktober'), (11, 'November'), (12, 'Desember')
    ]
    tahun_list = [hari_ini.year, hari_ini.year - 1, hari_ini.year - 2]

    return render_template(
        'wp_panel/laporan_bulanan.html',
        data_harian=data_harian,
        selected_month=selected_month,
        selected_year=selected_year,
        bulan_list=bulan_list,
        tahun_list=tahun_list,
        grand_total_trx=grand_total_trx,
        grand_total_dpp=grand_total_dpp,
        grand_total_pbjt=grand_total_pbjt,
        grand_total_bayar=grand_total_bayar
    )