"""Integration and packaging checks for the production catalog."""
from pathlib import Path
import subprocess
import sys
import unittest
from utils.rewards import REWARDS

ROOT=Path(__file__).resolve().parents[1]


class ProductionCatalogTests(unittest.TestCase):
    def test_production_contains_only_tetris(self):
        self.assertEqual([key for key,value in REWARDS.items() if value.get('type')=='game'],['game_tetris'])
        self.assertFalse((ROOT/'frontend/rpg').exists())
        self.assertFalse((ROOT/'assets/rpg').exists())
        self.assertIn("'frontend.rpg'",(ROOT/'smducar_pyqt.spec').read_text())
        for category in ('skin','header','font','emoji','badge','game'):
            self.assertTrue((ROOT/f'assets/images/catalog_categories/{category}.png').is_file())

    def test_real_catalog_controls_and_game_lifetime(self):
        result=subprocess.run([sys.executable,str(ROOT/'tools/verify_catalog_ui.py'),'--offscreen'],
                              cwd=ROOT,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,(result.stdout+result.stderr)[-6000:])
        self.assertIn('PASS:',result.stdout)


if __name__=='__main__': unittest.main()
