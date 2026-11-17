"""Exercise real Shop/Inventory controls against a mocked, isolated reward profile."""
import argparse
from pathlib import Path
import os
import sys
from unittest.mock import Mock, patch

parser = argparse.ArgumentParser()
parser.add_argument('--offscreen', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
output = root / 'output/catalog-check'
output.mkdir(parents=True, exist_ok=True)
os.environ['PUBLIC'] = str(output / 'test-profile')
if args.offscreen:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QImage
from PyQt5 import sip
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QPushButton
from frontend.pyqt_dialogs import InventoryDialog, ShopDialog
from utils.rewards import ACHIEVEMENTS, REWARDS, normalize_user_rewards

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
owned = ['game_tetris']
for category in ('skin', 'header', 'font'):
    owned += [key for key, item in REWARDS.items() if item.get('type') == category][:1 if category != 'header' else 3]
profile = normalize_user_rewards({'xp': 15000, 'coins': 22000, 'unlocked': owned,
                                  'achievements': list(ACHIEVEMENTS)})
dialog_box = Mock()
dialog_box.exec_.return_value = 0
with patch('frontend.pyqt_dialogs.load_user_rewards', return_value=profile), \
     patch('utils.rewards.load_user_rewards', return_value=profile), \
     patch('frontend.pyqt_dialogs.save_user_rewards') as save_ui, \
     patch('utils.rewards.save_user_rewards') as save_rewards, \
     patch.object(InventoryDialog, 'create_styled_message_box', return_value=dialog_box), \
     patch.object(ShopDialog, 'create_styled_message_box', return_value=dialog_box):
    shop = ShopDialog()
    shop.show()
    QTest.qWait(100)
    browser = shop.catalog_browser
    assert len(browser.category_buttons) == 5 and not browser._rows, 'Home eagerly built item widgets'
    shop.grab().save(str(output / 'shop-categories.png'))
    for category in browser.category_buttons:
        icon = QImage(str(root / f'assets/images/catalog_categories/{category}.png'))
        assert not icon.isNull() and icon.hasAlphaChannel()
    browser.search.setFocus()
    QTest.keyClicks(browser.search, 'oce gla')
    QTest.qWait(220)
    assert browser.model.rowCount() and browser._rows
    assert 'Ocean Glass' in browser.model.item(0).text()
    assert browser.completer.pathFromIndex(browser.model.index(0, 0)) == 'Ocean Glass'
    QTest.keyClick(browser.search, Qt.Key_Return)
    QTest.qWait(40)
    save_rewards.assert_not_called()
    save_ui.assert_not_called()
    assert shop.isVisible(), 'Search Enter accidentally activated a dialog button'
    popup = browser.completer.popup()
    popup.setCurrentIndex(browser.completer.completionModel().index(0, 0))
    QTest.mouseClick(popup.viewport(), Qt.LeftButton, pos=popup.visualRect(popup.currentIndex()).center())
    QTest.qWait(200)
    assert browser.search.text() == 'Ocean Glass'
    assert browser._focused_reward_id == next(iter(browser._rows))
    assert len(browser._rows) == 1
    browser.completer.popup().hide()
    shop.grab().save(str(output / 'shop-search.png'))
    browser.search.setText('zzzzzz-no-item')
    QTest.qWait(200)
    assert not browser._rows and browser.location.text().startswith('0 Results')
    browser.go_home()
    assert not browser._rows
    browser.open_category('skin')
    buy = next((button for row in browser._rows.values() for button in row.findChildren(QPushButton)
                if button.text() == 'BUY' and button.isEnabled()), None)
    assert buy is not None
    coins = profile['coins']
    previous_owned = set(profile['unlocked'])
    QTest.mouseClick(buy, Qt.LeftButton)
    QTest.qWait(60)
    assert profile['coins'] < coins and save_rewards.called
    purchased = (set(profile['unlocked']) - previous_owned).pop()
    assert profile['item_history'][purchased]['acquired_at'] > 0
    assert browser.category == 'skin', 'Purchase lost the selected category'
    shop.close()
    QTest.qWait(40)

    inventory = InventoryDialog()
    inventory.show()
    QTest.qWait(100)
    browser = inventory.catalog_browser
    assert len(browser.category_buttons) == 6 and not browser._rows
    inventory.grab().save(str(output / 'inventory-categories.png'))
    unowned = next((key, reward) for key, reward in REWARDS.items()
                   if reward.get('type') == 'header' and key not in profile['unlocked'] and key != 'custom_wallpaper')
    browser.search.setText(unowned[1]['name'])
    QTest.qWait(180)
    assert unowned[0] not in browser._rows, 'Inventory exposed an unowned item'
    browser.search.setFocus()
    browser.search.setText('preci')
    QTest.qWait(200)
    assert browser._rows and browser.model.rowCount()
    browser.completer.popup().hide()
    inventory.grab().save(str(output / 'inventory-search.png'))
    browser.search.clear()
    QTest.qWait(180)
    assert not browser._rows and browser.back.isHidden()
    browser.open_category('skin')
    equip = next(button for row in browser._rows.values() for button in row.findChildren(QPushButton)
                 if button.text() == 'EQUIP')
    QTest.mouseClick(equip, Qt.LeftButton)
    QTest.qWait(50)
    assert profile['equipped']['skin'] and save_ui.called
    equipped_id = profile['equipped']['skin']
    assert profile['item_history'][equipped_id]['use_count'] == 1
    assert next(iter(browser._rows)) == equipped_id, 'Currently used item is not first'
    assert browser.category == 'skin'
    browser.open_category('header')
    assert browser._rows
    assert inventory.findChildren(QPushButton), 'Wallpaper import actions disappeared'
    # A real Tetris window must survive Inventory's delete-on-close lifecycle.
    from frontend.pyqt_tetris import TetrisGame
    with patch.object(TetrisGame, 'HIGHSCORE_FILE', str(output / 'test-highscore.txt')):
        inventory.launch_game('game_tetris')
        QTest.qWait(200)
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        games = app._autorouter_game_windows
        assert len(games) == 1
        game = next(iter(games.values()))
        assert isinstance(game, TetrisGame) and game.isVisible() and not sip.isdeleted(game)
        assert profile['item_history']['game_tetris']['use_count'] == 1
        game.game_over = True
        game.close()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert not games, 'Closed game leaked its retained window'
        QTest.qWait(100)

print('PASS: icon categories, partial search, suggestions, ownership filtering, safe keyboard selection, purchases, equip, refresh and Tetris lifetime', flush=True)
