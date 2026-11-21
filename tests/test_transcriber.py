import tempfile
from pathlib import Path
import unittest
from unittest import mock
from types import SimpleNamespace
from transcriber import process_video

class FakeModel:
    def transcribe(self,filename,**kw):
        assert Path(filename).is_file()
        return iter([SimpleNamespace(start=0,end=1.4,text='Hello world'),
                     SimpleNamespace(start=1.4,end=3,text='again')]),SimpleNamespace(language='en')

class TranscriberTests(unittest.TestCase):
    def test_integration_using_fake_audio(self):
        def fake_download(url,folder):
            f=folder/'source.mp3'
            f.write_bytes(b'fake model accepts audio')
            return f,'Example'
        with mock.patch('transcriber.download_audio',side_effect=fake_download):
            result=process_video('https://fb.watch/example/',FakeModel())
        self.assertEqual(result['status'],'done')
        self.assertEqual(result['transcript'],'Hello world again')
        self.assertIn('00:00:01,400',result['srt'])

    def test_access_failure_is_recorded(self):
        with mock.patch('transcriber.download_audio',side_effect=RuntimeError('Login required')):
            result=process_video('https://fb.watch/example/',FakeModel())
        self.assertEqual(result['status'],'failed')
        self.assertIn('Login required',result['error'])
