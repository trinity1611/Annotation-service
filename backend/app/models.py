import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON
from backend.app.database import Base

class FHIRBundleRecord(Base):
    __tablename__ = "fhir_bundles"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, index=True)
    patient_name = Column(String, index=True)
    encounter_reason = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    bundle_json = Column(JSON)
