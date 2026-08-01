from flask import Flask, render_template, send_from_directory


def create_app():
    app = Flask(__name__)

    from .api import bp as api_bp
    app.register_blueprint(api_bp)

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/sw.js')
    def service_worker():
        # Served from the root so its scope can cover the whole app
        return send_from_directory(app.static_folder, 'sw.js',
                                   mimetype='application/javascript')

    return app
