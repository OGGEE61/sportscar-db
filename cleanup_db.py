import db

conn = db.get_db()

# Delete non-S2000 Hondas
res1 = conn.execute("DELETE FROM pending_listings WHERE make='Honda' AND model='S2000' AND raw_title NOT LIKE '%s2000%' AND raw_title NOT LIKE '%s 2000%'")

# Delete non-TRX Rams
res2 = conn.execute("DELETE FROM pending_listings WHERE make='RAM' AND variant='TRX' AND raw_title NOT LIKE '%trx%'")

# Delete 911s/Macans from Caymans
res3 = conn.execute("DELETE FROM pending_listings WHERE make='Porsche' AND model IN ('Cayman', '718') AND (raw_title LIKE '%911%' OR raw_title LIKE '%carrera%' OR raw_title LIKE '%macan%' OR raw_title LIKE '%panamera%' OR raw_title LIKE '%cayenne%' OR raw_title LIKE '%taycan%')")

# Delete Nissan Patrols
res4 = conn.execute("DELETE FROM pending_listings WHERE make='Nissan' AND model='Patrol'")

print("Cleanup done!")
