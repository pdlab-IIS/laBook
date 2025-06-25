from .books import bp as books_bp
from .shelves import bp as shelves_bp
from .users import bp as users_bp
from .loans import bp as loans_bp

def register_blueprints(app):
    app.register_blueprint(books_bp)
    app.register_blueprint(shelves_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(loans_bp)