from flask import Blueprint, render_template, redirect, url_for, request, current_app, flash, jsonify
from . import wp_panel_bp 
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Transaksi, Menu, WajibPajak, KategoriMenu # Pastikan KategoriMenu di-import
from sqlalchemy import func
import os
from werkzeug.utils import secure_filename

@wp_panel_bp.route('/menu', methods=['GET', 'POST'])
@login_required
def kelola_menu():
    if not current_user.wp_id:
        return "Akses Ditolak", 403

    if request.method == 'POST':
        nama_menu = request.form.get('nama_menu')
        kategori_id = request.form.get('kategori_id') or None
        harga_dasar = request.form.get('harga_dasar')
        diskon = request.form.get('diskon', 0)
        
        # Tangkap nilai is_tax_inclusive (1 = True, 0 = False)
        is_tax_inclusive = True if request.form.get('is_tax_inclusive') == '1' else False
        
        is_track_stock = True if request.form.get('is_track_stock') else False
        stok = request.form.get('stok', 0)
        
        foto_file = request.files.get('foto')
        nama_file_foto = None
        
        if foto_file and foto_file.filename != '':
            nama_file_foto = secure_filename(foto_file.filename)
            jalur_simpan = os.path.join(current_app.root_path, 'static', 'uploads', 'menu', nama_file_foto)
            foto_file.save(jalur_simpan)

        # Simpan nilai baru ke DB
        menu_baru = Menu(
            wp_id=current_user.wp_id, 
            kategori_id=kategori_id,
            nama_menu=nama_menu,
            harga_dasar=harga_dasar,
            diskon=diskon,
            is_tax_inclusive=is_tax_inclusive, # <--- Ambil data baru
            is_track_stock=is_track_stock,
            stok=stok if is_track_stock else 0,
            foto_url=nama_file_foto
        )
        db.session.add(menu_baru)
        db.session.commit()
        
        flash('Menu baru berhasil ditambahkan!', 'success')
        return redirect(url_for('wp_panel_bp.kelola_menu'))

    daftar_menu = Menu.query.filter_by(wp_id=current_user.wp_id).order_by(Menu.nama_menu.asc()).all()
    daftar_kategori = KategoriMenu.query.filter_by(wp_id=current_user.wp_id).order_by(KategoriMenu.nama_kategori.asc()).all()
    return render_template('wp_panel/menu.html', menus=daftar_menu, kategoris=daftar_kategori)

# Endpoint AJAX untuk tambah kategori via Modal
@wp_panel_bp.route('/api/kategori/tambah', methods=['POST'])
@login_required
def api_tambah_kategori():
    data = request.get_json()
    nama_kategori = data.get('nama_kategori')
    
    if not nama_kategori:
        return jsonify({'status': 'error', 'message': 'Nama kategori tidak boleh kosong'}), 400
        
    kategori_baru = KategoriMenu(
        wp_id=current_user.wp_id,
        nama_kategori=nama_kategori
    )
    db.session.add(kategori_baru)
    db.session.commit()
    
    return jsonify({
        'status': 'success', 
        'id': str(kategori_baru.id), 
        'nama_kategori': kategori_baru.nama_kategori
    })

@wp_panel_bp.route('/menu/hapus/<id>', methods=['POST'])
@login_required
def hapus_menu(id):
    menu = Menu.query.get_or_404(id)
    
    # PROTEKSI GANDA: Pastikan menu yang dihapus benar-benar milik resto ini
    if menu.wp_id != str(current_user.wp_id):
        return "Akses Ditolak", 403
        
    db.session.delete(menu)
    db.session.commit()
    
    flash('Menu berhasil dihapus!', 'success')
    return redirect(url_for('wp_panel_bp.kelola_menu'))

@wp_panel_bp.route('/menu/edit/<id>', methods=['POST'])
@login_required
def edit_menu(id):
    menu = Menu.query.get_or_404(id)
    if str(menu.wp_id) != str(current_user.wp_id):
        return "Akses Ditolak", 403

    try:
        menu.nama_menu = request.form.get('nama_menu')
        kategori_id = request.form.get('kategori_id')
        menu.kategori_id = kategori_id if kategori_id else None
        menu.harga_dasar = request.form.get('harga_dasar')
        menu.diskon = request.form.get('diskon', 0)
        
        # Update nilai is_tax_inclusive saat edit data
        menu.is_tax_inclusive = True if request.form.get('is_tax_inclusive') == '1' else False
        
        is_track_stock = True if request.form.get('is_track_stock') else False
        menu.is_track_stock = is_track_stock
        menu.stok = request.form.get('stok', 0) if is_track_stock else 0

        foto_file = request.files.get('foto')
        if foto_file and foto_file.filename != '':
            nama_file_foto = secure_filename(foto_file.filename)
            jalur_simpan = os.path.join(current_app.root_path, 'static', 'uploads', 'menu', nama_file_foto)
            foto_file.save(jalur_simpan)
            menu.foto_url = nama_file_foto

        db.session.commit()
        flash('Data menu berhasil diperbarui!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal memperbarui menu: {str(e)}', 'error')

    return redirect(url_for('wp_panel_bp.kelola_menu'))