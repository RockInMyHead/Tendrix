import requests
import json

from database import SessionLocal, Tender
db = SessionLocal()
latest = db.query(Tender).order_by(Tender.id.desc()).limit(5).all()
for t in latest:
    print(f"ID: {t.number}, Subject: {t.subject[:50]}, UpdateDate: {t.update_date}, Region: {t.region}")
db.close()
