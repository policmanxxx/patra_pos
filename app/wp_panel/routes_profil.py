import os
import uuid as uuid_lib # Gunakan alias agar tidak bentrok dengan model
from werkzeug.utils import  secure_filename
from flask_login import login_required, current_user
from flask import current_app, flash,request,render_template,redirect,url_for,jsonify
from . import wp_panel_bp 
from app.extensions import db
from app.models import Transaksi, Menu, WajibPajak,TransaksiDetail
# Pastikan folder upload ada (Bisa diletakkan di __init__.py app Anda)
# UPLOAD_FOLDER = 'app/static/uploads/logos'
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@wp_panel_bp.route('/pengaturan', methods=['GET', 'POST'])
@login_required
def pengaturan_toko():
    if not current_user.wp_id:
        return "Akses Ditolak. Anda bukan pemilik tenant.", 403

    wp = WajibPajak.query.get_or_404(current_user.wp_id)

    if request.method == 'POST':
        nama_usaha_baru = request.form.get('nama_usaha')
        alamat_baru = request.form.get('alamat')

        if not nama_usaha_baru:
            flash("Nama Usaha tidak boleh kosong!", "error")
            return redirect(url_for('wp_panel_bp.pengaturan_toko'))

        wp.nama_usaha = nama_usaha_baru
        wp.alamat = alamat_baru

        upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'logos')
        os.makedirs(upload_path, exist_ok=True)

        # Tangani Upload Logo Utama
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = f"logo_{wp.id}_{uuid_lib.uuid4().hex[:8]}.{ext}"
                    file.save(os.path.join(upload_path, filename))
                    
                    if wp.logo_url and wp.logo_url != 'default_logo.png':
                        old_file = os.path.join(upload_path, wp.logo_url)
                        if os.path.exists(old_file):
                            os.remove(old_file)

                    wp.logo_url = filename
                else:
                    flash("Format file logo utama tidak didukung!", "error")
                    return redirect(url_for('wp_panel_bp.pengaturan_toko'))

        # Tangani Upload Logo Struk (Hitam Putih)
        if 'logo_struk' in request.files:
            file_struk = request.files['logo_struk']
            if file_struk and file_struk.filename != '':
                if allowed_file(file_struk.filename):
                    ext = file_struk.filename.rsplit('.', 1)[1].lower()
                    filename_struk = f"logo_struk_{wp.id}_{uuid_lib.uuid4().hex[:8]}.{ext}"
                    file_struk.save(os.path.join(upload_path, filename_struk))
                    
                    if wp.logo_struk_url:
                        old_file_struk = os.path.join(upload_path, wp.logo_struk_url)
                        if os.path.exists(old_file_struk):
                            os.remove(old_file_struk)

                    wp.logo_struk_url = filename_struk
                else:
                    flash("Format file logo struk tidak didukung!", "error")
                    return redirect(url_for('wp_panel_bp.pengaturan_toko'))

        try:
            db.session.commit()
            flash("Profil toko berhasil diperbarui!", "success")
        except Exception as e:
            db.session.rollback()
            flash("Terjadi kesalahan saat menyimpan data.", "error")

        return redirect(url_for('wp_panel_bp.pengaturan_toko'))

    return render_template('wp_panel/pengaturan.html', wp=wp)