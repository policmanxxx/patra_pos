import csv
from io import StringIO
from flask import Blueprint, render_template, request, Response
from datetime import datetime, timedelta
from sqlalchemy import func, extract
from app.extensions import db
from . import admin_bp 
from app.models import Transaksi, WajibPajak
from flask_login import login_required

# Helper untuk nama bulan
def get_nama_bulan(angka_bulan):
    bulan_dict = {
        1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
        5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
        9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
    }
    return bulan_dict.get(angka_bulan, '')
    
def format_tanggal_indo(date_obj):
    bulan_dict = {
        1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
        5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
        9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
    }
    return f"{date_obj.day} {bulan_dict[date_obj.month]} {date_obj.year}"
    
@admin_bp.route('/laporan/bulanan', methods=['GET'])
@login_required
def laporan_bulanan():
    wib_now = datetime.utcnow() + timedelta(hours=7)
    
    # Ambil filter dari request, default ke bulan dan tahun saat ini
    bulan_filter = request.args.get('bulan', default=wib_now.month, type=int)
    tahun_filter = request.args.get('tahun', default=wib_now.year, type=int)
    is_export = request.args.get('export') == 'csv'

    # Kita gunakan OUTER JOIN agar WP yang transaksinya 0 tetap muncul
    # Syarat join-nya disisipkan filter bulan dan tahun menggunakan func.extract
    query = db.session.query(
        WajibPajak.npwpd,
        WajibPajak.nama_usaha,
        func.count(Transaksi.id).label('total_struk'),
        func.sum(Transaksi.total_dpp).label('total_dpp'),
        func.sum(Transaksi.total_pbjt).label('total_pbjt')
    ).outerjoin(Transaksi, db.and_(
        WajibPajak.id == Transaksi.wp_id,
        func.extract('month', Transaksi.waktu_transaksi + timedelta(hours=7)) == bulan_filter,
        func.extract('year', Transaksi.waktu_transaksi + timedelta(hours=7)) == tahun_filter
    )).filter(WajibPajak.is_active == True) \
      .group_by(WajibPajak.id) \
      .order_by(WajibPajak.nama_usaha)

    laporan_data = query.all()

    # Hitung grand total untuk kartu summary di atas tabel
    grand_total_dpp = sum((row.total_dpp or 0) for row in laporan_data)
    grand_total_pbjt = sum((row.total_pbjt or 0) for row in laporan_data)
    grand_total_struk = sum((row.total_struk or 0) for row in laporan_data)

    # ---------------------------------------------------------
    # FITUR EKSPOR CSV (Hanya dieksekusi jika tombol ekspor ditekan)
    # ---------------------------------------------------------
    if is_export:
        si = StringIO()
        writer = csv.writer(si, delimiter=';') # Pakai titik koma agar rapi saat dibuka Excel versi Indonesia
        
        # Header Excel
        writer.writerow(['Laporan Rekapitulasi PBJT'])
        writer.writerow(['Periode:', f"{get_nama_bulan(bulan_filter)} {tahun_filter}"])
        writer.writerow([]) # Baris kosong
        writer.writerow(['NPWPD', 'Nama Usaha', 'Total Transaksi', 'Total Omzet (DPP)', 'Total Pajak (PBJT 10%)'])
        
        # Isi Data
        for row in laporan_data:
            writer.writerow([
                row.npwpd,
                row.nama_usaha,
                row.total_struk or 0,
                float(row.total_dpp or 0),
                float(row.total_pbjt or 0)
            ])
            
        # Baris Grand Total di bawah tabel Excel
        writer.writerow([])
        writer.writerow(['GRAND TOTAL', '', grand_total_struk, float(grand_total_dpp), float(grand_total_pbjt)])
        
        output = Response(si.getvalue(), mimetype='text/csv')
        output.headers["Content-Disposition"] = f"attachment; filename=Laporan_PBJT_{tahun_filter}_{bulan_filter:02d}.csv"
        return output

    # ---------------------------------------------------------
    # RENDER TEMPLATE HTML (Jika tidak mode ekspor)
    # ---------------------------------------------------------
    return render_template(
        'admin_bpkpd/laporan_bulanan.html',
        laporan_data=laporan_data,
        bulan_terpilih=bulan_filter,
        tahun_terpilih=tahun_filter,
        nama_bulan=get_nama_bulan(bulan_filter),
        grand_total_dpp=grand_total_dpp,
        grand_total_pbjt=grand_total_pbjt
    )
    
@admin_bp.route('/laporan/harian', methods=['GET'])
@login_required
def laporan_harian():
    wib_now = datetime.utcnow() + timedelta(hours=7)
    
    # Ambil filter tanggal dari request (format: YYYY-MM-DD)
    # Default ke hari ini (WIB) jika tidak ada
    tanggal_str = request.args.get('tanggal', default=wib_now.strftime('%Y-%m-%d'))
    try:
        tanggal_filter = datetime.strptime(tanggal_str, '%Y-%m-%d').date()
    except ValueError:
        tanggal_filter = wib_now.date()
        tanggal_str = tanggal_filter.strftime('%Y-%m-%d')
        
    is_export = request.args.get('export') == 'csv'

    # Gunakan func.cast untuk mengambil nilai tanggal (Date) dari waktu_transaksi (DateTime)
    query = db.session.query(
        WajibPajak.npwpd,
        WajibPajak.nama_usaha,
        func.count(Transaksi.id).label('total_struk'),
        func.sum(Transaksi.total_dpp).label('total_dpp'),
        func.sum(Transaksi.total_pbjt).label('total_pbjt')
    ).outerjoin(Transaksi, db.and_(
        WajibPajak.id == Transaksi.wp_id,
        # Sesuaikan timezone ke WIB, lalu cast menjadi DATE
        func.cast(Transaksi.waktu_transaksi + timedelta(hours=7), db.Date) == tanggal_filter
    )).filter(WajibPajak.is_active == True) \
      .group_by(WajibPajak.id) \
      .order_by(WajibPajak.nama_usaha)

    laporan_data = query.all()

    # Hitung grand total untuk kartu summary
    grand_total_dpp = sum((row.total_dpp or 0) for row in laporan_data)
    grand_total_pbjt = sum((row.total_pbjt or 0) for row in laporan_data)
    grand_total_struk = sum((row.total_struk or 0) for row in laporan_data)

    tanggal_format = format_tanggal_indo(tanggal_filter)

    # ---------------------------------------------------------
    # FITUR EKSPOR CSV
    # ---------------------------------------------------------
    if is_export:
        si = StringIO()
        writer = csv.writer(si, delimiter=';') 
        
        writer.writerow(['Laporan Rekapitulasi PBJT Harian'])
        writer.writerow(['Tanggal:', tanggal_format])
        writer.writerow([])
        writer.writerow(['NPWPD', 'Nama Usaha', 'Total Transaksi', 'Total Omzet (DPP)', 'Total Pajak (PBJT 10%)'])
        
        for row in laporan_data:
            writer.writerow([
                row.npwpd,
                row.nama_usaha,
                row.total_struk or 0,
                float(row.total_dpp or 0),
                float(row.total_pbjt or 0)
            ])
            
        writer.writerow([])
        writer.writerow(['GRAND TOTAL', '', grand_total_struk, float(grand_total_dpp), float(grand_total_pbjt)])
        
        output = Response(si.getvalue(), mimetype='text/csv')
        output.headers["Content-Disposition"] = f"attachment; filename=Laporan_PBJT_Harian_{tanggal_str}.csv"
        return output

    # ---------------------------------------------------------
    # RENDER TEMPLATE HTML
    # ---------------------------------------------------------
    return render_template(
        'admin_bpkpd/laporan_harian.html',
        laporan_data=laporan_data,
        tanggal_input=tanggal_str,
        tanggal_format=tanggal_format,
        grand_total_dpp=grand_total_dpp,
        grand_total_pbjt=grand_total_pbjt
    )    