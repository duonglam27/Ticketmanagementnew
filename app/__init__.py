import cloudinary
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from urllib.parse import quote

db = SQLAlchemy()
login = LoginManager()
migrate = Migrate()

def create_app():
    app = Flask(__name__, template_folder='template')

    # SECRET
    app.secret_key = "!@#$%^&*dasdafaádasds()"

    # DATABASE
    app.config['SQLALCHEMY_DATABASE_URI'] = \
        'mysql+pymysql://root:%s@localhost/ticketmanagementdb2904?charset=utf8mb4' % quote('lam27072004Aa')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # INIT EXTENSIONS
    db.init_app(app)
    login.init_app(app)
    migrate.init_app(app, db)

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

    app.config['MOMO'] = {
        'partner_code': 'MOMO',
        'access_key': 'YOUR_ACCESS_KEY',
        'secret_key': 'YOUR_SECRET_KEY',
        'endpoint': 'https://test-payment.momo.vn/gw_payment/transactionProcessor',
        'return_url': 'http://127.0.0.1:5000/momo_return',
        'notify_url': 'http://127.0.0.1:5000/momo_notify'
    }

    # IMPORT ROUTES
    from app.app import init_routes
    from app import models
    init_routes(app)

    return app