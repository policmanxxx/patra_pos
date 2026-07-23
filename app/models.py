import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from .extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------------------------------------------------------
# 1. SKEMA MASTER (TENANT & AKSES)
# -------------------------------------------------------------------

class WajibPajak(db.Model):
    __tablename__ = 'wajib_pajak'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    npwpd = db.Column(db.String(50), unique=True, nullable=False)
    nama_usaha = db.Column(db.String(150), nullable=False)
    alamat = db.Column(db.Text)
    kode_kecamatan = db.Column(db.String(5))
    kode_kelurahan = db.Column(db.String(5))
    tarif_pbjt = db.Column(db.Numeric(5, 2), default=10.00)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Logo Utama (Berwarna, untuk panel/UI)
    logo_url = db.Column(db.String(255), nullable=True, default='default_logo.png')
    
    # Logo Struk (Tambahan Baru: Hitam Putih, ukuran kecil untuk thermal)
    logo_struk_url = db.Column(db.String(255), nullable=True) 

    users = db.relationship('User', backref='wajib_pajak', lazy=True, cascade="all, delete-orphan")
    menus = db.relationship('Menu', backref='wajib_pajak', lazy=True, cascade="all, delete-orphan")
    transaksis = db.relationship('Transaksi', backref='wajib_pajak', lazy=True)

class User(db.Model, UserMixin): # <-- Tambahkan UserMixin di sini
    __tablename__ = 'users'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Ubah nullable=True agar Admin BPKPD tidak wajib terikat ke satu restoran tertentu
    wp_id = db.Column(UUID(as_uuid=True), db.ForeignKey('wajib_pajak.id'), nullable=True) 
    username = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nama_lengkap = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='kasir') # 'admin' atau 'kasir'
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # <-- Tambahkan method ini untuk verifikasi password saat login
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# -------------------------------------------------------------------
# 2. SKEMA OPERASIONAL (KATALOG & SHIFT)
# -------------------------------------------------------------------

class KategoriMenu(db.Model):
    __tablename__ = 'kategori_menu'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wp_id = db.Column(UUID(as_uuid=True), db.ForeignKey('wajib_pajak.id'), nullable=False)
    nama_kategori = db.Column(db.String(100), nullable=False)
    urutan = db.Column(db.Integer, default=0)

    menus = db.relationship('Menu', backref='kategori', lazy=True)

class Menu(db.Model):
    __tablename__ = 'menu'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wp_id = db.Column(UUID(as_uuid=True), db.ForeignKey('wajib_pajak.id'), nullable=False)
    kategori_id = db.Column(UUID(as_uuid=True), db.ForeignKey('kategori_menu.id'))
    kode_sku = db.Column(db.String(50))
    nama_menu = db.Column(db.String(150), nullable=False)
    harga_dasar = db.Column(db.Numeric(15, 2), nullable=False) # Harga sebelum PBJT
    # --------------------------------
    diskon = db.Column(db.Numeric(15, 2), default=0) # Potongan harga dalam Rupiah
    is_track_stock = db.Column(db.Boolean, default=False) # Aktifkan hitung stok?
    stok = db.Column(db.Integer, default=0) # Jumlah stok saat ini
    # --------------------------------------------
    # --------------------------------
    is_tax_inclusive = db.Column(db.Boolean, default=False) # False = Exclude, True = Include
    # --------------------------------------------
    is_taxable = db.Column(db.Boolean, default=True) # Apakah kena pajak 10%?
    is_active = db.Column(db.Boolean, default=True)
    foto_url = db.Column(db.String(255), nullable=True)
    hpp = db.Column(db.Numeric(15, 2), default=0) # Harga Pokok Penjualan (Modal)
    batas_stok_minimum = db.Column(db.Integer, default=5)

class ShiftKasir(db.Model):
    __tablename__ = 'shift_kasir'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wp_id = db.Column(UUID(as_uuid=True), db.ForeignKey('wajib_pajak.id'), nullable=False)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    waktu_buka = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    waktu_tutup = db.Column(db.DateTime)
    saldo_awal = db.Column(db.Numeric(15, 2), default=0)
    saldo_akhir = db.Column(db.Numeric(15, 2), default=0)
    saldo_awal = db.Column(db.Numeric(15, 2), default=0)
    saldo_sistem = db.Column(db.Numeric(15, 2), default=0) # Saldo awal + Pemasukan Tunai - Pengeluaran
    saldo_aktual = db.Column(db.Numeric(15, 2), default=0) # Uang fisik yang dihitung kasir saat tutup
    catatan_selisih = db.Column(db.Text, nullable=True)

# -------------------------------------------------------------------
# 3. SKEMA TRANSAKSI (PESANAN & PAJAK)
# -------------------------------------------------------------------

class Transaksi(db.Model):
    __tablename__ = 'transaksi'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wp_id = db.Column(UUID(as_uuid=True), db.ForeignKey('wajib_pajak.id'), nullable=False)
    shift_id = db.Column(UUID(as_uuid=True), db.ForeignKey('shift_kasir.id'))
    kasir_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'))
    
    no_struk = db.Column(db.String(50), nullable=False)
    waktu_transaksi = db.Column(db.DateTime, default=datetime.utcnow)
    no_meja = db.Column(db.String(50), nullable=True)
    # Komponen Perhitungan Pajak
    total_dpp = db.Column(db.Numeric(15, 2), nullable=False, default=0)    # Dasar Pengenaan Pajak
    total_diskon = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    total_pbjt = db.Column(db.Numeric(15, 2), nullable=False, default=0)   # Nilai Pajak 10%
    grand_total = db.Column(db.Numeric(15, 2), nullable=False, default=0)  # Total Bayar Pembeli
    
    metode_pembayaran = db.Column(db.String(50), default='Tunai')
    status = db.Column(db.String(20), default='Selesai')
    
    # Flag Integrasi BPKPD
    is_reported = db.Column(db.Boolean, default=False) 
    
    details = db.relationship('TransaksiDetail', backref='transaksi', lazy=True, cascade="all, delete-orphan")

class TransaksiDetail(db.Model):
    __tablename__ = 'transaksi_detail'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaksi_id = db.Column(UUID(as_uuid=True), db.ForeignKey('transaksi.id'), nullable=False)
    menu_id = db.Column(UUID(as_uuid=True), db.ForeignKey('menu.id'))
    
    # Snapshot untuk mencegah perubahan data historis jika menu diubah
    nama_item_snapshot = db.Column(db.String(150), nullable=False)
    harga_satuan_snapshot = db.Column(db.Numeric(15, 2), nullable=False)
    hpp_snapshot = db.Column(db.Numeric(15, 2), default=0)
    hpp_snapshot = db.Column(db.Numeric(15, 2), default=0)
    
    qty = db.Column(db.Integer, nullable=False, default=1)
    subtotal_dpp = db.Column(db.Numeric(15, 2), nullable=False)
    subtotal_pajak = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    total_harga = db.Column(db.Numeric(15, 2), nullable=False)