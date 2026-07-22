# app/wp_panel/routes.py
from flask import Blueprint, render_template, redirect, url_for,request,jsonify
from . import wp_panel_bp 
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Transaksi, Menu, WajibPajak,TransaksiDetail
from sqlalchemy import func
from datetime import datetime, date


# ==========================================
# LAPORAN PENJUALAN RINCI
# ==========================================

@wp_panel_bp.route('/laporan')
@login_required
def laporan_penjualan():
    if not current_user.wp_id:
        return "Akses Ditolak", 403

    wp_id_string = str(current_user.wp_id)

    # Logika Filter Tanggal (Sama dengan Dashboard)
    hari_ini = date.today()
    default_start = hari_ini.replace(day=1).strftime('%Y-%m-%d')
    default_end = hari_ini.strftime('%Y-%m-%d')

    start_date_str = request.args.get('start_date', default_start)
    end_date_str = request.args.get('end_date', default_end)

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # Ambil SEMUA transaksi pada rentang tanggal tersebut (diurutkan dari yang terbaru)
    transaksi_lengkap = Transaksi.query.filter_by(wp_id=wp_id_string)\
        .filter(Transaksi.waktu_transaksi >= start_date)\
        .filter(Transaksi.waktu_transaksi <= end_date)\
        .order_by(Transaksi.waktu_transaksi.desc()).all()

    # Hitung Grand Total untuk Footer Tabel
    total_dpp_semua = sum([float(trx.total_dpp or 0) for trx in transaksi_lengkap])
    total_pbjt_semua = sum([float(trx.total_pbjt or 0) for trx in transaksi_lengkap])

    return render_template(
        'wp_panel/laporan.html',
        transaksi=transaksi_lengkap,
        start_date=start_date_str,
        end_date=end_date_str,
        total_dpp=total_dpp_semua,
        total_pbjt=total_pbjt_semua
    )


# app/wp_panel/routes.py

@wp_panel_bp.route('/laporan/ringkasan')
@login_required
def laporan_ringkasan():
    if not current_user.wp_id:
        return "Akses Ditolak", 403

    wp_id = current_user.wp_id

    # Filter Tanggal (Bisa diambil dari request.args seperti kode Anda)
    hari_ini = date.today()
    start_date_str = request.args.get('start_date', hari_ini.replace(day=1).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', hari_ini.strftime('%Y-%m-%d'))
    
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # 1. SALES SUMMARY & PROFIT (Laba/Rugi)
    transaksi_qs = Transaksi.query.filter_by(wp_id=wp_id, status='Selesai').filter(
        Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date
    )
    
    total_transaksi = transaksi_qs.count()
    total_omzet_dpp = db.session.query(func.sum(Transaksi.total_dpp)).filter_by(wp_id=wp_id, status='Selesai').filter(Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date).scalar() or 0
    total_pajak = db.session.query(func.sum(Transaksi.total_pbjt)).filter_by(wp_id=wp_id, status='Selesai').filter(Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date).scalar() or 0
    
    # Hitung HPP total dari TransaksiDetail
    total_hpp = db.session.query(func.sum(TransaksiDetail.hpp_snapshot * TransaksiDetail.qty))\
        .join(Transaksi)\
        .filter(Transaksi.wp_id == wp_id, Transaksi.status == 'Selesai', 
                Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date).scalar() or 0
    
    laba_kotor = float(total_omzet_dpp) - float(total_hpp)

    # 2. RINCIAN METODE PEMBAYARAN
    pembayaran_summary = db.session.query(
        Transaksi.metode_pembayaran, func.sum(Transaksi.grand_total).label('total'), func.count(Transaksi.id).label('jumlah')
    ).filter_by(wp_id=wp_id, status='Selesai')\
     .filter(Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date)\
     .group_by(Transaksi.metode_pembayaran).all()

    # 3. BARANG TERLARIS (Top 5)
    menu_terlaris = db.session.query(
        TransaksiDetail.nama_item_snapshot, 
        func.sum(TransaksiDetail.qty).label('total_qty'),
        func.sum(TransaksiDetail.subtotal_dpp).label('total_pendapatan')
    ).join(Transaksi).filter(Transaksi.wp_id == wp_id, Transaksi.status == 'Selesai', 
                             Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date)\
     .group_by(TransaksiDetail.nama_item_snapshot)\
     .order_by(db.desc('total_qty')).limit(5).all()

    # 4. PERINGATAN STOK MENIPIS (Real-time, tidak terpengaruh filter tanggal)
    stok_menipis = Menu.query.filter(
        Menu.wp_id == wp_id, 
        Menu.is_track_stock == True, 
        Menu.stok <= Menu.batas_stok_minimum,
        Menu.is_active == True
    ).order_by(Menu.stok.asc()).all()

    return render_template(
        'wp_panel/laporan_ringkasan.html',
        start_date=start_date_str, end_date=end_date_str,
        total_transaksi=total_transaksi, total_omzet_dpp=total_omzet_dpp, 
        total_pajak=total_pajak, laba_kotor=laba_kotor, total_hpp=total_hpp,
        pembayaran_summary=pembayaran_summary,
        menu_terlaris=menu_terlaris,
        stok_menipis=stok_menipis
    )    
# ==========================================
# API UNTUK MODAL DETAIL TRANSAKSI
# ==========================================

@wp_panel_bp.route('/api/transaksi/<id_trx>')
@login_required
def get_detail_api(id_trx):
    # Cari transaksi
    trx = Transaksi.query.get_or_404(id_trx)
    
    # Proteksi: Pastikan ini milik resto yang sedang login
    if str(trx.wp_id) != str(current_user.wp_id):
        return jsonify({"error": "Akses ditolak"}), 403

    # Ambil rincian item (Asumsi Anda sudah punya relasi DetailTransaksi / items)
    # Jika Anda belum membuat tabel Detail, kode ini akan mengembalikan list kosong
   
    items_data = []
    # trx.details otomatis memanggil tabel TransaksiDetail karena Anda sudah memasang relationship cascade
    for item in trx.details:
        items_data.append({
            "nama": item.nama_item_snapshot,          # Disesuaikan dengan model Anda
            "harga": float(item.harga_satuan_snapshot), # Disesuaikan dengan model Anda
            "qty": item.qty,
            "subtotal": float(item.subtotal_dpp)      # Disesuaikan dengan model Anda
        })

    return jsonify({
        "no_struk": trx.no_struk,
        "waktu": trx.waktu_transaksi.strftime('%d-%m-%Y %H:%M'),
        "items": items_data,
        "total_dpp": trx.total_dpp,
        "total_pbjt": trx.total_pbjt
    })