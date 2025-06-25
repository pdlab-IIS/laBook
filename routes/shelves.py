from flask import Blueprint, request, jsonify, abort
from db import get_db

bp = Blueprint('shelves', __name__, url_prefix='/shelves')

@bp.route('', methods=['GET'])
def list_shelves():
    db = get_db()
    cursor = db.execute("SELECT * FROM Shelves")
    shelves = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
    return jsonify(shelves)

@bp.route('/<int:shelf_id>', methods=['GET'])
def get_shelf(shelf_id):
    db = get_db()
    cursor = db.execute("SELECT * FROM Shelves WHERE shelf_id = ?", (shelf_id,))
    row = cursor.fetchone()
    if row is None:
        abort(404, description="Shelf not found")
    return jsonify(dict(zip([col[0] for col in cursor.description], row)))

@bp.route('/by_code/<shelf_code>', methods=['GET'])
def get_shelf_id_by_code(shelf_code):
    db = get_db()
    cursor = db.execute("SELECT shelf_id FROM Shelves WHERE shelf_code = ?", (shelf_code,))
    row = cursor.fetchone()
    if row is None:
        abort(404, description="Shelf not found")
    return jsonify({"shelf_code": shelf_code, "shelf_id": row[0]})

@bp.route('', methods=['POST'])
def add_shelf():
    data = request.get_json()
    if 'shelf_code' not in data:
        abort(400, description="Missing required fields")
    db = get_db()
    cursor = db.execute("SELECT 1 FROM Shelves WHERE shelf_code = ?", (data['shelf_code'],))
    if cursor.fetchone():
        abort(409, description="Shelf code already exists")
    print(data)
    db.execute(
        "INSERT INTO Shelves (shelf_code, location_description) VALUES (?, ?)",
        (data['shelf_code'],  data.get('location_description'))
    )
    db.commit()
    cursor = db.execute("SELECT shelf_id FROM Shelves WHERE shelf_code = ?", (data['shelf_code'],))
    row = cursor.fetchone()
    return jsonify({"message": "Shelf added", "shelf_id": row[0]}), 201

@bp.route('/<int:shelf_id>', methods=['PUT'])
def update_shelf(shelf_id):
    data = request.get_json()
    db = get_db()
    cursor = db.execute("SELECT * FROM Shelves WHERE shelf_id = ?", (shelf_id,))
    if cursor.fetchone() is None:
        abort(404, description="Shelf not found")
    db.execute(
        "UPDATE Shelves SET shelf_code=?,  location_description=? WHERE shelf_id=?",
        (data.get('shelf_code'),  data.get('location_description'), shelf_id)
    )
    db.commit()
    return jsonify({"message": "Shelf updated"})

@bp.route('/<int:shelf_id>', methods=['DELETE'])
def delete_shelf(shelf_id):
    db = get_db()
    cursor = db.execute("SELECT * FROM Shelves WHERE shelf_id = ?", (shelf_id,))
    if cursor.fetchone() is None:
        abort(404, description="Shelf not found")
    db.execute("DELETE FROM Shelves WHERE shelf_id = ?", (shelf_id,))
    db.commit()
    return jsonify({"message": "Shelf deleted"})