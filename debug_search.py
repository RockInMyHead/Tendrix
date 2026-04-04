
import asyncio
from database import SessionLocal, Tender
from sqlalchemy.orm import Session
from sqlalchemy import or_

def test_search():
    db = SessionLocal()
    
    law_44 = True
    law_223 = False
    region = None
    final_search_string = None
    price_from = None
    price_to = None

    query = db.query(Tender)

    if final_search_string:
        words = final_search_string.split()
        for word in words:
            word = word.strip().replace(',', '').replace(';', '')
            if len(word) < 2: continue
            search_filter = f"%{word}%"
            query = query.filter(
                (Tender.subject.ilike(search_filter)) | 
                (Tender.customer.ilike(search_filter)) |
                (Tender.number.ilike(search_filter))
            )

    # Filter by Law
    if law_44 and not law_223:
        query = query.filter(
            (Tender.procurement_type.ilike("%44-ФЗ%")) | 
            (Tender.procurement_type == None) | 
            (~Tender.procurement_type.ilike("%223-ФЗ%"))
        )
    elif law_223 and not law_44:
        query = query.filter(Tender.procurement_type.ilike("%223-ФЗ%"))
    elif not law_44 and not law_223:
        query = query.filter(Tender.id < 0)

    if price_from is not None:
        query = query.filter(Tender.price >= price_from)
    if price_to is not None:
        query = query.filter(Tender.price <= price_to)
    
    if region:
        query = query.filter(Tender.region.ilike(f"%{region}%"))
        
    count = query.count()
    print(f"Total found: {count}")
    
    if count > 0:
        first = query.first()
        print(f"First item: {first.number}, {first.procurement_type}")

    db.close()

if __name__ == "__main__":
    test_search()
