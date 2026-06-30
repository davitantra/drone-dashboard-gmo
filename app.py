from flask import Flask, render_template
from database import init_db
from api.boundaries import bp as boundaries_bp
from api.sessions import bp as sessions_bp
from api.map_data import bp as map_bp
from api.export import bp as export_bp

def create_app():
    app = Flask(__name__)
    app.register_blueprint(boundaries_bp, url_prefix="/api/boundaries")
    app.register_blueprint(sessions_bp,   url_prefix="/api/sessions")
    app.register_blueprint(map_bp,        url_prefix="/api/map")
    app.register_blueprint(export_bp,     url_prefix="/api/export")

    @app.route("/")
    def index():
        return render_template("index.html")

    return app

if __name__ == "__main__":
    init_db()
    app = create_app()
    print("Drone Dashboard berjalan di http://0.0.0.0:5000")
    print("Akses dari perangkat lain di WiFi yang sama: http://<IP-laptop>:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
