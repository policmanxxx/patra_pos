import os
from werkzeug.utils import secure_filename
from . import admin_bp  # Import blueprint dari file utama
from flask import Blueprint, render_template, request, redirect, url_for, current_app
from app.extensions import db
from app.models import Transaksi, WajibPajak, Menu
from sqlalchemy import func
from flask_login import login_required


@admin_bp.route('/wajib-pajak')
@login_required
def kelola_wp():
    wps = WajibPajak.query.all()
    return render_template('admin_bpkpd/wajib_pajak.html', wps=wps)

@admin_bp.route('/wajib-pajak/tambah', methods=['POST'])
@login_required
def tambah_wp():
    new_wp = WajibPajak(
        npwpd=request.form.get('npwpd'),
        nama_usaha=request.form.get('nama_usaha'),
        alamat=request.form.get('alamat')
    )
    db.session.add(new_wp)
    db.session.commit()
    return redirect(url_for('admin_bp.kelola_wp'))   