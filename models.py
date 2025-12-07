from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer
from config import Config


db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    is_limited = db.Column(db.Boolean, default=False)
    stores = db.relationship("Store", backref="owner", lazy=True, cascade="all, delete-orphan")
    snapshots = db.relationship("ProductSnapshot", backref="owner", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def generate_reset_token(self, expires_sec: int = 3600) -> str:
        serializer = URLSafeTimedSerializer(Config.SECRET_KEY)
        return serializer.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_token(token: str, max_age: int = 3600):
        serializer = URLSafeTimedSerializer(Config.SECRET_KEY)
        try:
            data = serializer.loads(token, max_age=max_age)
        except Exception:
            return None
        return User.query.get(data.get('user_id'))


class Store(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    client_id = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class ProductSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    data = db.Column(db.JSON, nullable=False)
    store = db.relationship("Store")


class ActionSheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    filename = db.Column(db.String(255), nullable=False)
    data = db.Column(db.JSON, nullable=False)
    store = db.relationship("Store")
