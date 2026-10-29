import json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from footprint import FootprintError
from inspect_binary import expected_detectors,parse_compiled_detectors,verify_inventory

class DetectorInspectionTests(unittest.TestCase):
    def test_kubernetes_alias_is_expected_only_when_compiled(self):
        catalog={'ec2':{},'k8s_api':{}}
        self.assertEqual(['ec2','k8s_api','k8snode'],expected_detectors({'kind':'full'},catalog))
        self.assertEqual(['ec2'],expected_detectors({'kind':'single','detectors':['resourcedetection_ec2']},catalog))
        self.assertEqual(['k8s_api','k8snode'],expected_detectors({'kind':'single','detectors':['resourcedetection_k8s_api']},catalog))
    def test_rejects_missing_unexpected_and_duplicate_detectors(self):
        for observed in (None,[],['ec2','gcp']):
            with self.assertRaises(FootprintError):verify_inventory(['ec2'],observed)
        with self.assertRaises(FootprintError):parse_compiled_detectors(json.dumps({'compiled_detectors':['ec2','ec2']}))
    def test_extracts_registry_without_confusing_configured_detectors(self):
        log='not json\n'+json.dumps({'configured_detectors':[],'compiled_detectors':['system','env']})
        self.assertEqual(['env','system'],parse_compiled_detectors(log))
        self.assertIsNone(parse_compiled_detectors(json.dumps({'configured_detectors':['ec2']})))
    def test_rejects_invalid_and_ambiguous_inventories(self):
        with self.assertRaises(FootprintError):parse_compiled_detectors(json.dumps({'compiled_detectors':'ec2'}))
        with self.assertRaises(FootprintError):parse_compiled_detectors('\n'.join([json.dumps({'compiled_detectors':['ec2']})]*2))
