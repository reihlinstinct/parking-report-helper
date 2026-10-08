import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from parking_report.api_cli import execute

class CategoryRoutingTests(unittest.TestCase):
    def check(self, category, routing, allowed):
        with TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'report.json').write_text(json.dumps({'violation':{'category':category}}))
            args=argparse.Namespace(submit=True,approved_sha256='digest',approved_category_routing=routing,
                folder=folder,state_dir=folder/'state',retry_photo=False)
            with patch.dict('os.environ',{'PARKING_106_ENABLE_LIVE':'true'}),patch('parking_report.api106.Municipality'),patch('parking_report.api106.submit',return_value={'status':'submitted','photo_attached':True}) as submit:
                if allowed:
                    execute(args,{}, {}, b'', 'digest', None, {'state':{}}, 'id');submit.assert_called_once()
                else:
                    with self.assertRaises(ValueError):execute(args,{}, {}, b'', 'digest', None, {'state':{}}, 'id')
                    submit.assert_not_called()
    def test_default_does_not_widen(self):
        for category in ['crosswalk_parking','blocked_ramp','other']:
            self.check(category,'',False)
    def test_exact_type_override_only(self):
        self.check('crosswalk_parking','crosswalk_parking',True)
        self.check('blocked_ramp','blocked_ramp',True)
        self.check('crosswalk_parking','blocked_ramp',False)
        self.check('other','crosswalk_parking',False)
    def test_sidewalk_default_retained(self):self.check('sidewalk_parking','',True)
