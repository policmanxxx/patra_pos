from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_jwt_extended import JWTManager

jwt = JWTManager()

db = SQLAlchemy()
login_manager = LoginManager()