import os
from werkzeug.utils import secure_filename
from . import admin_bp  # Import blueprint dari file utama
from flask import Blueprint, render_template, request, redirect, url_for, current_app
from app.extensions import db
from app.models import Transaksi, WajibPajak, Menu
from sqlalchemy import func
from flask_login import login_required


    
@admin_bp.route('/menu', methods=['GET', 'POST'])
@login_required
def kelola_menu():
    # JIKA ADMIN MENEKAN TOMBOL SIMPAN (POST)
    if request.method == 'POST':
        wp_id = request.form.get('wp_id')
        nama_menu = request.form.get('nama_menu')
        harga_dasar = request.form.get('harga_dasar')
        foto_file = request.files.get('foto') # Menangkap file gambar

        nama_file_foto = None
        
        # Proses jika ada file foto yang diunggah
        if foto_file and foto_file.filename != '':
            # Mengamankan nama file (misal: "Nasi Goreng!.jpg" jadi "Nasi_Goreng.jpg")
            nama_file_foto = secure_filename(foto_file.filename)
            
            # Menentukan jalur penyimpanan: app/static/uploads/menu/
            jalur_simpan = os.path.join(current_app.root_path, 'static', 'uploads', 'menu', nama_file_foto)
            
            # Menyimpan file fisik ke dalam folder
            foto_file.save(jalur_simpan)

        # Menyimpan data teks & nama file ke PostgreSQL
        menu_baru = Menu(
            wp_id=wp_id,
            nama_menu=nama_menu,
            harga_dasar=harga_dasar,
            foto_url=nama_file_foto # Hanya simpan nama filenya saja
        )
        db.session.add(menu_baru)
        db.session.commit()
        
        # Setelah simpan, refresh halaman
        return redirect(url_for('admin_bp.kelola_menu'))

    # JIKA ADMIN HANYA MEMBUKA HALAMAN (GET)
    # Kita tarik data Wajib Pajak untuk pilihan dropdown, dan data Menu untuk tabel
    daftar_wp = WajibPajak.query.all()
    
    # Gunakan JOIN agar kita bisa menampilkan nama restoran di tabel menu
    daftar_menu = db.session.query(Menu, WajibPajak.nama_usaha)\
        .join(WajibPajak, Menu.wp_id == WajibPajak.id)\
        .order_by(Menu.nama_menu.asc()).all()

    return render_template('admin_bpkpd/menu.html', wps=daftar_wp, menus=daftar_menu)    