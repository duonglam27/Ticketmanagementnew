import cloudinary
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from urllib.parse import quote
from flask_apscheduler import APScheduler
from .config import Config

scheduler = APScheduler()
db = SQLAlchemy()
login = LoginManager()
migrate = Migrate()


def create_app():
    app = Flask(__name__, template_folder='template')
    app.config.from_object(Config)  # Nạp toàn bộ config ở bước 1

    db.init_app(app)
    login.init_app(app)
    migrate.init_app(app, db)

    # Khởi động Scheduler an toàn
    if not scheduler.running:
        scheduler.init_app(app)
        scheduler.start()

    # CLOUDINARY
    cloudinary.config(
        cloud_name='dtkzgdef1',
        api_key='159519239888648',
        api_secret='DZWRFYAgl22pGGAqsQhxjo-0H30'
    )

    # PAYMENT CONFIG
    app.config['VN_PAY'] = {
        'vnp_TmnCode': 'PMAKVMOW',
        'vnp_HashSecret': 'USYEHCIUSVVCFQYKBQBZSUASXUXRSTCS',
        'vnp_Url': 'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html',
    }

    # app.config['MOMO'] = {
    #     'partner_code': 'MOMO',
    #     'access_key': 'F8B6Eu7sL9gy97h7',
    #     'secret_key': 'K97U9Gv9E9ef968hi98X6o57vr7s366C',
    #     'endpoint': 'https://test-payment.momo.vn/v2/gateway/api/create',
    #     'return_url': 'http://127.0.0.1:5000/momo_return',
    #     'notify_url': 'http://127.0.0.1:5000/momo_notify'
    # }

    # IMPORT ROUTES
    from app.index import init_routes
    from app import models
    init_routes(app)


    return app