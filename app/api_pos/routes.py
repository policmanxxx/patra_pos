from flask import Blueprint, jsonify, request
from app.extensions import db
from datetime import datetime, timedelta
from app.models import WajibPajak,KategoriMenu, Menu,Transaksi,TransaksiDetail,User
from werkzeug.security import check_password_hash
from .sync_handler import process_bulk_transactions
from flask_jwt_extended import create_access_token,jwt_required, get_jwt
from flask_login import login_required
# Mendefinisikan Blueprint untuk API POS
api_bp = Blueprint('api_pos', __name__)

@api_bp.route('/test-wp', methods=['GET'])
def test_wajib_pajak():
    # 1. Cek apakah sudah ada data di tabel Wajib Pajak
    wp_exist = WajibPajak.query.first()
    
    if not wp_exist:
        # 2. Jika kosong, kita buat 1 data dummy
        wp_baru = WajibPajak(
            npwpd="PJT-3516-2026-001",
            nama_usaha="Warkop Mojopahit",
            alamat="Jl. Gajah Mada, Kota Mojokerto",
            kode_kecamatan="35161", # Contoh kode
            tarif_pbjt=10.00
        )
        db.session.add(wp_baru)
        db.session.commit()
        
        return jsonify({
            "status": "sukses",
            "pesan": "Wajib Pajak Warkop Mojopahit berhasil ditambahkan ke PostgreSQL!",
            "data": {
                "id": str(wp_baru.id),
                "nama_usaha": wp_baru.nama_usaha
            }
        })
    else:
        # 3. Jika sudah ada, tampilkan datanya
        return jsonify({
            "status": "sudah_ada",
            "pesan": "Data Wajib Pajak sudah ada di database.",
            "data": {
                "id": str(wp_exist.id),
                "nama_usaha": wp_exist.nama_usaha,
                "npwpd": wp_exist.npwpd
            }
        })
        
@api_bp.route('/sync', methods=['POST'])
@login_required
def sync_transaksi():
    # Menangkap JSON dari body request
    payload = request.get_json()
    
    if not payload:
         return jsonify({"status": "error", "pesan": "Tidak ada data JSON yang diterima"}), 400
      
    payload['wp_id'] = str(current_user.wp_id)     
    # Lempar JSON ke file handler
    response_data, status_code = process_bulk_transactions(payload)
    
    return jsonify(response_data), status_code 

@api_bp.route('/sinkronisasi-menu', methods=['GET'])
def sinkronisasi_menu():
    # Misal Android mengirimkan parameter wp_id melalui query string
    wp_id = request.args.get('wp_id')
    if not wp_id:
        return jsonify({'error': 'wp_id wajib diisi'}), 400

    # 1. Ambil data Kategori
    kategori_query = KategoriMenu.query.filter_by(wp_id=wp_id).all()
    kategori_list = [{
        'id': str(k.id),
        'wp_id': str(k.wp_id),
        'nama_kategori': k.nama_kategori,
        'urutan': k.urutan
    } for k in kategori_query]

    # 2. Ambil data Menu
    menu_query = Menu.query.filter_by(wp_id=wp_id, is_active=True).all()
    menu_list = [{
        'id': str(m.id),
        'wp_id': str(m.wp_id),
        'kategori_id': str(m.kategori_id) if m.kategori_id else None,
        'kode_sku': m.kode_sku,
        'nama_menu': m.nama_menu,
        'harga_dasar': float(m.harga_dasar),
        'diskon': float(m.diskon),
        'is_track_stock': 1 if m.is_track_stock else 0, # Konversi ke format SQLite
        'stok': m.stok,
        'is_tax_inclusive': 1 if m.is_tax_inclusive else 0,
        'is_taxable': 1 if m.is_taxable else 0,
        'foto_url': m.foto_url,
        'hpp': float(m.hpp)
    } for m in menu_query]

    return jsonify({
        'status': 'success',
        'kategori': kategori_list,
        'menu': menu_list
    }), 200  

@api_bp.route('/sync-transaksi', methods=['POST'])
def sync_transaksi_mobile():
    data = request.get_json()
    
    # Cek apakah ID transaksi ini sudah ada di PostgreSQL (mencegah data ganda)
    existing_tx = Transaksi.query.filter_by(id=data['id']).first()
    if existing_tx:
        return jsonify({'status': 'already_exists'}), 200

    try:
        # 1. Simpan ke tabel Transaksi
        baru_tx = Transaksi(
            id=data['id'],
            wp_id=data['wp_id'],
            shift_id=data['shift_id'],
            kasir_id=data['kasir_id'],
            no_struk=data['no_struk'],
            waktu_transaksi=datetime.fromisoformat(data['waktu_transaksi']),
            no_meja=data.get('no_meja', ''),
            total_dpp=data['total_dpp'],
            total_diskon=data['total_diskon'],
            total_pbjt=data['total_pbjt'],
            grand_total=data['grand_total'],
            metode_pembayaran=data['metode_pembayaran'],
            status=data['status']
        )
        db.session.add(baru_tx)

        # 2. Simpan ke tabel Detail Transaksi & POTONG STOK
        for detail in data['details']:
            qty_terjual = int(detail['qty'])
            menu_id = detail.get('menu_id')

            # ---> TAMBAHAN LOGIKA POTONG STOK <---
            if menu_id:
                menu_db = Menu.query.get(menu_id)
                # Cek apakah menu ditemukan DAN fitur tracking stoknya aktif
                if menu_db and getattr(menu_db, 'is_track_stock', False):
                    menu_db.stok = menu_db.stok - qty_terjual
            # --------------------------------------

            baru_detail = TransaksiDetail(
                id=detail['id'],
                transaksi_id=detail['transaksi_id'],
                menu_id=menu_id,
                nama_item_snapshot=detail['nama_item_snapshot'],
                harga_satuan_snapshot=detail['harga_satuan_snapshot'],
                hpp_snapshot=detail.get('hpp_snapshot'),
                qty=qty_terjual,
                subtotal_dpp=detail['subtotal_dpp'],
                subtotal_pajak=detail['subtotal_pajak'],
                total_harga=detail['total_harga']
            )
            db.session.add(baru_detail)

        # Jika semua aman, simpan ke database
        db.session.commit()
        return jsonify({'status': 'synced_successfully'}), 201 

    except Exception as e:
        # Jika terjadi error saat memproses (misal format salah/stok gagal), batalkan semua!
        db.session.rollback()
        logging.error(f"Error sync transaksi mobile: {str(e)}")
        return jsonify({'status': 'error', 'pesan': str(e)}), 500    

@api_bp.route('/login', methods=['POST'])
def login_mobile():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username dan password wajib diisi'}), 400

    # Cari user berdasarkan username
    user = User.query.filter_by(username=username).first()

    # Validasi user dan kecocokan password
    if user and user.check_password(password):
        if not user.is_active:
            return jsonify({'status': 'error', 'message': 'Akun kasir dinonaktifkan'}), 403

        # Jika sukses, kembalikan data penting untuk disimpan di HP
        return jsonify({
            'status': 'success',
            'data': {
                'user_id': str(user.id),
                'wp_id': str(user.wp_id) if user.wp_id else None,
                'nama_lengkap': user.nama_lengkap,
                'role': user.role
            }
        }), 200
    else:
        return jsonify({'status': 'error', 'message': 'Username atau password salah'}), 401
        
@api_bp.route('/sinkronisasi-profil', methods=['GET'])
def sinkronisasi_profil():
    wp_id = request.args.get('wp_id')
    if not wp_id:
        return jsonify({'error': 'wp_id wajib diisi'}), 400

    wp = WajibPajak.query.get(wp_id)
    if not wp:
        return jsonify({'error': 'Wajib Pajak tidak ditemukan'}), 404

    return jsonify({
        'status': 'success',
        'data': {
            'id': str(wp.id),
            'npwpd': wp.npwpd,
            'nama_usaha': wp.nama_usaha,
            'alamat': wp.alamat,
            'tarif_pbjt': float(wp.tarif_pbjt),
            'logo_url': wp.logo_url
        }
    }), 200