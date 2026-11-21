import csv
import io
import unittest
import zipfile
from core import (normalize_facebook_url,extract_links,as_timestamp,make_srt,
                  export_csv,import_checkpoint,export_zip,MAX_URLS)

class CoreTests(unittest.TestCase):
    def test_supplied_facebook_share_link_forms(self):
        self.assertEqual(normalize_facebook_url('https://www.facebook.com/share/r/1BGrBYMauY/?mibextid=wwXIfr'),
                         'https://www.facebook.com/share/r/1BGrBYMauY/')
        self.assertEqual(normalize_facebook_url('https://www.facebook.com/share/v/14rDXprwH7J/?mibextid=wwXIfr'),
                         'https://www.facebook.com/share/v/14rDXprwH7J/')
        self.assertEqual(normalize_facebook_url('https://www.facebook.com/watch/?v=123&fbclid=abc'),
                         'https://www.facebook.com/watch/?v=123')

    def test_unsafe_domains_and_url_forms(self):
        for u in ['https://evil.com/reel/42','https://facebook.com.evil.com/reel/1',
                  'https://facebook.com@evil.com/reel/1','file:///etc/passwd',
                  'https://facebook.com','https://facebook.com:444/reel/1',
                  'https://u:p@facebook.com/reel/1','https://localhost/foo']:
            self.assertIsNone(normalize_facebook_url(u),u)

    def test_extract_links(self):
        u='https://www.facebook.com/reel/123'
        text=f'Link: {u}, https://fb.watch/abc/\n{u} https://evil.com/x'
        self.assertEqual(extract_links(text),[u,'https://fb.watch/abc/'])
        self.assertEqual(len(extract_links('\n'.join(f'https://fb.watch/{n}/' for n in range(800)))),MAX_URLS)

    def test_srt(self):
        self.assertEqual(as_timestamp(62.155),'00:01:02,155')
        self.assertEqual(make_srt([{'start':0,'end':1,'text':'Hello'},
                                   {'start':1,'end':2,'text':'World'}]),
                         '1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nWorld\n')

    def test_export_checkpoint_restore_and_zip(self):
        url='https://www.facebook.com/reel/123'
        result={'url':url,'title':'demo','status':'done','language':'en',
                'transcript':'Hello world','error':'',
                'srt':'1\n00:00:00,000 --> 00:00:02,000\nHello world\n'}
        results={url:result}
        self.assertEqual(import_checkpoint(export_csv(results,checkpoint=True)),results)
        rows=list(csv.DictReader(io.StringIO(export_csv(results).decode('utf-8-sig'))))
        self.assertEqual(rows[0]['transcript'],'Hello world')
        for fmt in ('txt','srt'):
            with zipfile.ZipFile(io.BytesIO(export_zip(results,fmt))) as z:
                self.assertEqual(z.namelist(),[f'video_0001.{fmt}','source_links.csv'])

    def test_csv_formula_protection(self):
        url='https://www.facebook.com/reel/123'
        item={'url':url,'title':'=HYPERLINK("malware")','status':'done',
              'transcript':'+cmd()','language':'en','error':'','srt':''}
        rows=list(csv.DictReader(io.StringIO(export_csv({url:item}).decode('utf-8-sig'))))
        self.assertTrue(rows[0]['title'].startswith("'="))
        self.assertTrue(rows[0]['transcript'].startswith("'+"))
        self.assertEqual(import_checkpoint(export_csv({url:item},checkpoint=True))[url],item)
