import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from blogops import workflows
from blogops.config import settings
from blogops.runners import Runner, RunnerError, parse_json
from blogops.store import Store, BudgetExceeded

ARTICLE={'title':'Useful source example','description':'An evidence based example','category':'Guide','tags':['guide'],'markdown_content':'This is a specific factual statement from the source.','faqs':[]}
EVIDENCE=[{'id':'source-1','text':'This is a specific factual statement from the source.','url':'https://example.org/'}]
REVIEW={'decision':'pass','rights':'clear','original_value':'A practical comparison','requires_expert_review':False,'coverage_checked':True,'issues':[],'claims':[{'claim':ARTICLE['markdown_content'],'source_id':'source-1','quote':ARTICLE['markdown_content'],'assessment':'supported'}]}

class Isolated(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.env=patch.dict(os.environ,{'BLOGOPS_STATE_DIR':self.tmp.name});self.env.start();self.addCleanup(self.env.stop)
  self.store=Store()

class WorkflowTests(Isolated):
 def create(self):return workflows.create_workflow('absian','Useful source example',['https://example.org/'],'A practical comparison',self.store)
 def test_complete_workflow_stops_at_human_review(self):
  calls=[]; bridges=[]
  results={'source_summary':{'sources':[{'source_id':'source-1','quote':ARTICLE['markdown_content'],'summary':'summary'}]},'plan':{'reader_problem':'clarity','original_value':'comparison','outline':['example']},'draft':ARTICLE,'metadata':{'description':ARTICLE['description'],'tags':['guide']},'review':REVIEW}
  def run(provider,prompt,ident,images=()):
   kind=self.store.get(ident)['kind'];calls.append((provider,kind));return dict(results[kind])
  def bridge(site,mode,payload):
   bridges.append(mode)
   if mode=='images':return payload['article']
   self.assertEqual(mode,'queue');self.assertEqual(payload['article']['operations']['gate']['status'],'passed')
   return {'draft_id':'draft-test','status':'pending_review'}
  ident=self.create()
  with patch.object(workflows,'collect_evidence',return_value=EVIDENCE),patch.object(Runner,'run',side_effect=run),patch.object(workflows,'legacy',side_effect=bridge):
   result=workflows.run_workflow(ident,self.store)
   self.assertEqual(result['state'],'pending_review')
   self.assertEqual([x['state'] for x in self.store.list(parent=ident)],['succeeded']*8)
   workflows.run_workflow(ident,self.store)
  self.assertEqual(bridges,['images','queue']);self.assertEqual(len(calls),5)
  self.assertIn(('agy','metadata'),calls);self.assertIn(('codex','review'),calls)
 def test_daily_workflow_limit(self):
  self.create()
  with self.assertRaises(BudgetExceeded):self.create()
 def test_auxiliary_bounded_fallback(self):
  ident=self.store.enqueue('absian','metadata','agy',{})
  with patch.object(Runner,'run',side_effect=[{'title':'out of scope'},{'tags':'invalid'},{'description':'valid','tags':['one']}]) as run:
   result=workflows.run_task(ident,self.store)
  self.assertEqual(result['description'],'valid')
  self.assertEqual([c.args[0] for c in run.call_args_list],['agy','agy','codex'])
 def test_budget_wait_does_not_fall_back(self):
  ident=self.store.enqueue('absian','metadata','agy',{})
  with patch.object(Runner,'run',side_effect=BudgetExceeded('limit')) as run:
   result=workflows.run_task(ident,self.store)
  self.assertEqual(result['status'],'budget_wait');self.assertEqual(run.call_count,1)
 def test_review_failure_never_queues(self):
  ident=self.create()
  for task in self.store.list(parent=ident):
   if task['kind'] in ('review','queue_draft'):break
   result=EVIDENCE if task['kind']=='evidence' else ARTICLE if task['kind'] in ('draft','images') else {}
   self.store.finish(task['id'],result)
  invalid={**REVIEW,'decision':'revise','issues':['Unsupported fact']}
  with patch.object(Runner,'run',return_value=invalid),patch.object(workflows,'legacy') as bridge:
   result=workflows.run_workflow(ident,self.store)
  self.assertEqual(result['state'],'needs_attention');bridge.assert_not_called()
  self.assertEqual(self.store.list(parent=ident)[-1]['state'],'queued')
 def test_image_budget_reservation_does_not_partially_consume(self):
  ident=self.create()
  for task in self.store.list(parent=ident):
   if task['kind']=='images':break
   self.store.finish(task['id'],ARTICLE if task['kind']=='draft' else {})
  self.store.reserve_calls('codex','model',8,amount=6)
  with patch.object(workflows,'legacy') as bridge:
   result=workflows.run_task(task['id'],self.store)
  self.assertEqual(result['status'],'budget_wait');bridge.assert_not_called()
  self.assertEqual(self.store.usage()[0]['calls'],6)

class RunnerTests(Isolated):
 def test_agy_actual_envelope(self):
  self.assertEqual(parse_json(json.dumps({'status':'SUCCESS','response':'```json\n{"summary":"ok"}\n```'})),{'summary':'ok'})
 def test_failed_envelope_rejected_even_structured(self):
  for value in ({'status':'FAILED','response':'{}'},{'status':'FAILED','structured_output':{'looks':'valid'}},{'is_error':True,'result':'{}'}):
   with self.assertRaises(RunnerError):parse_json(json.dumps(value))
 def test_non_object_rejected(self):
  with self.assertRaises(RunnerError):parse_json('[]')
 def test_codex_env_and_image_review(self):
  def execute(cmd,**kwargs):
   self.assertNotIn('TELEGRAM_BOT_TOKEN',kwargs['env']);self.assertNotIn('GITHUB_TOKEN',kwargs['env'])
   self.assertIn('--image',cmd);self.assertIn('read-only',cmd)
   Path(cmd[cmd.index('--output-last-message')+1]).write_text('{"decision":"pass"}')
   return SimpleNamespace(returncode=0,stdout='',stderr='')
  with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'secret','GITHUB_TOKEN':'secret'}),patch('blogops.runners.shutil.which',return_value='/bin/codex'),patch('blogops.runners.subprocess.run',side_effect=execute):
   result=Runner(self.store).run('codex','Review',images=['/tmp/example.png'])
  self.assertEqual(result,{'decision':'pass'});self.assertEqual(self.store.usage()[0]['calls'],1)
 def test_errors_do_not_reveal_output(self):
  with patch('blogops.runners.shutil.which',return_value='/bin/agy'),patch('blogops.runners.subprocess.run',return_value=SimpleNamespace(returncode=1,stdout='secret-token',stderr='secret-token')):
   with self.assertRaises(RunnerError) as error:Runner(self.store).run('agy','Prompt')
  self.assertNotIn('secret-token',str(error.exception))
  with self.store.db() as db:self.assertEqual(db.execute('SELECT state FROM calls').fetchone()[0],'failed')

if __name__=='__main__':unittest.main()

class ApprovalAndRepairTests(Isolated):
 def test_bot_token_matches_legacy_contract(self):
  import hashlib
  from blogops.bot import article_review_token
  expected=hashlib.sha256(json.dumps(ARTICLE,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()[:12]
  self.assertEqual(article_review_token(ARTICLE),expected)
 def test_review_receipt_changes_when_image_bytes_change(self):
  from blogops.bot import review_fingerprint
  root=Path(self.tmp.name);image=root/'blog-frontend/public/images/a.webp';image.parent.mkdir(parents=True);image.write_bytes(b'first')
  item={'article':{**ARTICLE,'heroImage':'/images/a.webp'},'existing_slug':'example'}
  before=review_fingerprint(item,root);image.write_bytes(b'second')
  self.assertNotEqual(before,review_fingerprint(item,root))
 def test_repair_preserves_url_and_does_not_write_existing_post(self):
  root=Path(self.tmp.name);post=root/'blog-frontend/src/content/blog/existing.md';post.parent.mkdir(parents=True)
  content='---\ntitle: Existing\ncategory: Guide\ndescription: Helpful post\n---\nOld unverified content'
  post.write_text(content)
  cfg={**workflows.site_config('absian'),'root':str(root)}
  with patch.object(workflows,'site_config',return_value=cfg):
   ident=workflows.create_workflow('absian','Repair',['https://example.org/'],'Improve verified value',self.store,existing_slug='existing')
   tasks=self.store.list(parent=ident)
   self.assertEqual(tasks[0]['payload']['existing_slug'],'existing')
   for task in tasks:
    if task['kind']=='draft':break
    self.store.finish(task['id'],EVIDENCE if task['kind']=='evidence' else {})
   with patch.object(Runner,'run',return_value=dict(ARTICLE)):
    article=workflows.run_task(task['id'],self.store)
  self.assertEqual(article['slug'],'existing');self.assertEqual(article['existing_slug'],'existing')
  self.assertEqual(post.read_text(),content)
 def test_changed_images_after_review_prevent_queue(self):
  ident=self.store.enqueue('absian','workflow','code',{})
  values={'evidence':EVIDENCE,'draft':ARTICLE,'images':ARTICLE,'review':{**REVIEW,'_reviewed_images':[{'url':'/wrong','sha256':'wrong'}]}}
  for kind,result in values.items():
   child=self.store.enqueue('absian',kind,'code',{},parent=ident);self.store.finish(child,result)
  child=self.store.enqueue('absian','queue_draft','code',{},parent=ident)
  with patch.object(workflows,'legacy') as bridge:result=workflows.run_task(child,self.store)
  self.assertEqual(result['status'],'needs_attention');bridge.assert_not_called()

class FencingTests(Isolated):
 def test_old_attempt_cannot_overwrite_new_worker(self):
  ident=self.store.enqueue('absian','draft','codex',{})
  old=self.store.claim(ident,lease_seconds=-1);self.store.recover_expired();self.store.retry(ident)
  current=self.store.claim(ident)
  self.assertFalse(self.store.finish(ident,{'old':True},expected_attempt=old['attempts']))
  self.assertEqual(self.store.get(ident)['state'],'running')
  self.assertTrue(self.store.finish(ident,{'new':True},expected_attempt=current['attempts']))
  self.assertEqual(self.store.get(ident)['result'],{'new':True})
