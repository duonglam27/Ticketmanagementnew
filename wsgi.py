from app import create_app
from app.admin import admin_bp

app = create_app()
app.register_blueprint(admin_bp)

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)