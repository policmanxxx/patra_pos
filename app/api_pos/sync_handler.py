from app.extensions import db
from app.models import WajibPajak, Transaksi, TransaksiDetail, Menu
from decimal import Decimal
import logging

def process_bulk_transactions(payload):
    try:
        wp_id = payload.get('wp_id')
        transaksi_list = payload.get('transaksi', [])

        if not wp_id or not transaksi_list:
            return {"status": "error", "pesan": "Payload tidak lengkap (butuh wp_id dan array transaksi)"}, 400

        wp = WajibPajak.query.get(wp_id)
        if not wp:
            return {"status": "error", "pesan": "ID Wajib Pajak tidak ditemukan"}, 404

        tarif_pajak = wp.tarif_pbjt / Decimal('100.0')
        berhasil = 0
        dilewati = 0

        for trx_data in transaksi_list:
            no_struk = trx_data.get('no_struk')
            
            # 1. CEK IDEMPOTENSI & STATUS OPEN BILL
            existing_trx = Transaksi.query.filter_by(wp_id=wp_id, no_struk=no_struk).first()
            is_update_open_bill = False
            
            if existing_trx:
                if existing_trx.status == 'Belum Bayar':
                    # Ini adalah Open Bill dari Waiter yang mau dibayar!
                    is_update_open_bill = True
                    baru_trx = existing_trx
                    
                    # Hapus rincian barang lama (karena akan ditimpa dengan jumlah/hitungan kasir yang valid)
                    for old_detail in baru_trx.details:
                        db.session.delete(old_detail)
                else:
                    # Jika statusnya Selesai, berarti ini benar-benar data duplikat (Internet kasir lag)
                    dilewati += 1
                    continue 

            total_diskon = Decimal(str(trx_data.get('total_diskon', 0)))

            # 2. PROSES HEADER (Buat Baru ATAU Timpa yang Lama)
            if is_update_open_bill:
                # Update header Open Bill menjadi Lunas
                baru_trx.waktu_transaksi = trx_data.get('waktu_transaksi')
                baru_trx.total_diskon = total_diskon
                baru_trx.metode_pembayaran = trx_data.get('metode_pembayaran', 'Tunai')
                baru_trx.status = 'Selesai'
                baru_trx.no_meja = trx_data.get('no_meja', baru_trx.no_meja)
            else:
                # Buat Header Transaksi murni baru (Kasus kasir fast-food biasa)
                baru_trx = Transaksi(
                    wp_id=wp_id,
                    no_struk=no_struk,
                    waktu_transaksi=trx_data.get('waktu_transaksi'),
                    no_meja=trx_data.get('no_meja', ''),
                    total_dpp=Decimal('0'),
                    total_diskon=total_diskon,
                    total_pbjt=Decimal('0'),
                    grand_total=Decimal('0'),
                    metode_pembayaran=trx_data.get('metode_pembayaran', 'Tunai'),
                    status='Selesai',
                    is_reported=False
                )
                db.session.add(baru_trx)
            
            db.session.flush()

            kalkulasi_dpp = Decimal('0')
            kalkulasi_pbjt = Decimal('0')
            kalkulasi_grand_total = Decimal('0')

            # 3. PROSES RINCIAN BARANG (Logika Matematikanya Tetap Sama)
            for item in trx_data.get('items', []):
                qty = Decimal(str(item.get('qty', 1)))
                harga_input = Decimal(str(item.get('harga_satuan', 0)))
                
                menu_id = item.get('menu_id')
                menu_db = Menu.query.get(menu_id) if menu_id else None
                
                diskon_item = Decimal('0')
                is_taxable = True
                is_tax_inclusive = False
                
                if menu_db:
                    diskon_item = menu_db.diskon or Decimal('0')
                    is_taxable = menu_db.is_taxable
                    is_tax_inclusive = menu_db.is_tax_inclusive
                    
                    if menu_db.is_track_stock:
                        menu_db.stok = menu_db.stok - int(qty)

                harga_bersih = harga_input - diskon_item
                total_baris = harga_bersih * qty
                
                subtotal_dpp = Decimal('0')
                subtotal_pajak = Decimal('0')
                total_harga = Decimal('0')
                
                if is_taxable:
                    if is_tax_inclusive:
                        total_harga = total_baris
                        subtotal_dpp = total_harga / (Decimal('1') + tarif_pajak)
                        subtotal_pajak = total_harga - subtotal_dpp
                    else:
                        subtotal_dpp = total_baris
                        subtotal_pajak = subtotal_dpp * tarif_pajak
                        total_harga = subtotal_dpp + subtotal_pajak
                else:
                    subtotal_dpp = total_baris
                    subtotal_pajak = Decimal('0')
                    total_harga = total_baris

                kalkulasi_dpp += subtotal_dpp
                kalkulasi_pbjt += subtotal_pajak
                kalkulasi_grand_total += total_harga

                detail = TransaksiDetail(
                    transaksi_id=baru_trx.id,
                    menu_id=menu_id,
                    nama_item_snapshot=item.get('nama_item'),
                    harga_satuan_snapshot=harga_input, 
                    qty=int(qty),
                    subtotal_dpp=subtotal_dpp,
                    subtotal_pajak=subtotal_pajak,
                    total_harga=total_harga
                )
                db.session.add(detail)
                
            # 4. KUNCI TOTAL PRESISI KE HEADER
            baru_trx.total_dpp = kalkulasi_dpp
            baru_trx.total_pbjt = kalkulasi_pbjt
            baru_trx.grand_total = kalkulasi_grand_total
            
            berhasil += 1

        db.session.commit()
        
        return {
            "status": "sukses", 
            "pesan": "Sinkronisasi selesai.",
            "data": {
                "tersimpan": berhasil,
                "duplikat_dilewati": dilewati
            }
        }, 200

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error sinkronisasi: {str(e)}")
        return {"status": "error", "pesan": "Terjadi kesalahan internal server."}, 500