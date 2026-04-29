setting .env

pip install -r requirements.txt

flask --app wsgi run# Ticketmanagementnew

flask db init
flask db migrate -m "init tables"
flask db upgrade