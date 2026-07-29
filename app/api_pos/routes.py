from flask import Blueprint, jsonify, request,current_app
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
                'kasir_id': user.user_id,
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
            'logo_struk_url':wp.logo_struk_url
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