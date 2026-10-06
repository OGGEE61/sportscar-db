import re

with open("app.py", "r") as f:
    content = f.read()

new_route = """
@app.route("/vehicle/<path:vin>/update_details", methods=["POST"])
def update_vehicle_details(vin):
    conn = get_db()
    try:
        conn.execute('''
            UPDATE vehicles
            SET year = ?, body_type = ?, engine_cc = ?, engine_cyl = ?,
                power_hp = ?, drivetrain = ?, transmission = ?, color_ext = ?,
                color_int = ?, registration_plate = ?, first_registration_date = ?
            WHERE vin = ?
        ''', (
            request.form.get("year", type=int) or None,
            request.form.get("body_type") or None,
            request.form.get("engine_cc", type=int) or None,
            request.form.get("engine_cyl", type=int) or None,
            request.form.get("power_hp", type=int) or None,
            request.form.get("drivetrain") or None,
            request.form.get("transmission") or None,
            request.form.get("color_ext") or None,
            request.form.get("color_int") or None,
            request.form.get("registration_plate") or None,
            request.form.get("first_registration_date") or None,
            vin
        ))
        conn.commit()
    except Exception as e:
        print("Error updating vehicle:", e)
    finally:
        conn.close()
    return redirect(url_for("vehicle_detail", vin=vin))

"""

content = content.replace(
    "@app.route(\"/vehicle/<path:vin>/add_tag\", methods=[\"POST\"])",
    new_route + "@app.route(\"/vehicle/<path:vin>/add_tag\", methods=[\"POST\"])"
)

with open("app.py", "w") as f:
    f.write(content)

