from flask import Blueprint, render_template, request, current_app
from datetime import datetime, timedelta
from . import admin_bp 
from app.extensions import db
from app.models import Transaksi, WajibPajak, TransaksiDetail
from sqlalchemy import func
from flask_login import login_required

# ... rute dashboard sebelumnya ...

@admin_bp.route('/transaksi/riwayat', methods=['GET'])
@login_required
def riwayat_transaksi():
    # 1. Ambil parameter filter dari request args (URL)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    wp_id = request.args.get('wp_id')
    no_struk = request.args.get('no_struk')

    # Set nilai default jika tidak ada input (Menampilkan 7 hari terakhir)
    wib_now = datetime.utcnow() + timedelta(hours=7)
    
    if not start_date_str or not end_date_str:
        end_date_obj = wib_now.date()
        start_date_obj = end_date_obj - timedelta(days=6)
        # Format ke string YYYY-MM-DD untuk ditampilkan di input form
        start_date_str = start_date_obj.strftime('%Y-%m-%d')
        end_date_str = end_date_obj.strftime('%Y-%m-%d')
    else:
        # Konversi dari string form HTML (YYYY-MM-DD) ke objek datetime
        start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    # 2. Siapkan Base Query
    # Join Transaksi dengan WajibPajak untuk mendapatkan nama_usaha
    query = db.session.query(Transaksi, WajibPajak.nama_usaha)\
        .join(WajibPajak, Transaksi.wp_id == WajibPajak.id)

    # 3. Terapkan Filter (Dynamically Build Query)
    
    # Perbaikan Filter Tanggal:
    # Transaksi.waktu_transaksi di-cast ke date dan disesuaikan zona waktunya (jika disimpan dalam UTC)
    query = query.filter(func.date(Transaksi.waktu_transaksi + timedelta(hours=7)) >= start_date_obj)
    query = query.filter(func.date(Transaksi.waktu_transaksi + timedelta(hours=7)) <= end_date_obj)

    # Filter berdasarkan Wajib Pajak (jika dipilih dari dropdown)
    if wp_id and wp_id != 'all':
        query = query.filter(Transaksi.wp_id == wp_id)

    # Filter berdasarkan Nomor Struk (pencarian teks spesifik)
    if no_struk:
        # Menggunakan ilike untuk pencarian case-insensitive dan parsial
        query = query.filter(Transaksi.no_struk.ilike(f'%{no_struk}%'))

    # 4. Eksekusi Query dan Urutkan dari yang terbaru
    transaksi_list = query.order_by(Transaksi.waktu_transaksi.desc()).all()

    # 5. Hitung Ringkasan (Summary) dari hasil pencarian
    total_dpp = sum(trx.Transaksi.total_dpp for trx in transaksi_list)
    total_pbjt = sum(trx.Transaksi.total_pbjt for trx in transaksi_list)
    total_transaksi = len(transaksi_list)

    # 6. Ambil daftar semua Wajib Pajak untuk dropdown filter HTML
    daftar_wp = WajibPajak.query.filter_by(is_active=True).order_by(WajibPajak.nama_usaha).all()

    return render_template(
        'admin_bpkpd/riwayat_transaksi.html',
        transaksi_list=transaksi_list,
        daftar_wp=daftar_wp,
        # Mengirim parameter pencarian kembali ke template untuk mempertahankan input user di form
        current_start_date=start_date_str,
        current_end_date=end_date_str,
        current_wp_id=wp_id,
        current_no_struk=no_struk,
        # Ringkasan data
        summary_dpp=total_dpp,
        summary_pbjt=total_pbjt,
        summary_count=total_transaksi
    )

# Rute tambahan untuk mengambil detail item per transaksi via AJAX/Fetch
@admin_bp.route('/transaksi/detail/<uuid:trx_id>', methods=['GET'])
@login_required
def detail_transaksi(trx_id):
    # Rute ini berguna jika Anda ingin membuat modal popup saat struk diklik
    transaksi = Transaksi.query.get_or_404(trx_id)
    
    # Karena kita sudah mendefinisikan cascade/backref 'details' di model Transaksi, 
    # kita bisa langsung mengakses transaksi.details
    
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
        'tanggal': transaksi.waktu_transaksi.strftime('%d-%m-%Y %H:%M:%S'),
        'items': detail_data,
        'grand_total': float(transaksi.grand_total)
    }