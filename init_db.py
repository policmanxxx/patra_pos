from app import create_app
from app.extensions import db
# Penting: Import models agar SQLAlchemy tahu tabel apa saja yang harus dibuat
from app.models import WajibPajak, User, KategoriMenu, Menu, ShiftKasir, Transaksi, TransaksiDetail

app = create_app()

def build_db():
    # Menjalankan konteks aplikasi Flask
    with app.app_context():
        print("Memulai pembuatan tabel di PostgreSQL...")
        
        # Perintah ajaib untuk membuat semua tabel yang belum ada
        db.create_all()
        
        print("Tabel berhasil dibuat!")
        print("Silakan cek di pgAdmin atau DBeaver untuk memastikan.")

if __name__ == '__main__':
    build_db()