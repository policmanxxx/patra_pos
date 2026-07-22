from . import ui_pos_bp
from flask import Blueprint, render_template,jsonify, request,send_from_directory, current_app,redirect,url_for
import uuid
from app.models import Transaksi, WajibPajak, Menu, TransaksiDetail
# 1. Tambahkan import current_user di sini
from flask_login import login_required, current_user 
from datetime import datetime, date, timedelta
from sqlalchemy import func
from app.extensions import db


@ui_pos_bp.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@ui_pos_bp.route('/')
@login_required
def halaman_kasir():
    resto = WajibPajak.query.get(current_user.wp_id)
    nama_toko = resto.nama_usaha if resto else "Nama Restoran"
    semua_menu = Menu.query.filter_by(
        is_active=True, 
        wp_id=current_user.wp_id
    ).all()
    if getattr(current_user, 'is_admin', False) or getattr(current_user, 'role', None) == 'admin':
        return redirect(url_for('admin_bp.index'))
    daftar_menu = []
    for m in semua_menu:
        daftar_menu.append({
            "id": str(m.id),
            "nama": m.nama_menu,    
            "harga": float(m.harga_dasar),
            # --- TAMBAHAN BARU ---
            "diskon": float(m.diskon),
            "is_taxable": bool(m.is_taxable), 
            "is_tax_inclusive": bool(m.is_tax_inclusive), 
            "is_track_stock": bool(m.is_track_stock),
            "stok": int(m.stok),
            # ---------------------
            "foto": m.foto_url
        })
    
    return render_template('pos_kasir/index.html', menus=daftar_menu,nama_resto=nama_toko)


@ui_pos_bp.route('/rekap-harian')
@login_required
def get_rekap_harian():

    # Mengambil tanggal hari ini
    wib_now = datetime.utcnow() + timedelta(hours=7)
    hari_ini = wib_now.date()
    
    # Query total grand_total hari ini khusus untuk WP tersebut
    total = db.session.query(func.sum(Transaksi.grand_total))\
        .filter(Transaksi.wp_id == current_user.wp_id)\
        .filter(func.date(Transaksi.waktu_transaksi) == hari_ini)\
        .scalar() or 0
        
    return jsonify({"total": float(total)})    

@ui_pos_bp.route('/waiter')
@login_required
def halaman_waiter():
    # Ambil data menu seperti di kasir
    semua_menu = Menu.query.filter_by(
        is_active=True, 
        wp_id=current_user.wp_id
    ).all()
    
    daftar_menu = []
    for m in semua_menu:
        daftar_menu.append({
            "id": str(m.id),
            "nama": m.nama_menu,    
            "harga": float(m.harga_dasar),
            "diskon": float(m.diskon),
            "is_track_stock": bool(m.is_track_stock),
            "stok": int(m.stok),
            "foto": m.foto_url
        })
    
    return render_template('pos_kasir/waiter.html', menus=daftar_menu)   

@ui_pos_bp.route('/api/waiter/kirim', methods=['POST'])
@login_required
def api_waiter_kirim():
    try:
        data = request.get_json()
        no_meja = data.get('meja')
        items = data.get('items', [])
        
        if not items:
            return jsonify({'status': 'error', 'pesan': 'Pesanan kosong'}), 400

        # Buat Header Transaksi "Menggantung"
        baru_trx = Transaksi(
            wp_id=current_user.wp_id,
            no_struk="OB-" + str(uuid.uuid4())[:8].upper(), # Prefix OB = Open Bill
            waktu_transaksi=datetime.utcnow() + timedelta(hours=7),
            no_meja=no_meja,
            status='Belum Bayar', # <--- Kunci pembedanya ada di sini
            is_reported=False,
            total_dpp=0, total_pbjt=0, grand_total=0
        )
        db.session.add(baru_trx)
        db.session.flush()

        # Simpan Detail Pesanan
        for item in items:
            detail = TransaksiDetail(
                transaksi_id=baru_trx.id,
                menu_id=item.get('id'),
                nama_item_snapshot=item.get('nama'),
                harga_satuan_snapshot=item.get('harga'), 
                qty=item.get('qty'),
                subtotal_dpp=0, subtotal_pajak=0, total_harga=0 # Dihitung presisi nanti di kasir
            )
            db.session.add(detail)

        db.session.commit()
        return jsonify({'status': 'sukses'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'pesan': str(e)}), 500


# --- API UNTUK KASIR MENGAMBIL PESANAN MENGGANTUNG ---
@ui_pos_bp.route('/api/kasir/open-bills', methods=['GET'])
@login_required
def api_kasir_get_open_bills():
    # Cari semua transaksi wp ini yang statusnya masih 'Belum Bayar'
    open_bills_db = Transaksi.query.filter_by(
        wp_id=current_user.wp_id, 
        status='Belum Bayar'
    ).order_by(Transaksi.waktu_transaksi.asc()).all()
    
    hasil = []
    for trx in open_bills_db:
        items = []
        for d in trx.details:
            # Ambil sisa data diskon & pajak langsung dari master menu agar update
            menu_asli = Menu.query.get(d.menu_id)
            items.append({
                "id": str(d.menu_id),
                "nama": d.nama_item_snapshot,
                "harga": float(d.harga_satuan_snapshot),
                "qty": d.qty,
                "diskon": float(menu_asli.diskon) if menu_asli else 0,
                "is_taxable": bool(menu_asli.is_taxable) if menu_asli else True,
                "is_tax_inclusive": bool(menu_asli.is_tax_inclusive) if menu_asli else False,
                "is_track_stock": bool(menu_asli.is_track_stock) if menu_asli else False,
                "stok": int(menu_asli.stok) if menu_asli else 0
            })
            
        hasil.append({
            "id": trx.no_struk, # Kita pakai no_struk (OB-XXX) sebagai ID referensi
            "meja": trx.no_meja,
            "waktu": trx.waktu_transaksi.isoformat(),
            "items": items
        })
        
    return jsonify({'status': 'sukses', 'data': hasil}), 200