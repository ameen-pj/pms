from __future__ import annotations

from datetime import datetime
from functools import wraps

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, URLSafeSerializer

from models import Diagnosis, Doctor, Medicine, PMSUser, Patient, Prescription, db


app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///pms.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(PMSUser, int(user_id))


def wants_json_response() -> bool:
    return request.args.get("format") == "json" or request.is_json


def get_share_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(app.config["SECRET_KEY"], salt="prescription-share")


def build_prescription_share_token(prescription_id: int) -> str:
    return get_share_serializer().dumps({"prescription_id": prescription_id})


def parse_prescription_share_token(token: str) -> int | None:
    try:
        payload = get_share_serializer().loads(token)
    except BadSignature:
        return None

    prescription_id = payload.get("prescription_id")
    return prescription_id if isinstance(prescription_id, int) else None


def doctor_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.type != "doctor":
            abort(403)
        return view_func(*args, **kwargs)

    return wrapped


def patient_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.type != "patient":
            abort(403)
        return view_func(*args, **kwargs)

    return wrapped


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    prefill = {
        "doctor": ("doctor@pms.local", "doctor123"),
        "patient": ("patient@pms.local", "patient123"),
    }

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = PMSUser.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid email or password", "danger")
        return render_template("login.html", prefill_email=email)

    role = request.args.get("role", "doctor").strip().lower()
    prefill_email, prefill_password = prefill.get(role, prefill["doctor"])
    return render_template("login.html", prefill_email=prefill_email, prefill_password=prefill_password)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        role = request.form.get("role", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        if role not in {"doctor", "patient"}:
            flash("Please select a valid role.", "danger")
            return render_template("register.html")

        if not all([email, password, confirm_password, first_name, last_name]):
            flash("Please fill all required fields.", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        existing_user = PMSUser.query.filter_by(email=email).first()
        if existing_user:
            flash("An account with this email already exists.", "danger")
            return render_template("register.html")

        try:
            if role == "doctor":
                specialization = request.form.get("specialization", "").strip()
                office_phno = request.form.get("office_phno", "").strip()
                personal_phno = request.form.get("personal_phno", "").strip()
                hospital_name = request.form.get("hospital_name", "").strip()

                if not all([specialization, office_phno, personal_phno, hospital_name]):
                    flash("Please complete all doctor fields.", "danger")
                    return render_template("register.html")

                user = Doctor(
                    type="doctor",
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    specialization=specialization,
                    office_phno=office_phno,
                    personal_phno=personal_phno,
                    hospital_name=hospital_name,
                )
            else:
                dob_raw = request.form.get("dob", "").strip()
                phone_no = request.form.get("phone_no", "").strip()
                street = request.form.get("street", "").strip()
                city = request.form.get("city", "").strip()
                locality = request.form.get("locality", "").strip()
                state = request.form.get("state", "").strip()
                pincode = request.form.get("pincode", "").strip()

                if not all([dob_raw, phone_no, street, city, locality, state, pincode]):
                    flash("Please complete all patient fields.", "danger")
                    return render_template("register.html")

                dob = datetime.strptime(dob_raw, "%Y-%m-%d").date()

                user = Patient(
                    type="patient",
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    dob=dob,
                    phone_no=phone_no,
                    street=street,
                    city=city,
                    locality=locality,
                    state=state,
                    pincode=pincode,
                )

            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Registration successful. Please login.", "success")
            return redirect(url_for("login"))
        except ValueError:
            flash("Invalid date format. Use YYYY-MM-DD.", "danger")

    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.type == "doctor":
        doctor_diagnoses = (
            Diagnosis.query.filter_by(doctor_id=current_user.user_id)
            .order_by(Diagnosis.date.desc())
            .limit(10)
            .all()
        )
        return render_template("doctor_dashboard.html", diagnoses=doctor_diagnoses)

    patient_diagnoses = (
        Diagnosis.query.filter_by(patient_id=current_user.user_id)
        .order_by(Diagnosis.date.desc())
        .all()
    )
    return render_template("patient_dashboard.html", diagnoses=patient_diagnoses)


@app.route("/doctor/patient/<int:patientid>")
@login_required
@doctor_required
def search_patient(patientid: int):
    patient = db.session.get(Patient, patientid)
    if not patient:
        abort(404, description="Patient not found")

    if not wants_json_response():
        return render_template("patient_search.html", patient=patient)

    return jsonify(
        {
            "patient_id": patient.user_id,
            "name": f"{patient.first_name} {patient.last_name}",
            "email": patient.email,
            "phone_no": patient.phone_no,
            "dob": patient.dob.isoformat(),
            "age": patient.age,
            "address": {
                "street": patient.street,
                "city": patient.city,
                "locality": patient.locality,
                "state": patient.state,
                "pincode": patient.pincode,
            },
        }
    )


@app.route("/doctor/patient/search", methods=["GET", "POST"])
@login_required
@doctor_required
def search_patient_form():
    patient_id = request.values.get("patient_id", type=int)
    if not patient_id:
        flash("Enter a valid patient ID", "danger")
        return redirect(url_for("dashboard"))
    return redirect(url_for("search_patient", patientid=patient_id))


@app.route("/doctor/diagnosis/create", methods=["POST"])
@login_required
@doctor_required
def create_diagnosis():
    patient_id = request.form.get("patient_id", type=int)
    summary = request.form.get("summary", "").strip()
    date_raw = request.form.get("date", "").strip()

    if not patient_id or not summary:
        abort(400, description="patient_id and summary are required")

    patient = db.session.get(Patient, patient_id)
    if not patient:
        abort(404, description="Patient not found")

    try:
        diagnosis_date = datetime.strptime(date_raw, "%Y-%m-%d").date() if date_raw else datetime.utcnow().date()
    except ValueError:
        flash("Invalid diagnosis date. Use YYYY-MM-DD.", "danger")
        return redirect(url_for("dashboard"))

    diagnosis = Diagnosis(
        patient_id=patient.user_id,
        doctor_id=current_user.user_id,
        summary=summary,
        date=diagnosis_date,
    )
    db.session.add(diagnosis)
    db.session.commit()

    if not wants_json_response():
        flash(f"Diagnosis #{diagnosis.diagnosis_id} created for patient #{patient.user_id}", "success")
        return redirect(url_for("dashboard"))

    return jsonify({"diagnosis_id": diagnosis.diagnosis_id, "message": "Diagnosis created"}), 201


@app.route("/doctor/prescription/add/<int:diagnosis_id>", methods=["POST"])
@login_required
@doctor_required
def add_prescription(diagnosis_id: int):
    diagnosis = db.session.get(Diagnosis, diagnosis_id)
    if not diagnosis:
        abort(404, description="Diagnosis not found")

    if diagnosis.doctor_id != current_user.user_id:
        abort(403, description="You can only prescribe for your own diagnosis records")

    if diagnosis.prescription:
        if not wants_json_response():
            flash("Prescription already exists for this diagnosis.", "warning")
            return redirect(url_for("dashboard"))
        return jsonify({"prescription_id": diagnosis.prescription.prescription_id, "message": "Prescription exists"})

    prescription = Prescription(diagnosis_id=diagnosis_id)
    db.session.add(prescription)
    db.session.commit()

    if not wants_json_response():
        flash(f"Prescription #{prescription.prescription_id} created.", "success")
        return redirect(url_for("dashboard"))

    return jsonify({"prescription_id": prescription.prescription_id, "message": "Prescription created"}), 201


@app.route("/doctor/prescription/<int:prescription_id>/medicine/add", methods=["POST"])
@login_required
@doctor_required
def add_medicine(prescription_id: int):
    prescription = db.session.get(Prescription, prescription_id)
    if not prescription:
        abort(404, description="Prescription not found")

    if prescription.diagnosis.doctor_id != current_user.user_id:
        abort(403, description="You can only add medicines to your own prescriptions")

    med_name = request.form.get("med_name", "").strip()
    dosage = request.form.get("dosage", "").strip()
    instructions = request.form.get("instructions", "").strip()

    if not all([med_name, dosage, instructions]):
        abort(400, description="med_name, dosage and instructions are required")

    medicine = Medicine(
        prescription_id=prescription_id,
        med_name=med_name,
        dosage=dosage,
        instructions=instructions,
    )
    db.session.add(medicine)
    db.session.commit()

    if not wants_json_response():
        flash(f"Medicine '{medicine.med_name}' added to prescription #{prescription_id}.", "success")
        return redirect(url_for("dashboard"))

    return jsonify({"medicine_id": medicine.medicine_id, "message": "Medicine added"}), 201


@app.route("/patient/diagnosis/<int:diagnosis_id>")
@login_required
@patient_required
def view_diagnosis(diagnosis_id: int):
    diagnosis = db.session.get(Diagnosis, diagnosis_id)
    if not diagnosis or diagnosis.patient_id != current_user.user_id:
        abort(404, description="Diagnosis not found")

    share_url = None
    if diagnosis.prescription:
        share_token = build_prescription_share_token(diagnosis.prescription.prescription_id)
        share_url = url_for("shared_prescription", token=share_token, _external=True)

    return render_template("diagnosis.html", diagnosis=diagnosis, share_url=share_url)


@app.route("/shared/prescription/<token>")
def shared_prescription(token: str):
    prescription_id = parse_prescription_share_token(token)
    if not prescription_id:
        abort(404, description="Shared prescription not found")

    prescription = db.session.get(Prescription, prescription_id)
    if not prescription:
        abort(404, description="Shared prescription not found")

    return render_template(
        "shared_prescription.html",
        prescription=prescription,
        diagnosis=prescription.diagnosis,
    )


@app.route("/patient/diagnoses")
@login_required
@patient_required
def view_all_diagnosis():
    diagnoses = (
        Diagnosis.query.filter_by(patient_id=current_user.user_id)
        .order_by(Diagnosis.date.desc())
        .all()
    )

    if not wants_json_response():
        return render_template("diagnosis_list.html", diagnoses=diagnoses)

    return jsonify(
        [
            {
                "diagnosis_id": d.diagnosis_id,
                "date": d.date.isoformat(),
                "doctor": f"Dr. {d.doctor.first_name} {d.doctor.last_name}",
                "summary": d.summary,
            }
            for d in diagnoses
        ]
    )


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=getattr(error, "description", "Bad request")), 400


@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, message=getattr(error, "description", "Forbidden")), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message=getattr(error, "description", "Not found")), 404


@app.cli.command("seed-data")
def seed_data():
    if PMSUser.query.count() > 0:
        return

    doctor = Doctor(
        type="doctor",
        email="doctor@pms.local",
        first_name="Asha",
        last_name="Verma",
        specialization="General Medicine",
        office_phno="011-123456",
        personal_phno="9999999999",
        hospital_name="City Care Hospital",
    )
    doctor.set_password("doctor123")

    patient = Patient(
        type="patient",
        email="patient@pms.local",
        first_name="Ravi",
        last_name="Kumar",
        dob=datetime(1995, 7, 12).date(),
        phone_no="8888888888",
        street="21 MG Road",
        city="Bengaluru",
        locality="Indiranagar",
        state="Karnataka",
        pincode="560038",
    )
    patient.set_password("patient123")

    db.session.add_all([doctor, patient])
    db.session.commit()


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
