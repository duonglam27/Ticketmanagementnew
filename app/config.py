import pytz
from urllib.parse import quote


class Config:
    SECRET_KEY = "!@#$%^&*dasdafaádasds()"
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:%s@localhost/ticketmanagementdb2904?charset=utf8mb4' % quote(
        'lam27072004Aa')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ORDER_TIMEOUT_MINUTES = 1
    # ĐỔI THÀNH UTC ĐỂ KHỚP VỚI datetime.utcnow() TRONG CODE
    SCHEDULER_TIMEZONE = "UTC"
    SCHEDULER_API_ENABLED = True