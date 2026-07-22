import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from . import admin_bp  # Import blueprint dari file utama
from flask import Blueprint, render_template, request, redirect, url_for, current_app
from app.extensions import db
from app.models import Transaksi, WajibPajak, Menu, User
from sqlalchemy import func
from flask_login import login_required


# --- CRUD USER ---
@admin_bp.route('/user')
@login_required
def kelola_user():
    users = User.query.all()
    wps = WajibPajak.query.all()
    return render_template('admin_bpkpd/user.html', users=users,wps=wps)

@admin_bp.route('/user/tambah', methods=['POST'])
@login_required
def tambah_user():
    user_baru = User(
        username=request.form.get('username'),
        password_hash=generate_password_hash(request.form.get('password')),
        nama_lengkap=request.form.get('nama_lengkap'),
        role=request.form.get('role'),
        wp_id=request.form.get('wp_id') # Bisa dikosongkan jika admin
    )
    db.session.add(user_baru)
    db.session.commit()
    return redirect(url_for('admin_bp.kelola_user'))   