from flask import Flask, render_template


def create_app():
    app = Flask(__name__)

    from .api import bp as api_bp
    app.register_blueprint(api_bp)

    @app.get('/')
    def index():
        return render_template('index.html')

    return app
