from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


@dataclass(frozen=True)
class Name:
    first: str
    last: str

    def __composite_values__(self):
        return self.first, self.last


@dataclass(frozen=True)
class Address:
    street: str
    city: str
    locality: str
    state: str
    pincode: str

    def __composite_values__(self):
        return self.street, self.city, self.locality, self.state, self.pincode


class PMSUser(UserMixin, db.Model):
    __tablename__ = "pms_user"

    user_id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

    first_name = db.Column(db.String(60), nullable=False)
    last_name = db.Column(db.String(60), nullable=False)
    name = db.composite(Name, first_name, last_name)

    __mapper_args__ = {
        "polymorphic_on": type,
        "polymorphic_identity": "user",
    }

    def get_id(self) -> str:
        return str(self.user_id)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Patient(PMSUser):
    __tablename__ = "patient"

    user_id = db.Column(db.Integer, db.ForeignKey("pms_user.user_id"), primary_key=True)
    dob = db.Column(db.Date, nullable=False)
    phone_no = db.Column(db.String(20), nullable=False)

    street = db.Column(db.String(150), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    locality = db.Column(db.String(80), nullable=False)
    state = db.Column(db.String(80), nullable=False)
    pincode = db.Column(db.String(12), nullable=False)
    address = db.composite(Address, street, city, locality, state, pincode)

    diagnoses = db.relationship("Diagnosis", back_populates="patient", cascade="all, delete-orphan")

    __mapper_args__ = {
        "polymorphic_identity": "patient",
    }

    @property
    def age(self) -> int:
        today = date.today()
        years = today.year - self.dob.year
        if (today.month, today.day) < (self.dob.month, self.dob.day):
            years -= 1
        return years


class Doctor(PMSUser):
    __tablename__ = "doctor"

    user_id = db.Column(db.Integer, db.ForeignKey("pms_user.user_id"), primary_key=True)
    specialization = db.Column(db.String(120), nullable=False)
    office_phno = db.Column(db.String(20), nullable=False)
    personal_phno = db.Column(db.String(20), nullable=False)
    hospital_name = db.Column(db.String(120), nullable=False)

    diagnoses = db.relationship("Diagnosis", back_populates="doctor", cascade="all, delete-orphan")

    __mapper_args__ = {
        "polymorphic_identity": "doctor",
    }


class Diagnosis(db.Model):
    __tablename__ = "diagnosis"

    diagnosis_id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.user_id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctor.user_id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    summary = db.Column(db.Text, nullable=False)

    patient = db.relationship("Patient", back_populates="diagnoses")
    doctor = db.relationship("Doctor", back_populates="diagnoses")
    prescription = db.relationship(
        "Prescription", back_populates="diagnosis", uselist=False, cascade="all, delete-orphan"
    )


class Prescription(db.Model):
    __tablename__ = "prescription"

    prescription_id = db.Column(db.Integer, primary_key=True)
    diagnosis_id = db.Column(db.Integer, db.ForeignKey("diagnosis.diagnosis_id"), nullable=False, unique=True)

    diagnosis = db.relationship("Diagnosis", back_populates="prescription")
    medicines = db.relationship("Medicine", back_populates="prescription", cascade="all, delete-orphan")


class Medicine(db.Model):
    __tablename__ = "medicine"

    medicine_id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescription.prescription_id"), nullable=False)
    med_name = db.Column(db.String(120), nullable=False)
    dosage = db.Column(db.String(120), nullable=False)
    instructions = db.Column(db.Text, nullable=False)

    prescription = db.relationship("Prescription", back_populates="medicines")
