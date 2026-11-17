"""Lazy desktop-style category browser with local, ranked search suggestions."""
from PyQt5.QtCore import QEvent, QModelIndex, QTimer, Qt
from PyQt5.QtGui import QIcon, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QCompleter, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)
from utils.catalog_search import CATEGORY_LABELS, rank_catalog


CATEGORY_DESCRIPTIONS = {
    'skin': 'Change the colours and finish of your workspace.',
    'header': 'Choose a background or import a personal wallpaper.',
    'font': 'Find a typeface for your workspace.',
    'emoji': 'Choose an expression for your profile.',
    'badge': 'Browse earned achievement badges and display settings.',
    'game': 'Open your available break-time games.',
}


class CategoryButton(QPushButton):
    def __init__(self, category, count, icon_path, inventory, parent=None):
        super().__init__(parent)
        self.setObjectName('CatalogCategoryTile')
        self.setAutoDefault(False)
        title = CATEGORY_LABELS[category]
        count_text = f'{count} Owned' if inventory else f'{count} Available'
        self.setAccessibleName(f'{title}, {count_text}')
        self.setToolTip(f'{title}\n{CATEGORY_DESCRIPTIONS[category]}\n{count_text}')
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(138, 142)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        art = QLabel()
        pixmap = QIcon(str(icon_path)).pixmap(152, 152)
        pixmap.setDevicePixelRatio(2)
        art.setPixmap(pixmap)
        art.setFixedHeight(78)
        art.setAlignment(Qt.AlignCenter)
        label = QLabel(title)
        label.setObjectName('CategoryName')
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        count_label = QLabel(count_text)
        count_label.setObjectName('CategoryCount')
        count_label.setAlignment(Qt.AlignCenter)
        for child in (art, label, count_label):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(child)


class CatalogBrowser(QWidget):
    def __init__(self, owner, *, entries, sections, row_factory, icon_dir,
                 inventory=False, extras=None):
        super().__init__(owner)
        self.owner = owner
        self.entries = list(entries)
        self.sections = sections
        self.row_factory = row_factory
        self.icon_dir = icon_dir
        self.inventory = inventory
        self.extras = extras
        self.category = None
        self._rows = {}
        self._all_results = False
        self.setStyleSheet('''
            QLineEdit#CatalogSearch { background:#0c1421; color:#edf5ff; border:1px solid #345364;
                border-radius:10px; padding:11px 13px; font-size:13px; selection-background-color:#544280; }
            QLineEdit#CatalogSearch:focus { border-color:#91dfe6; }
            QPushButton#CatalogCategoryTile { background:transparent; border:1px solid transparent; border-radius:12px; }
            QPushButton#CatalogCategoryTile:hover { background:rgba(113,174,218,18); border-color:#405b71; }
            QPushButton#CatalogCategoryTile:focus { border-color:#a990ee; }
            QLabel#CategoryName { color:#eff6ff; font-size:12px; font-weight:600; background:transparent; border:0; }
            QLabel#CategoryCount { color:#91a6b8; font-size:10px; background:transparent; border:0; }
            QLabel#CatalogLocation { color:#c3cddd; font-size:12px; background:transparent; border:0; }
            QPushButton#CatalogBack { background:transparent; color:#95dee8; border:0; padding:6px 0; text-align:left; }
            QFrame#CatalogResult { background:transparent; border:1px solid transparent; border-radius:9px; }
            QFrame#CatalogResult[focused="true"] { border-color:#a58cde; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.search = QLineEdit()
        self.search.setObjectName('CatalogSearch')
        self.search.setPlaceholderText('Search your inventory…' if inventory else 'Search the shop…')
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Search Inventory' if inventory else 'Search Shop')
        self.search.installEventFilter(self)
        self.search.setToolTip('Search names, categories, or descriptions. Partial keywords work too.')
        layout.addWidget(self.search)
        navigation = QHBoxLayout()
        self.back = QPushButton('‹  All Categories')
        self.back.setObjectName('CatalogBack')
        self.back.clicked.connect(self.go_home)
        self.location = QLabel('Browse Categories')
        self.location.setObjectName('CatalogLocation')
        if inventory:
            self.location.setToolTip('Default Order: Currently Used → Newest Acquired → Most Frequently Used → Other Items')
        navigation.addWidget(self.back)
        navigation.addWidget(self.location, 1)
        layout.addLayout(navigation)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet('QScrollArea, QScrollArea>QWidget>QWidget { background:transparent; border:0; }')
        body = QWidget()
        self.items_layout = QVBoxLayout(body)
        self.items_layout.setContentsMargins(0, 0, 3, 0)
        self.items_layout.setSpacing(10)
        self.scroll.setWidget(body)
        layout.addWidget(self.scroll, 1)
        self.model = QStandardItemModel(self)
        self.completer = QCompleter(self.model, self)
        self.completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.completer.setCompletionRole(Qt.UserRole + 1)
        self.completer.setMaxVisibleItems(8)
        self.completer.activated[QModelIndex].connect(self._suggestion_activated)
        self.completer.popup().setStyleSheet('''QListView { background:#101827; color:#eaf3ff;
            border:1px solid #52758a; padding:4px; font-family:"Segoe UI"; font-size:12px; }
            QListView::item { padding:8px; } QListView::item:selected { background:#34304c; }''')
        self.search.setCompleter(self.completer)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(140)
        self.debounce.timeout.connect(self._search_changed)
        self.search.textChanged.connect(lambda: self.debounce.start())
        self.search.returnPressed.connect(self._activate_first)
        self.focus_timer = QTimer(self)
        self.focus_timer.setSingleShot(True)
        self.focus_timer.setInterval(30)
        self.focus_timer.timeout.connect(self._scroll_to_focus)
        self._focused_reward_id = None
        for button in owner.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
        self._render()

    def _clear(self):
        self._rows = {}
        if hasattr(self.owner, '_inventory_rows'):
            self.owner._inventory_rows.clear()
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _add_row(self, reward_id, reward, *, show_category=False):
        row = QFrame()
        row.setObjectName('CatalogResult')
        row.setProperty('rewardId', reward_id)
        row.setProperty('focused', reward_id == self._focused_reward_id)
        outer = QVBoxLayout(row)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(3)
        if show_category:
            label = QLabel(CATEGORY_LABELS.get(reward.get('type'), 'Item'))
            label.setObjectName('CategoryCount')
            outer.addWidget(label)
        outer.addLayout(self.row_factory(reward_id, reward))
        for button in row.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
        self.items_layout.addWidget(row)
        self._rows[reward_id] = row

    def _render(self):
        self._clear()
        query = self.search.text().strip()
        self.owner._expanded_category = self.category
        if query:
            matches = rank_catalog(query, self.entries)
            self.location.setText(f'{len(matches)} Result' + ('' if len(matches) == 1 else 's'))
            self.back.show()
            for reward_id, reward in (matches if self._all_results else matches[:24]):
                self._add_row(reward_id, reward, show_category=True)
            if len(matches) > 24 and not self._all_results:
                more = QPushButton(f'Show All {len(matches)} Results')
                more.clicked.connect(self._show_all)
                self.items_layout.addWidget(more)
            if not matches:
                empty = QLabel('No matching items. Try a shorter keyword or a category name.')
                empty.setWordWrap(True)
                empty.setObjectName('CatalogLocation')
                self.items_layout.addWidget(empty)
        elif self.category:
            self.back.show()
            entries = [(key, value) for key, value in self.entries if value.get('type') == self.category]
            self.location.setText(f'{CATEGORY_LABELS[self.category]}  ·  {len(entries)} Items')
            for extra in (self.extras(self.category) if self.extras else []):
                wrap = QWidget()
                wrap.setLayout(extra)
                self.items_layout.addWidget(wrap)
            for reward_id, reward in entries:
                self._add_row(reward_id, reward)
            if not entries:
                empty = QLabel('No owned items in this category yet.' if self.inventory else 'No items available yet.')
                empty.setObjectName('CatalogLocation')
                self.items_layout.addWidget(empty)
        else:
            self.back.hide()
            self.location.setText('Browse Categories')
            home = QWidget()
            home.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            grid = QGridLayout(home)
            grid.setContentsMargins(2, 2, 2, 2)
            grid.setSpacing(8)
            self.category_buttons = {}
            for index, (category, _) in enumerate(self.sections):
                count = sum(reward.get('type') == category for _, reward in self.entries)
                tile = CategoryButton(category, count, self.icon_dir / f'{category}.png', self.inventory)
                tile.clicked.connect(lambda checked=False, key=category: self.open_category(key))
                grid.addWidget(tile, index//3, index%3)
                self.category_buttons[category] = tile
            self.items_layout.addWidget(home)
        self.items_layout.addStretch(1)

    def _search_changed(self):
        self._all_results = False
        self._render()
        self.scroll.verticalScrollBar().setValue(0)
        self.model.clear()
        for reward_id, reward in rank_catalog(self.search.text(), self.entries)[:8]:
            title = reward.get('display_name') or reward.get('name', reward_id)
            state = 'Owned' if reward_id in self.owner.user_data.get('unlocked', []) else (
                f'{int(reward.get("required_xp", 0)):,} XP' if reward.get('required_xp') else
                f'{int(reward.get("price", 0)):,} Coins')
            item = QStandardItem(QIcon(str(self.icon_dir / f'{reward.get("type")}.png')),
                                 f'{title}\n{CATEGORY_LABELS.get(reward.get("type"), "Item")} · {state}')
            item.setData(reward_id, Qt.UserRole)
            item.setData(title, Qt.UserRole + 1)
            self.model.appendRow(item)
        if self.search.text().strip() and self.model.rowCount() and self.search.hasFocus():
            self.completer.complete()
        else:
            self.completer.popup().hide()

    def _show_all(self):
        self._all_results = True
        self._render()

    def go_home(self):
        self.category = None
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.debounce.stop()
        self.completer.popup().hide()
        self._render()

    def open_category(self, category):
        self.category = category if category in CATEGORY_LABELS else None
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.debounce.stop()
        self.completer.popup().hide()
        self._render()
        self.scroll.verticalScrollBar().setValue(0)

    def refresh(self, entries):
        self.entries = list(entries)
        self._render()
        if self.search.text().strip():
            self._search_changed()

    def focus_reward(self, reward_id):
        self._focused_reward_id = reward_id
        reward = next((value for key, value in self.entries if key == reward_id), None)
        if reward is None:
            return
        if reward_id not in self._rows:
            self.open_category(reward['type'])
        row = self._rows.get(reward_id)
        if row:
            row.setProperty('focused', True)
            row.style().unpolish(row)
            row.style().polish(row)
            self.focus_timer.start()

    def _scroll_to_focus(self):
        row = self._rows.get(self._focused_reward_id)
        if row:
            self.scroll.ensureWidgetVisible(row, 0, 20)

    def _suggestion_activated(self, index):
        reward_id = index.data(Qt.UserRole)
        self.completer.popup().hide()
        self.focus_reward(reward_id)

    def _activate_first(self):
        matches = rank_catalog(self.search.text(), self.entries)
        if matches:
            self.focus_reward(matches[0][0])

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            if self.completer.popup().isVisible():
                self.completer.popup().hide()
                return True
            if self.search.text():
                self.search.clear()
                return True
        return super().eventFilter(watched, event)
