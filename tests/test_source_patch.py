import hashlib,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import footprint

class ExactSourcePatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name);self.source=self.root/'source'
        (self.source/'processor').mkdir(parents=True);(self.source/'processor/go.mod').write_text('module fixture\n')
        (self.root/'experiments').mkdir();self.file=self.root/'experiments/control.patch'
        self.content='exact approved patch\n';self.file.write_text(self.content)
        self.manifest={'source':{'commit':'a'*40,'processor_dir':'processor','url':'https://github.com/oso-team/opentelemetry-collector-contrib.git','patch':{'path':'experiments/control.patch','sha256':hashlib.sha256(self.content.encode()).hexdigest()}}}
        self.actual=self.content;self.untracked=''
        self.root_patch=patch.object(footprint,'ROOT',self.root);self.root_patch.start();self.addCleanup(self.root_patch.stop)
        self.command_patch=patch.object(footprint,'command',side_effect=self.command);self.command_patch.start();self.addCleanup(self.command_patch.stop)
    def command(self,args,**kwargs):
        if args[1]=='rev-parse':return 'a'*40+'\n'
        if args[1]=='diff':return self.actual
        if args[1]=='ls-files':return self.untracked
        if args[1]=='remote':return self.manifest['source']['url']+'\n'
        raise AssertionError(args)
    def test_accepts_only_the_exact_recorded_patch(self):
        self.assertEqual('a'*40,footprint.verify_source(self.source,self.manifest))
    def test_rejects_changed_patch_file(self):
        self.file.write_text('different patch\n')
        with self.assertRaisesRegex(footprint.FootprintError,'checksum'):footprint.verify_source(self.source,self.manifest)
    def test_rejects_additional_source_edit(self):
        self.actual+='unrecorded edit\n'
        with self.assertRaisesRegex(footprint.FootprintError,'exact pinned patch'):footprint.verify_source(self.source,self.manifest)
    def test_rejects_untracked_source(self):
        self.untracked='extra.go\n'
        with self.assertRaisesRegex(footprint.FootprintError,'untracked'):footprint.verify_source(self.source,self.manifest)
    def test_rejects_patch_path_outside_repository(self):
        self.manifest['source']['patch']['path']='../outside.patch'
        with self.assertRaisesRegex(footprint.FootprintError,'repository-relative'):footprint.verify_source(self.source,self.manifest)
