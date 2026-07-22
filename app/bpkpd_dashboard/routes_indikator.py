from flask import Blueprint, render_template
from datetime import datetime, timedelta
from sqlalchemy import func
from app.extensions import db
from . import admin_bp 
from app.models import Transaksi, WajibPajak
from flask_login import login_required



@admin_bp.route('/kepatuhan/monitoring', methods=['GET'])
@login_required
def monitoring_kepatuhan():
    # Set waktu sekarang di zona WIB
    wib_now = datetime.utcnow() + timedelta(hours=7)

    # 1. Buat Subquery untuk mencari Waktu Transaksi Terakhir tiap WP
    # Menggunakan func.max untuk mendapatkan transaksi paling baru
    subquery_last_trx = db.session.query(
        Transaksi.wp_id,
        func.max(Transaksi.waktu_transaksi).label('waktu_terakhir')
    ).group_by(Transaksi.wp_id).subquery()

    # 2. Main Query: Gabungkan (OUTER JOIN) tabel WajibPajak dengan subquery
    results = db.session.query(
        WajibPajak,
        subquery_last_trx.c.waktu_terakhir
    ).outerjoin(
        subquery_last_trx, WajibPajak.id == subquery_last_trx.c.wp_id
    ).filter(WajibPajak.is_active == True).order_by(WajibPajak.nama_usaha).all()

    # 3. Olah data untuk klasifikasi status dan perhitungan selisih waktu
    monitoring_data = []
    stats = {'online': 0, 'warning': 0, 'offline': 0, 'belum_ada_data': 0}

    for wp, waktu_terakhir_utc in results:
        waktu_str = "-"
        status = "Belum Ada Data"
        keterangan_waktu = "Belum pernah kirim data"

        if waktu_terakhir_utc:
            # Sesuaikan dengan WIB jika data di DB disimpan dalam UTC
            waktu_terakhir_wib = waktu_terakhir_utc + timedelta(hours=7)
            waktu_str = waktu_terakhir_wib.strftime('%d-%m-%Y %H:%M:%S')
            
            # Hitung selisih waktu dari sekarang ke transaksi terakhir
            selisih = wib_now - waktu_terakhir_wib
            
            # Buat keterangan waktu yang human-readable
            if selisih.days > 0:
                keterangan_waktu = f"{selisih.days} hari yang lalu"
            else:
                jam = selisih.seconds // 3600
                menit = (selisih.seconds % 3600) // 60
                if jam > 0:
                    keterangan_waktu = f"{jam} jam {menit} menit yang lalu"
                else:
                    keterangan_waktu = f"{menit} menit yang lalu"

            # Klasifikasi Kepatuhan/Status
            if selisih <= timedelta(hours=24):
                status = "Online"
                stats['online'] += 1
            elif selisih <= timedelta(days=3):
                status = "Warning"
                stats['warning'] += 1
            else:
                status = "Offline"
                stats['offline'] += 1
        else:
            stats['belum_ada_data'] += 1

        monitoring_data.append({
            'wp': wp,
            'waktu_terakhir': waktu_str,
            'keterangan_waktu': keterangan_waktu,
            'status': status
        })

    # Opsional: Urutkan agar yang 'Offline' dan 'Warning' berada di paling atas
    # Definisi urutan: Offline (0), Warning (1), Belum Ada Data (2), Online (3)
    order_dict = {"Offline": 0, "Warning": 1, "Belum Ada Data": 2, "Online": 3}
    monitoring_data.sort(key=lambda x: order_dict[x['status']])

    return render_template(
        'admin_bpkpd/monitoring_kepatuhan.html',
        monitoring_data=monitoring_data,
        stats=stats,
        update_terakhir=wib_now.strftime('%d %B %Y - %H:%M WIB')
    )