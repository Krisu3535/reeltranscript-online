import time
import unittest
from jobs import JobManager

class MockModel: pass

def mock_process(url,model,language):
    time.sleep(.025)
    return {'url':url,'title':'mock clip','status':'done','language':language or 'en',
            'transcript':'one two three','srt':'1\n00:00:00,000 --> 00:00:02,000\none two three\n','error':''}

class JobTests(unittest.TestCase):
    def setUp(self):
        self.mgr=JobManager(model_factory=lambda name: MockModel(),processor=mock_process)

    def wait_finish(self,token):
        for _ in range(150):
            state=self.mgr.snapshot(token)
            if state['state']!='running':
                return state
            time.sleep(.01)
        self.fail('Background worker did not complete')

    def test_process_resume_and_no_repeat(self):
        urls=[f'https://fb.watch/{i}/' for i in range(4)]
        self.assertEqual(self.mgr.start('mine',urls,{},model_name='tiny',language='en',limit=2),2)
        state=self.wait_finish('mine')
        self.assertEqual(len(state['results']),2)
        self.assertEqual(state['state'],'complete')
        self.assertEqual(self.mgr.start('mine',urls,state['results'],model_name='tiny',language='en',limit=10),2)
        state=self.wait_finish('mine')
        self.assertEqual(len(state['results']),4)
        self.assertEqual(self.mgr.start('mine',urls,state['results'],model_name='tiny',language='en',limit=5),0)

    def test_only_one_job_on_free_server(self):
        urls=[f'https://fb.watch/{i}/' for i in range(10)]
        self.mgr.start('one',urls,{},model_name='tiny',language='en',limit=10)
        with self.assertRaises(RuntimeError):
            self.mgr.start('two',urls,{},model_name='tiny',language='en',limit=5)
        self.mgr.stop('one')
        self.assertEqual(self.wait_finish('one')['state'],'stopped')
