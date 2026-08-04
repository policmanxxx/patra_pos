from flask import Blueprint, jsonify, request,current_app,render_template_string
from app.extensions import db
from datetime import datetime, timedelta
from app.models import WajibPajak,KategoriMenu, Menu,Transaksi,TransaksiDetail,User
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import os
from .sync_handler import process_bulk_transactions
from flask_jwt_extended import create_access_token,jwt_required, get_jwt
from flask_login import login_required,current_user
import uuid
import logging
from sqlalchemy import func
# Mendefinisikan Blueprint untuk API POS
api_bp = Blueprint('api_pos', __name__)

@api_bp.route('/test-wp', methods=['GET'])
def test_wajib_pajak():
    # 1. Cek apakah sudah ada data di tabel Wajib Pajak
    wp_exist = WajibPajak.query.first()
    
    if not wp_exist:
        # 2. Jika kosong, kita buat 1 data dummy
        wp_baru = WajibPajak(
            npwpd="P000000000000",
            nama_usaha="BPKPD",
            alamat="Jl. Letkol Sumarjo, Kota Mojokerto",
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

# LOGIN MOBILE
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
                'kasir_nama': user.nama_lengkap,
                'kasir_id': str(user.id),
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
            'logo_url': wp.logo_url,
            'tarif_pbjt':wp.tarif_pbjt,
            'logo_struk_url':wp.logo_struk_url,
            'kode_wp':wp.kode_wp
        }
    }), 200
    
    
 # ---> tambah menu dari android <---    
@api_bp.route('/menu/tambah', methods=['POST'])
def api_tambah_menu():
    try:
        wp_id_str = request.form.get('wp_id')
        nama_menu = request.form.get('nama_menu')
        harga_dasar = request.form.get('harga_dasar')

        if not wp_id_str or not nama_menu or harga_dasar is None:
            return jsonify({'success': False, 'message': 'wp_id, nama_menu, dan harga_dasar wajib diisi!'}), 400

        # KONVERSI STRING KE UUID OBJECT UNTUK MENGHINDARI ERROR 500
        try:
            wp_id = uuid.UUID(wp_id_str)
        except ValueError:
            return jsonify({'success': False, 'message': 'Format wp_id tidak valid!'}), 400

        kategori_id_str = request.form.get('kategori_id')
        kategori_id = None
        if kategori_id_str and str(kategori_id_str).strip() != '' and str(kategori_id_str).lower() != 'null':
            try:
                kategori_id = uuid.UUID(kategori_id_str)
            except ValueError:
                pass  # Jika gagal parsing, biarkan tetap None
            
        kode_sku = request.form.get('kode_sku', '')

        # Konversi angka & boolean
        harga_dasar = float(harga_dasar)
        diskon = float(request.form.get('diskon', 0))
        is_tax_inclusive = str(request.form.get('is_tax_inclusive', 'false')).lower() == 'true'
        is_taxable = str(request.form.get('is_taxable', 'true')).lower() == 'true'
        is_track_stock = str(request.form.get('is_track_stock', 'false')).lower() == 'true'
        stok = int(request.form.get('stok', 0))
        is_active = str(request.form.get('is_active', 'true')).lower() == 'true'

        # --- TANGKAP GAMBAR DARI FLUTTER ---
        foto_file = request.files.get('foto')
        nama_file_foto = None
        
        if foto_file and foto_file.filename != '':
            nama_file_foto = secure_filename(foto_file.filename)
            jalur_simpan = os.path.join(current_app.root_path, 'static', 'uploads', 'menu', nama_file_foto)
            os.makedirs(os.path.dirname(jalur_simpan), exist_ok=True)
            foto_file.save(jalur_simpan)

        # Simpan ke DB
        menu_baru = Menu(
            wp_id=wp_id,                  # Menggunakan objek UUID
            kategori_id=kategori_id,      # Menggunakan objek UUID / None
            kode_sku=kode_sku,
            nama_menu=nama_menu,
            harga_dasar=harga_dasar,
            diskon=diskon,
            is_tax_inclusive=is_tax_inclusive,
            is_taxable=is_taxable,
            is_track_stock=is_track_stock,
            stok=stok if is_track_stock else 0,
            is_active=is_active,
            foto_url=nama_file_foto
        )

        db.session.add(menu_baru)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Menu berhasil ditambahkan!'}), 201

    except Exception as e:
        db.session.rollback()
        # Cetak error ke terminal Flask agar jika ada kendala lain terlihat jelas
        print(f"DEBUG ERROR 500 TAMBAH MENU: {str(e)}")
        return jsonify({'success': False, 'message': f'Kesalahan Server: {str(e)}'}), 500   
 
@api_bp.route('/kategori/tambah', methods=['POST'])
def api_tambah_kategori():
    try:
        wp_id_str = request.form.get('wp_id') or request.json.get('wp_id')
        nama_kategori = request.form.get('nama_kategori') or request.json.get('nama_kategori')

        if not wp_id_str or not nama_kategori:
            return jsonify({'success': False, 'message': 'wp_id dan nama_kategori wajib diisi!'}), 400

        try:
            wp_id = uuid.UUID(wp_id_str)
        except ValueError:
            return jsonify({'success': False, 'message': 'Format wp_id tidak valid!'}), 400

        # Cari urutan terakhir
        kategori_terakhir = KategoriMenu.query.filter_by(wp_id=wp_id).order_by(KategoriMenu.urutan.desc()).first()
        urutan_baru = (kategori_terakhir.urutan + 1) if kategori_terakhir else 1

        kategori_baru = KategoriMenu(
            wp_id=wp_id,
            nama_kategori=nama_kategori,
            urutan=urutan_baru
        )
        
        db.session.add(kategori_baru)
        db.session.commit()

        return jsonify({
            'success': True, 
            'message': 'Kategori berhasil ditambahkan!',
            'data': {
                'id': str(kategori_baru.id),
                'nama_kategori': kategori_baru.nama_kategori
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error Server: {str(e)}'}), 500 

@api_bp.route('/menu/hapus', methods=['POST'])
def api_hapus_menu():
    try:
        data = request.get_json()
        menu_id_str = data.get('menu_id')

        if not menu_id_str:
            return jsonify({'success': False, 'message': 'ID Menu wajib diisi'}), 400

        menu_id = uuid.UUID(menu_id_str)
        menu = Menu.query.get(menu_id)

        if not menu:
            return jsonify({'success': False, 'message': 'Menu tidak ditemukan'}), 404

        # Soft delete: Ubah is_active jadi False agar tidak muncul di POS, 
        # tapi histori transaksi masa lalu tidak error
        menu.is_active = False 
        db.session.commit()

        return jsonify({'success': True, 'message': f'Menu {menu.nama_menu} berhasil dinonaktifkan/dihapus.'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error Server: {str(e)}'}), 500
 
@api_bp.route('/laporan/ringkasan', methods=['GET'])
def api_laporan_ringkasan():
    # 1. Ambil Parameter dari Flutter
    wp_id = request.args.get('wp_id')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not wp_id:
        return jsonify({"status": "error", "message": "wp_id tidak ditemukan"}), 400

    # 2. Parsing Tanggal
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    except Exception:
        hari_ini = date.today()
        start_date = datetime.combine(hari_ini.replace(day=1), datetime.min.time())
        end_date = datetime.combine(hari_ini, datetime.max.time())

    # 3. Hitung Metrik Utama (Total Transaksi, Omzet, Pajak)
    transaksi_qs = Transaksi.query.filter_by(wp_id=wp_id, status='Selesai').filter(
        Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date
    )
    total_transaksi = transaksi_qs.count()
    
    total_omzet_dpp = db.session.query(func.sum(Transaksi.total_dpp)).filter_by(wp_id=wp_id, status='Selesai').filter(
        Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date
    ).scalar() or 0
    
    total_pajak = db.session.query(func.sum(Transaksi.total_pbjt)).filter_by(wp_id=wp_id, status='Selesai').filter(
        Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date
    ).scalar() or 0
    
    # 4. Hitung Laba Kotor (Omzet - HPP)
    total_hpp = db.session.query(func.sum(TransaksiDetail.hpp_snapshot * TransaksiDetail.qty))\
        .join(Transaksi).filter(
            Transaksi.wp_id == wp_id, Transaksi.status == 'Selesai', Transaksi.is_void == False,TransaksiDetail.is_void == False,
            Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date
        ).scalar() or 0
    
    laba_kotor = float(total_omzet_dpp) - float(total_hpp)

    # 5. Ambil Top 5 Menu Terlaris
    menu_terlaris_query = db.session.query(
        TransaksiDetail.nama_item_snapshot, 
        func.sum(TransaksiDetail.qty).label('total_qty'),
        func.sum(TransaksiDetail.subtotal_dpp).label('total_pendapatan')
    ).join(Transaksi).filter(
        Transaksi.wp_id == wp_id, Transaksi.status == 'Selesai', TransaksiDetail.is_void == False,Transaksi.is_void == False,
        Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date
    ).group_by(TransaksiDetail.nama_item_snapshot).order_by(db.desc('total_qty')).limit(5).all()

    top_menu = [
        {
            "nama": m.nama_item_snapshot, 
            "qty": int(m.total_qty), 
            "omzet": float(m.total_pendapatan)
        } for m in menu_terlaris_query
    ]

    # 6. Data Grafik Tren Penjualan Harian
    grafik_query = db.session.query(
        func.date(Transaksi.waktu_transaksi).label('tanggal'),
        func.sum(Transaksi.total_dpp).label('omzet')
    ).filter(
        Transaksi.wp_id == wp_id, Transaksi.status == 'Selesai',
        TransaksiDetail.is_void == False,Transaksi.is_void == False,
        Transaksi.waktu_transaksi >= start_date, Transaksi.waktu_transaksi <= end_date
    ).group_by(func.date(Transaksi.waktu_transaksi)).order_by('tanggal').all()

    label_grafik = [g.tanggal.strftime('%d %b') for g in grafik_query]
    data_grafik = [float(g.omzet) for g in grafik_query]

    # 7. Kembalikan Response JSON
    return jsonify({
        "status": "success",
        "data": {
            "periode": {"start": start_date_str, "end": end_date_str},
            "total_transaksi": total_transaksi,
            "omzet_dpp": float(total_omzet_dpp),
            "total_pbjt": float(total_pajak),
            "laba_kotor": float(laba_kotor),
            "top_menu": top_menu,
            "grafik": {
                "label": label_grafik,
                "data": data_grafik
            }
        }
    })


@api_bp.route('/laporan/transaksi', methods=['GET'])
def api_laporan_transaksi():
    # 1. Ambil Parameter
    wp_id = request.args.get('wp_id')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    page = request.args.get('page', 1, type=int)

    if not wp_id:
        return jsonify({"status": "error", "message": "wp_id tidak ditemukan"}), 400

    # 2. Parsing Tanggal
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    except Exception:
        hari_ini = date.today()
        start_date = datetime.combine(hari_ini.replace(day=1), datetime.min.time())
        end_date = datetime.combine(hari_ini, datetime.max.time())

    # 3. Eksekusi Query dengan Pagination
    query = Transaksi.query.filter_by(wp_id=wp_id).filter(
        Transaksi.waktu_transaksi >= start_date,
        Transaksi.waktu_transaksi <= end_date
    ).order_by(Transaksi.waktu_transaksi.desc())

    # Ambil 20 transaksi per halaman agar mobile app ringan
    transaksi_paginated = query.paginate(page=page, per_page=20, error_out=False)

    data_transaksi = []
    for trx in transaksi_paginated.items:
        data_transaksi.append({
            "id": trx.id,
            "no_struk": trx.no_struk,
            "waktu": trx.waktu_transaksi.strftime('%d %b %Y • %H:%M'),
            "total_dpp": float(trx.total_dpp or 0),
            "total_pbjt": float(trx.total_pbjt or 0),
            "metode_pembayaran": trx.metode_pembayaran or "Tunai",
            "is_void": getattr(trx, 'is_void', False)
        })

    return jsonify({
        "status": "success",
        "data": data_transaksi,
        "pagination": {
            "current_page": transaksi_paginated.page,
            "total_pages": transaksi_paginated.pages,
            "has_next": transaksi_paginated.has_next
        }
    })    

@api_bp.route('/api/transaksi/<id_trx>', methods=['GET'])
def get_detail_api(id_trx):
    # 1. Cari transaksi berdasarkan ID
    trx = Transaksi.query.get_or_404(id_trx)
    
    # 2. Ambil rincian item (menggunakan relationship 'details' ke TransaksiDetail)
    items_data = []
    for item in trx.details:
        items_data.append({
            "nama": item.nama_item_snapshot,
            "harga": float(item.harga_satuan_snapshot or 0),
            "qty": item.qty,
            "subtotal": float(item.subtotal_dpp or 0)
        })

    # 3. Kembalikan dalam format JSON
    return jsonify({
        "status": "success",
        "no_struk": trx.no_struk,
        "waktu": trx.waktu_transaksi.strftime('%d-%m-%Y %H:%M') if trx.waktu_transaksi else '-',
        "items": items_data,
        "total_dpp": float(trx.total_dpp or 0),
        "total_pbjt": float(trx.total_pbjt or 0)
    })    
    
@api_bp.route('/transaksi/void', methods=['POST'])
def api_void_transaksi():
    data = request.get_json()
    
    trx_id = data.get('transaksi_id')
    void_by_id = data.get('void_by_id')
    void_reason = data.get('void_reason')

    # 1. Validasi Input
    if not trx_id or not void_by_id or not void_reason:
        return jsonify({
            'success': False, 
            'message': 'Data tidak lengkap (transaksi_id, void_by_id, void_reason wajib diisi)'
        }), 400

    try:
        # 2. Cari Transaksi
        trx = Transaksi.query.get(trx_id)
        if not trx:
            return jsonify({'success': False, 'message': 'Transaksi tidak ditemukan'}), 404

        # Cegah double void
        if getattr(trx, 'is_void', False):
            return jsonify({'success': False, 'message': 'Transaksi ini sudah dibatalkan sebelumnya'}), 400

        # ---> TAMBAHAN LOGIKA BATAS WAKTU 1 JAM <---
        # Catatan: Jika server Anda menggunakan zona waktu lokal, gunakan datetime.now()
        # Jika server Anda menyimpan waktu dalam UTC, gunakan datetime.utcnow()
        waktu_sekarang = datetime.now() 
        selisih_waktu = waktu_sekarang - trx.waktu_transaksi
        
        # Jika selisih lebih dari 1 jam (3600 detik)
        if selisih_waktu > timedelta(hours=1):
            return jsonify({
                'success': False, 
                'message': 'Batas waktu habis! Void hanya dapat dilakukan maksimal 1 jam setelah transaksi.'
            }), 400
        # --------------------------------------------
        # 3. Update Header Transaksi
        trx.is_void = True
        trx.void_at = datetime.utcnow()
        # Handle konversi ke UUID agar tidak error di PostgreSQL
        try:
            trx.void_by_id = uuid.UUID(void_by_id)
        except ValueError:
            trx.void_by_id = None
            
        trx.void_reason = void_reason

        # 4. Update Detail Transaksi & Kembalikan Stok (Inventory Reversal)
        for detail in trx.details:
            detail.is_void = True
            detail.void_at = trx.void_at
            detail.void_by_id = trx.void_by_id
            detail.void_reason = void_reason

            # Kembalikan stok jika menu di-track stoknya
            if detail.menu_id:
                menu_db = Menu.query.get(detail.menu_id)
                if menu_db and getattr(menu_db, 'is_track_stock', False):
                    menu_db.stok = menu_db.stok + detail.qty

        # 5. Simpan Perubahan ke PostgreSQL
        db.session.commit()

        return jsonify({
            'success': True, 
            'message': f'Transaksi {trx.no_struk} berhasil dibatalkan (Void).'
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"DEBUG ERROR VOID TRANSAKSI: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Terjadi kesalahan internal: {str(e)}'
        }), 500
        
@api_bp.route('/cek-versi', methods=['GET'])
def cek_versi_aplikasi():
    try:
        # Nilai ini (version_code) harus dicocokkan dengan angka 'version' di file pubspec.yaml Flutter Anda
        # Misalnya di pubspec.yaml tertulis version: 1.0.0+2, maka version_code nya adalah 2.
        versi_terbaru_code = 1
        versi_terbaru_name = "1.0.1"
        link_download = "https://patra.bpkpdmjktpro.sbs/static/download/pos-terbaru.apk" # Ganti dengan link APK/PlayStore Anda
        wajib_update = True
        catatan_rilis = "Perbaikan sinkronisasi dan penambahan fitur void transaksi."

        return jsonify({
            'status': 'success',
            'data': {
                'latest_version_code': versi_terbaru_code,
                'latest_version_name': versi_terbaru_name,
                'download_url': link_download,
                'force_update': wajib_update,
                'release_notes': catatan_rilis
            }
        }), 200

    except Exception as e:
        print(f"DEBUG ERROR CEK VERSI: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Terjadi kesalahan internal: {str(e)}'
        }), 500        
        

# CETAK STRUK ONLINE
@api_bp.route('/struk/<id_trx>', methods=['GET'])
def web_struk(id_trx):
    # 1. Cari data transaksi
    trx = Transaksi.query.filter_by(id=id_trx).first()
    
    if not trx:
        return "<h3>Struk tidak ditemukan atau belum tersinkronisasi ke server.</h3>", 404

    # 2. Ambil data Wajib Pajak (Toko)
    wp = WajibPajak.query.get(trx.wp_id)
    nama_toko = wp.nama_usaha if wp else "Nama Toko"
    alamat_toko = wp.alamat if wp else "Alamat Toko"

    # 3. HTML & CSS Desain E-Receipt Modern
    html_struk = """
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>E-Receipt | {{ trx.no_struk }}</title>
        <!-- Menggunakan Google Fonts untuk tampilan modern -->
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            body { 
                font-family: 'Plus Jakarta Sans', sans-serif; 
                background-color: #f3f4f6; /* Abu-abu terang */
                margin: 0; 
                padding: 20px; 
                color: #1f2937;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }
            .receipt-card { 
                background: #ffffff; 
                width: 100%; 
                max-width: 380px; 
                border-radius: 16px; 
                box-shadow: 0 10px 25px rgba(0,0,0,0.05); 
                overflow: hidden;
            }
            .receipt-header {
                text-align: center;
                padding: 24px 20px 16px;
                border-bottom: 2px dashed #e5e7eb;
            }
            .icon-check {
                width: 50px;
                height: 50px;
                background-color: #10b981; /* Hijau sukses */
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 12px;
            }
            .icon-check svg {
                width: 28px;
                height: 28px;
                color: white;
            }
            .shop-name {
                font-size: 20px;
                font-weight: 700;
                margin: 0 0 4px;
                color: #111827;
            }
            .shop-address {
                font-size: 13px;
                color: #6b7280;
                margin: 0;
                line-height: 1.4;
            }
            .receipt-body {
                padding: 20px;
            }
            .info-row {
                display: flex;
                justify-content: space-between;
                font-size: 13px;
                margin-bottom: 10px;
                color: #4b5563;
            }
            .info-value {
                font-weight: 600;
                color: #111827;
                text-align: right;
            }
            .divider { 
                border-bottom: 2px dashed #e5e7eb; 
                margin: 16px 0; 
            }
            table { 
                width: 100%; 
                border-collapse: collapse; 
            }
            .item-name {
                font-size: 14px;
                font-weight: 600;
                color: #374151;
                padding-bottom: 4px;
            }
            .item-details {
                font-size: 13px;
                color: #6b7280;
                padding-bottom: 12px;
            }
            .item-total {
                font-size: 14px;
                font-weight: 600;
                color: #111827;
                text-align: right;
                padding-bottom: 12px;
            }
            .summary-row {
                display: flex;
                justify-content: space-between;
                font-size: 14px;
                margin-bottom: 8px;
                color: #4b5563;
            }
            .grand-total {
                background-color: #f0fdfa; /* Teal super muda */
                border-radius: 10px;
                padding: 16px;
                margin-top: 16px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border: 1px solid #ccfbf1;
            }
            .grand-total-label {
                font-size: 15px;
                font-weight: 700;
                color: #0f172a;
            }
            .grand-total-value {
                font-size: 20px;
                font-weight: 700;
                color: #0f766e; /* Teal menyesuaikan tombol Flutter */
            }
            .receipt-footer {
                text-align: center;
                padding: 20px;
                background-color: #f8fafc;
                font-size: 13px;
                color: #64748b;
                border-top: 2px dashed #e5e7eb;
            }
        </style>
    </head>
    <body>
        <div class="receipt-card">
            <!-- HEADER: Logo Centang & Info Toko -->
            <div class="receipt-header">
                <div class="icon-check">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path>
                    </svg>
                </div>
                <h2 class="shop-name">{{ nama_toko }}</h2>
                <p class="shop-address">{{ alamat_toko }}</p>
            </div>
            
            <!-- BODY: Detail Transaksi -->
            <div class="receipt-body">
                <div class="info-row">
                    <span>No. Struk</span>
                    <span class="info-value">{{ trx.no_struk }}</span>
                </div>
                <div class="info-row">
                    <span>Waktu</span>
                    <span class="info-value">{{ trx.waktu_transaksi.strftime('%d %b %Y, %H:%M') }}</span>
                </div>
                <div class="info-row">
                    <span>Pembayaran</span>
                    <span class="info-value">{{ trx.metode_pembayaran }}</span>
                </div>
                
                <div class="divider"></div>
                
                <!-- Rincian Pesanan -->
                <table>
                    {% for item in trx.details %}
                    <tr>
                        <td colspan="2" class="item-name">{{ item.nama_item_snapshot }}</td>
                    </tr>
                    <tr>
                        <td class="item-details">{{ item.qty }} x Rp {{ "{:,.0f}".format(item.harga_satuan_snapshot).replace(',', '.') }}</td>
                        <td class="item-total">Rp {{ "{:,.0f}".format(item.total_harga).replace(',', '.') }}</td>
                    </tr>
                    {% endfor %}
                </table>
                
                <div class="divider"></div>
                
                <!-- Rincian Pajak & Total -->
                <div class="summary-row">
                    <span>Total DPP</span>
                    <span>Rp {{ "{:,.0f}".format(trx.total_dpp).replace(',', '.') }}</span>
                </div>
                {% if trx.total_diskon > 0 %}
                <div class="summary-row">
                    <span>Total Diskon</span>
                    <span style="color: #ef4444;">- Rp {{ "{:,.0f}".format(trx.total_diskon).replace(',', '.') }}</span>
                </div>
                {% endif %}
                <div class="summary-row">
                    <span>PBJT (10%)</span>
                    <span>Rp {{ "{:,.0f}".format(trx.total_pbjt).replace(',', '.') }}</span>
                </div>
                
                <!-- Kotak Grand Total -->
                <div class="grand-total">
                    <span class="grand-total-label">Total Tagihan</span>
                    <span class="grand-total-value">Rp {{ "{:,.0f}".format(trx.grand_total).replace(',', '.') }}</span>
                </div>
            </div>
            
            <!-- FOOTER -->
            <div class="receipt-footer">
                <strong>Terima kasih atas kunjungan Anda!</strong><br>
                <span style="font-size: 11px; opacity: 0.8; margin-top: 6px; display: block;">Simpan struk ini sebagai bukti pembayaran yang sah. Anda dapat melakukan tangkapan layar (screenshot).</span>
            </div>
        </div>
    </body>
    </html>
    """
    
    return render_template_string(html_struk, trx=trx, nama_toko=nama_toko, alamat_toko=alamat_toko)