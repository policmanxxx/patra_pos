from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from app.models import User, WajibPajak, db # Pastikan db di-import
import requests
import uuid
auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Jika sudah login, langsung arahkan ke dashboard yang sesuai
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_bp.index')) # Sesuaikan nama fungsi dashboard admin Anda
        else:
            return redirect(url_for('ui_pos.index')) # Sesuaikan nama fungsi kasir Anda

    # Jika ada pengiriman form login (POST)
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Cari user di database
        user = User.query.filter_by(username=username).first()

        # Verifikasi keberadaan user dan kecocokan password
        if user and user.check_password(password):
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin_bp.index'))
            else:
                return redirect(url_for('ui_pos_bp.halaman_kasir'))
        else:
            flash('Username atau password salah!', 'error')

    # Jika hanya membuka halaman (GET)
    return render_template('auth/login.html')

@auth_bp.route('/api/check_npwpd', methods=['POST'])
def check_npwpd():
    """Proxy API untuk mengecek NPWPD ke SIMPATDA menghindari CORS"""
    data = request.get_json()
    npwpd = data.get('npwpd')
    
    if not npwpd:
        return jsonify({"status": "error", "pesan": "NPWPD tidak boleh kosong."}), 400

    # 1. Cek apakah NPWPD sudah terdaftar di database POS kita
    existing_wp = WajibPajak.query.filter_by(npwpd=npwpd).first()
    if existing_wp:
        return jsonify({"status": "error", "pesan": "NPWPD ini sudah terdaftar di Sistem POS."}), 409

    # 2. Cek ke API SIMPATDA
    try:
        api_url = f"https://esptpd.mojokertokota.go.id/api/check_npwpd?npwpd={npwpd}"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            simpatda_data = response.json()
            
            # Memastikan respon berupa array dan statusnya Valid
            if simpatda_data and isinstance(simpatda_data, list) and len(simpatda_data) > 0:
                wp_info = simpatda_data[0]
                if wp_info.get('Status') == "1" or wp_info.get('pesan') == "Valid":
                    return jsonify({"status": "sukses", "data": wp_info}), 200
            
        return jsonify({"status": "error", "pesan": "NPWPD tidak ditemukan atau tidak valid di SIMPATDA."}), 404
        
    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "pesan": "Gagal terhubung ke server SIMPATDA. Coba lagi nanti."}), 500

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('ui_pos_bp.halaman_kasir'))

    if request.method == 'POST':
        npwpd = request.form.get('npwpd')
        nama_usaha = request.form.get('nama_usaha')
        alamat = request.form.get('alamat')
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Validasi ulang di sisi server (Security Check)
        if WajibPajak.query.filter_by(npwpd=npwpd).first():
            flash('Registrasi gagal. NPWPD sudah terdaftar!', 'error')
            return redirect(url_for('auth_bp.register'))
            
        if User.query.filter_by(username=username).first():
            flash('Username sudah digunakan, silakan pilih yang lain!', 'error')
            return redirect(url_for('auth_bp.register'))

        try:
            # 1. Simpan tabel WajibPajak
            wp_id = str(uuid.uuid4())
            baru_wp = WajibPajak(
                id=wp_id,
                npwpd=npwpd,
                nama_usaha=nama_usaha,
                alamat=alamat,
                tarif_pbjt=10.00, # Set default pajak 10%
                is_active=True
            )
            db.session.add(baru_wp)

            # 2. Simpan tabel User (Kasir/Pemilik)
            user_id = str(uuid.uuid4())
            hashed_password = generate_password_hash(password, method='scrypt')
            
            baru_user = User(
                id=user_id,
                wp_id=wp_id,
                username=username,
                password_hash=hashed_password,
                nama_lengkap=nama_usaha, # Bisa disamakan dengan nama usaha 
                role='kasir',
                is_active=True
            )
            db.session.add(baru_user)
            
            db.session.commit()
            flash('Pendaftaran berhasil! Silakan login dengan akun Anda.', 'success')
            return redirect(url_for('auth_bp.login'))
            
        except Exception as e:
            db.session.rollback()
            flash('Terjadi kesalahan internal server saat menyimpan data.', 'error')
            return redirect(url_for('auth_bp.register'))

    return render_template('auth/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth_bp.login'))