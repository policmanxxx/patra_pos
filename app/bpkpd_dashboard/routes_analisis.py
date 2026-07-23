import json
from flask import request, render_template
from sqlalchemy import func, extract
from flask_login import login_required
from . import admin_bp 
from app.models import Transaksi, WajibPajak
from app.extensions import db

@admin_bp.route('/analisis/jam-sibuk', methods=['GET'])
@login_required
def analisis_jam_sibuk():
    # Ambil parameter pencarian
    wp_id = request.args.get('wp_id')
    hari = request.args.get('hari', type=int) # 0=Minggu, 1=Senin, ..., 6=Sabtu

    # Ambil daftar WP untuk opsi dropdown
    daftar_wp = WajibPajak.query.filter_by(is_active=True).order_by(WajibPajak.nama_usaha).all()

    # Siapkan array kosong untuk 24 jam (00:00 - 23:00)
    jam_labels = [f"{str(i).zfill(2)}:00" for i in range(24)]
    data_transaksi = [0] * 24
    data_omzet = [0] * 24

    wp_terpilih = None
    total_trx_keseluruhan = 0
    total_omzet_keseluruhan = 0

    if wp_id:
        wp_terpilih = WajibPajak.query.get(wp_id)
        
        # FIX 1: Hapus konversi timezone. Gunakan Transaksi.waktu_transaksi secara langsung.
        # Query agregasi data per jam
        query = db.session.query(
            extract('hour', Transaksi.waktu_transaksi).label('jam'),
            func.count(Transaksi.id).label('jumlah_trx'),
            func.sum(Transaksi.grand_total).label('omzet')
        ).filter(Transaksi.wp_id == wp_id)

        # FIX 2: Terapkan juga pada filter hari
        if hari is not None and hari != -1:
            query = query.filter(extract('dow', Transaksi.waktu_transaksi) == hari)

        hasil = query.group_by('jam').all()

        # Mapping hasil query ke dalam array 24 jam
        for row in hasil:
            # Karena extract('hour') bisa mengembalikan None jika tidak ada data (meski secara logika group_by mencegahnya),
            # kita amankan dengan casting.
            if row.jam is not None:
                jam_index = int(row.jam)
                data_transaksi[jam_index] = row.jumlah_trx
                data_omzet[jam_index] = float(row.omzet or 0)
                
                total_trx_keseluruhan += row.jumlah_trx
                total_omzet_keseluruhan += float(row.omzet or 0)

    return render_template(
        'admin_bpkpd/analisis_jam_sibuk.html',
        daftar_wp=daftar_wp,
        wp_id_aktif=wp_id,
        hari_aktif=hari if hari is not None else -1,
        wp_terpilih=wp_terpilih,
        total_trx=total_trx_keseluruhan,
        total_omzet=total_omzet_keseluruhan,
        jam_labels=json.dumps(jam_labels),
        data_transaksi=json.dumps(data_transaksi),
        data_omzet=json.dumps(data_omzet)
    )