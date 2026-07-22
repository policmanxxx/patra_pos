from app import create_app
from dotenv import load_dotenv

# Load variabel dari file .env
load_dotenv()

app = create_app()

if __name__ == '__main__':
    # Mode debug ON karena server fisik ada di tangan Anda, sangat memudahkan pelacakan error
    app.run(host='0.0.0.0', port=5000, debug=True)