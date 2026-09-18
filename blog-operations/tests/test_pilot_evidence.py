import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from blogops.content import collect_evidence,local_evidence,validate_verified_code
from blogops.workflows import create_workflow,prompt
from blogops.store import Store

class PilotEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.env=patch.dict(os.environ,{'BLOGOPS_STATE_DIR':self.tmp.name});self.env.start();self.addCleanup(self.env.stop)
 def test_section_after_twenty_thousand_chars_is_selected(self):
  html=('<html><title>Official docs</title><p>'+('Unrelated introduction. '*1500)+'</p><dl><dt id="os.link">os.link</dt><dd>'+('Create a hard link to the source file. '*8)+'</dd></dl></html>').encode()
  with patch('blogops.content.safe_get',return_value={'url':'https://example.org/os.html#os.link','content_type':'text/html','body':html}):
   result=collect_evidence(['https://example.org/os.html#os.link'])[0]
  self.assertIn('Create a hard link',result['text']);self.assertNotIn('Unrelated',result['text']);self.assertEqual(result['selection'],'fragment:os.link')
 def test_absent_anchor_fails_instead_of_unrelated_evidence(self):
  with patch('blogops.content.safe_get',return_value={'url':'https://example.org/#missing','content_type':'text/html','body':b'<html>No section here</html>'}):
   with self.assertRaisesRegex(ValueError,'anchor'):collect_evidence(['https://example.org/#missing'])
 def test_local_artifacts_are_snapshotted_and_identified_as_local(self):
  path=Path(self.tmp.name)/'execution.json';path.write_text('{"passed": true}')
  result=local_evidence([path])[0]
  original=result['text'];path.write_text('changed')
  self.assertEqual(result['kind'],'operator_supplied_test_artifact');self.assertNotIn('url',result)
  self.assertEqual(result['sha256'],hashlib.sha256(original.encode()).hexdigest())
  self.assertEqual(result['text'],'{"passed": true}')
 def test_workflow_records_evidence_before_worker_runs(self):
  path=Path(self.tmp.name)/'execution.json';path.write_text('{"passed": true}')
  store=Store();ident=create_workflow('absian','Proof',['https://example.org/'],'Actual execution',store,verification_files=[path],image_assets=[])
  record=store.get(ident)['payload']['verification_records'][0];path.unlink()
  self.assertIn('passed',record['text'])
  cfg={'name':'Site','language':'ko','focus':'test'}
  data=json.loads(prompt('plan',cfg,store.get(ident)['payload'],{'evidence':[record]}).split('INPUT DATA:\n')[1])
  self.assertNotIn('verification_records',data['request']);self.assertNotIn('image_assets',data['request'])
  self.assertEqual(data['evidence'][0],record)
 def test_unsupported_artifact_type_rejected(self):
  path=Path(self.tmp.name)/'.env';path.write_text('TOKEN=value')
  with self.assertRaises(ValueError):local_evidence([path])
 def test_changed_or_missing_verified_python_is_rejected(self):
  path=Path(self.tmp.name)/'checked.py';path.write_text('print("measured")\n')
  evidence=local_evidence([path])
  for body in ('No code', '```python\nprint("rewritten")\n```'):
   with self.assertRaisesRegex(ValueError,'unchanged'):validate_verified_code({'markdown_content':body},evidence)
  validate_verified_code({'markdown_content':'```python\nprint("measured")\n```'},evidence)
 def test_duplicate_or_corrupt_verified_python_is_rejected(self):
  path=Path(self.tmp.name)/'checked.py';path.write_text('print("measured")\n')
  evidence=local_evidence([path]);body='```python\nprint("measured")\n```'
  with self.assertRaises(ValueError):validate_verified_code({'markdown_content':body+'\n'+body},evidence)
  evidence[0]['text']='changed'
  with self.assertRaisesRegex(ValueError,'snapshot'):validate_verified_code({'markdown_content':body},evidence)
