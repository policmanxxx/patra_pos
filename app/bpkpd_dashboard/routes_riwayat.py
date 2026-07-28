from flask import Blueprint, render_template, request, current_app
from datetime import datetime, timedelta
from . import admin_bp 
from app.extensions import db
from app.models import Transaksi, WajibPajak, TransaksiDetail
from sqlalchemy import func
from flask_login import login_required

@admin_bp.route('/transaksi/riwayat', methods=['GET'])
@login_required
def riwayat_transaksi():
    # 1. Ambil parameter filter dari request args (URL)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    wp_id = request.args.get('wp_id')
    no_struk = request.args.get('no_struk')
    
    # TAMBAHAN: Ambil halaman saat ini (default: 1)
    page = request.args.get('page', 1, type=int)
    per_page = 20 # Jumlah data per halaman

    # Set nilai default jika tidak ada input (Menampilkan 7 hari terakhir)
    wib_now = datetime.utcnow() + timedelta(hours=7)
    
    if not start_date_str or not end_date_str:
        end_date_obj = wib_now.date()
        start_date_obj = end_date_obj - timedelta(days=6)
        start_date_str = start_date_obj.strftime('%Y-%m-%d')
        end_date_str = end_date_obj.strftime('%Y-%m-%d')
    else:
        start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    # 2. Siapkan Kondisi Filter (Base Filters)
    filters = [
        func.date(Transaksi.waktu_transaksi + timedelta(hours=7)) >= start_date_obj,
        func.date(Transaksi.waktu_transaksi + timedelta(hours=7)) <= end_date_obj
    ]

    if wp_id and wp_id != 'all':
        filters.append(Transaksi.wp_id == wp_id)

    if no_struk:
        filters.append(Transaksi.no_struk.ilike(f'%{no_struk}%'))

    # 3. MENGHITUNG RINGKASAN SECARA GLOBAL (OPTIMASI)
    # Query ini menghitung total keseluruhan data yang di-filter (bukan cuma 1 halaman)
    summary_query = db.session.query(
        func.sum(Transaksi.total_dpp).label('total_dpp'),
        func.sum(Transaksi.total_pbjt).label('total_pbjt'),
        func.count(Transaksi.id).label('total_count')
    ).filter(*filters).first()

    total_dpp = summary_query.total_dpp or 0
    total_pbjt = summary_query.total_pbjt or 0
    total_transaksi = summary_query.total_count or 0

    # 4. EKSEKUSI QUERY DENGAN PAGINATION
    query = db.session.query(Transaksi, WajibPajak.nama_usaha)\
        .join(WajibPajak, Transaksi.wp_id == WajibPajak.id)\
        .filter(*filters)\
        .order_by(Transaksi.waktu_transaksi.desc())

    # Gunakan .paginate() bukan .all()
    transaksi_paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    # 5. Ambil daftar semua Wajib Pajak untuk dropdown
    daftar_wp = WajibPajak.query.filter_by(is_active=True).order_by(WajibPajak.nama_usaha).all()

    return render_template(
        'admin_bpkpd/riwayat_transaksi.html',
        transaksi_paginated=transaksi_paginated, # Mengirim objek paginasi
        daftar_wp=daftar_wp,
        # Mempertahankan input form
        current_start_date=start_date_str,
        current_end_date=end_date_str,
        current_wp_id=wp_id,
        current_no_struk=no_struk,
        # Ringkasan data global
        summary_dpp=total_dpp,
        summary_pbjt=total_pbjt,
        summary_count=total_transaksi
    )

# Rute Detail (Tidak ada perubahan, kodenya sudah baik)
@admin_bp.route('/transaksi/detail/<uuid:trx_id>', methods=['GET'])
@login_required
def detail_transaksi(trx_id):
    transaksi = Transaksi.query.get_or_404(trx_id)
    detail_data = []
    for item in transaksi.details:
        detail_data.append({
            'nama_item': item.nama_item_snapshot,
            'qty': item.qty,
            'harga_satuan': float(item.harga_satuan_snapshot),
            'subtotal': float(item.total_harga)
        })
        
    return {
        'no_struk': transaksi.no_struk,
        'tanggal': (transaksi.waktu_transaksi + timedelta(hours=7)).strftime('%d-%m-%Y %H:%M:%S'), # Pastikan zona waktu WIB
        'items': detail_data,
        'grand_total': float(transaksi.grand_total)
    }