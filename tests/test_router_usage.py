import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.router_usage import load_router_usage, rank_router_groups, record_router_run, usage_path


GROUPS = (('APPEALS', ('smd','dar')),
          ('FEDERAL', ('fcc','ferc','nlrb','itc','irsplr','mspb')),
          ('STATE', ('ohtax0','mnsutb','mework','mosu00')))


class RouterUsageTests(unittest.TestCase):
    def test_rank_within_each_category_and_preserve_ties(self):
        result = rank_router_groups(GROUPS, {'dar':5,'mspb':8,'ferc':3,'nlrb':3,'mework':20})
        self.assertEqual([label for label,_ in result], ['APPEALS','FEDERAL','STATE'])
        self.assertEqual(result[0][1], ('dar','smd'))
        self.assertEqual(result[1][1], ('mspb','ferc','nlrb','fcc','itc','irsplr'))
        self.assertEqual(result[2][1], ('mework','ohtax0','mnsutb','mosu00'))
        for before,after in zip(GROUPS,result): self.assertEqual(set(before[1]),set(after[1]))

    def test_new_user_keeps_default_order(self):
        self.assertEqual(rank_router_groups(GROUPS, {}), GROUPS)

    def test_run_counts_persist_and_change_next_open_order(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'profile'/'router_usage.json'
            self.assertTrue(record_router_run('dar', path))
            self.assertTrue(record_router_run('dar', path))
            self.assertTrue(record_router_run('smd', path))
            self.assertEqual(load_router_usage(path), {'dar':2,'smd':1})
            self.assertEqual(rank_router_groups(GROUPS,load_router_usage(path))[0][1], ('dar','smd'))
            self.assertEqual(len(list(path.parent.iterdir())),1)

    def test_windows_profiles_have_independent_history(self):
        with patch.dict(os.environ, {'LOCALAPPDATA':r'C:\Users\Alice\AppData\Local'}): first=usage_path()
        with patch.dict(os.environ, {'LOCALAPPDATA':r'C:\Users\Bob\AppData\Local'}): second=usage_path()
        self.assertNotEqual(first,second)

    def test_bad_counts_cannot_break_sorting(self):
        self.assertEqual(rank_router_groups(GROUPS, {'dar':True,'smd':-2,'mspb':'100','mework':None}), GROUPS)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'usage.json';path.write_text('{broken')
            self.assertEqual(load_router_usage(path),{})
            path.write_text(json.dumps({'runs':{'dar':3,'smd':'oops'}}))
            self.assertEqual(load_router_usage(path),{'dar':3})

    def test_write_failure_does_not_lose_existing_history(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'usage.json';record_router_run('dar',path)
            before=path.read_bytes()
            with patch('utils.router_usage.os.replace',side_effect=PermissionError('locked')):
                self.assertFalse(record_router_run('smd',path))
            self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
