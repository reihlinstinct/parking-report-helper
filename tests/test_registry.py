import unittest
from datetime import date
from parking_report.registry import lookup,VEHICLES
class RegistryTests(unittest.TestCase):
    def test_found_and_expiry(self):
        def fake(resource,field,plate):
            row={field:int(plate)}
            if resource==VEHICLES: row.update(tokef_dt='2026-10-08',tozeret_nm='Example')
            else: row.update({'SUG TAV':1,'TAARICH HAFAKAT TAG':20260101})
            return {'total':1,'records':[row]}
        out=lookup('00-000-00',date(2026,10,8),fake)
        self.assertEqual(out['licence_status'],'valid_on_check_date')
        self.assertEqual(out['disability_status'],'listed_in_dataset')
        self.assertNotIn('misgeret',out['vehicle'])
    def test_absence_remains_unknown(self):
        out=lookup('1234567',date(2026,10,8),lambda *a: {'total':0,'records':[]})
        self.assertEqual(out['licence_status'],'unknown')
        self.assertEqual(out['disability_status'],'unknown')
    def test_errors_remain_unknown(self):
        def fake(*args):raise OSError()
        out=lookup('1234567',date(2026,10,8),fake)
        self.assertEqual(out['vehicle_lookup'],'unverified')
    def test_invalid_plate(self):
        with self.assertRaises(ValueError):lookup('abc',date(2026,10,8))
