import os

from PySide6.QtCore import QDir, QPoint, QProcess, QStandardPaths, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence
from pyside6_scintilla import Scintilla
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabBar,
    QTabWidget,
    QToolButton,
    QToolBar,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qtedit import icons
from qtedit.codeintel_client import CodeIntelClient
from qtedit.completion_popup import CompletionPopup
from qtedit.debugger import breakpoint_store
from qtedit.debugger.breakpoint_dialog import BreakpointConditionDialog
from qtedit.debugger.dbgp import DbgpSession
from qtedit.debugger.session import DebugSession
from qtedit import editor_commands
from qtedit.editor import FOLD_MARGIN, LINE_NUMBER_MARGIN, UDL_LANGUAGES, CodeEditor, language_for_filename
from qtedit.find_bar import SEARCH_FILES, SEARCH_PROJECT, FindFrame
from qtedit.incremental_search import IncrementalSearchBar
from qtedit.menus import Command, MenuBuilder, add_window_shortcut, load_bindings
from qtedit import mru
from qtedit.history import RESTORE_PREF, EditorHistory, default_db_path
from qtedit import find_in_files
from qtedit.prefs import get_global_prefs
from qtedit.prefs_dialog import PreferencesDialog
from qtedit.projects import model as project_model
from qtedit.projects.tree_model import IS_FILE_ROLE, NODE_ROLE, build_project_model
from qtedit import session
from qtedit.skin.css import komodo_stylesheet
from qtedit.save_dialog import SaveModifiedDialog
from qtedit.statusbar import EditorStatusBar, file_icon
from qtedit import vcs
from qtedit.vcs_dock import VCSPanel
from qtedit.workspace import TYPE_HORIZONTAL, TYPE_ICONS, KoPane, make_splitter
from qtedit.toolbox import model as toolbox_model
from qtedit.toolbox.item_dialog import ToolboxItemDialog
from qtedit.toolbox.tree_model import (
    FOLDER_PATH_ROLE,
    TOOLBOX_ITEM_ROLE,
    build_toolbox_model,
)

KOMODO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The real Komodo app icons, already sitting in the repo from a prior build
# rather than duplicated into qtedit/ -- the same "reuse prior build
# artifacts" pattern used for the codeintel3/stdlibs/*.cix catalogs.
APP_ICON_PATH = os.path.join(KOMODO_ROOT, "build", "release", "main", "komodo128.edit.png")

# Persisted pane layout, like Komodo's ui.tabs.sidepanes.state pref plus
# the xulstore widths. Defaults match a Komodo 12 classic-mode profile with
# all panes and the toolbar row collapsed; sizes are komodo.p.xul's.
WORKSPACE_PREF = "ui.workspace"
WORKSPACE_DEFAULTS = {
    "workspace_left_area": {"collapsed": True, "size": 200},
    "workspace_right_area": {"collapsed": True, "size": 200},
    "workspace_bottom_area": {"collapsed": True, "size": 200},
    "toolbar": {"collapsed": True},
}


class MainWindow(QMainWindow):
    def __init__(self, project_dir=None):
        super().__init__()
        self.setWindowTitle("KomodoEdit (Qt MVP)")
        self.resize(1100, 700)
        if os.path.isfile(APP_ICON_PATH):
            self.setWindowIcon(QIcon(APP_ICON_PATH))

        self._history = EditorHistory(
            self._open_history_location, default_db_path(),
            restore=get_global_prefs().get(RESTORE_PREF), parent=self)
        self.tabs = QTabWidget()
        self._history.message.connect(lambda msg: self.status_bar.showMessage(msg, 5000))
        # Named after Komodo's XUL id; koTabs opts into skin/qss.py's
        # Komodo tab rules (shared with the pane tab strips).
        self.tabs.tabBar().setObjectName("tabbed-view")
        self.tabs.tabBar().setProperty("koTabs", True)
        self.tabs.setDocumentMode(True)
        # Close buttons are Komodo's glyph buttons, see _add_editor_tab.
        self.tabs.setTabsClosable(False)
        self.tabs.currentChanged.connect(self._on_current_tab_changed)

        self.status_bar = EditorStatusBar()
        self.status_bar.open_requested.connect(self.open_file)
        self.status_bar.language_menu_filler = self._fill_view_as_language_menu

        self._isearch_bar = IncrementalSearchBar(self)
        self._isearch_bar.closed.connect(self._return_focus_to_editor)
        self._isearch_bar.open_dialog_requested.connect(self._isearch_to_find_frame)

        self._find_bar = FindFrame(self)
        self._find_bar.hide()
        self._find_bar.closed.connect(self._return_focus_to_editor)
        self._find_bar.message.connect(lambda msg: self.status_bar.showMessage(msg, 5000))
        self._find_bar.hits_found.connect(self._on_find_in_files_hits)
        self._find_bar.replacements_applied.connect(self._on_find_in_files_replaced)
        self._find_bar.open_files_provider = self._open_file_paths
        self._find_bar.project_dir_provider = (
            lambda: self._project.base_dir if self._project is not None else None
        )
        self._find_bar.default_dir_provider = self._default_search_dir

        self._build_workspace()

        self._prefs_dialog = None
        self._last_replace_undo = []
        self._running_processes = []
        self._closed_tabs = mru.ClosedTabs()
        self._build_menu()
        self._build_project_tree(project_dir or os.getcwd())
        self._build_toolbox()
        self._build_find_results()
        self._build_vcs()
        self._build_debugger()
        self._build_codeintel()
        self._restore_workspace()

        self.new_file()

    def _build_workspace(self):
        """komodo.p.xul's #komodo-hbox: left pane | editor column | right
        pane, where the editor column is the editor (#komodo-editor-vbox-
        inner: views, classic statusbar, find frame) over the bottom pane."""
        self.left_pane = KoPane("workspace_left_area", TYPE_ICONS)
        self.right_pane = KoPane("workspace_right_area", TYPE_ICONS)
        self.bottom_pane = KoPane("workspace_bottom_area", TYPE_HORIZONTAL)
        self._panes = {
            pane.objectName(): pane for pane in (self.left_pane, self.right_pane, self.bottom_pane)
        }

        editor_box = QWidget()
        editor_box.setObjectName("komodo-editor-vbox-inner")
        editor_layout = QVBoxLayout(editor_box)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self.tabs, 1)
        editor_layout.addWidget(self._isearch_bar)
        editor_layout.addWidget(self.status_bar)
        editor_layout.addWidget(self._find_bar)

        self._editor_splitter = make_splitter(Qt.Orientation.Vertical, "bottom_splitter")
        self._editor_splitter.addWidget(editor_box)
        self._editor_splitter.addWidget(self.bottom_pane)
        self._editor_splitter.setStretchFactor(0, 1)

        self._workspace_splitter = make_splitter(Qt.Orientation.Horizontal, "komodo-hbox")
        self._workspace_splitter.addWidget(self.left_pane)
        self._workspace_splitter.addWidget(self._editor_splitter)
        self._workspace_splitter.addWidget(self.right_pane)
        self._workspace_splitter.setStretchFactor(1, 1)
        self.setCentralWidget(self._workspace_splitter)

    def _restore_workspace(self):
        state = get_global_prefs().get(WORKSPACE_PREF) or {}
        merged = {key: {**value, **state.get(key, {})} for key, value in WORKSPACE_DEFAULTS.items()}
        for pane_id, pane in self._panes.items():
            pane.setVisible(not merged[pane_id]["collapsed"])
        left = merged["workspace_left_area"]["size"]
        right = merged["workspace_right_area"]["size"]
        bottom = merged["workspace_bottom_area"]["size"]
        self._workspace_splitter.setSizes([left, max(100, self.width() - left - right), right])
        self._editor_splitter.setSizes([max(100, self.height() - bottom), bottom])
        self._toolbar.setVisible(not merged["toolbar"]["collapsed"])

    def _save_workspace(self):
        sizes = self._workspace_splitter.sizes()
        state = {
            "workspace_left_area": {"collapsed": not self.left_pane.isVisible(), "size": sizes[0]},
            "workspace_right_area": {"collapsed": not self.right_pane.isVisible(), "size": sizes[2]},
            "workspace_bottom_area": {
                "collapsed": not self.bottom_pane.isVisible(),
                "size": self._editor_splitter.sizes()[1],
            },
            "toolbar": {"collapsed": not self._toolbar.isVisible()},
        }
        # Collapsed panes report size 0; keep their last real size instead.
        previous = get_global_prefs().get(WORKSPACE_PREF) or {}
        for pane_id, entry in state.items():
            if entry.get("size") == 0:
                entry["size"] = previous.get(pane_id, WORKSPACE_DEFAULTS[pane_id]).get(
                    "size", WORKSPACE_DEFAULTS[pane_id].get("size")
                )
        get_global_prefs().set(WORKSPACE_PREF, state)

    def _open_file_paths(self):
        return [
            self.tabs.widget(i).filepath
            for i in range(self.tabs.count())
            if self.tabs.widget(i).filepath
        ]

    def _build_menu(self):
        """Komodo's menubar (menus.py) wired to qtedit's implementations,
        plus a Debug menu after View, where Komodo IDE has it."""
        self._menu_builder = MenuBuilder(self, self._komodo_commands(), {
            "menu_view_tabs": self._fill_tabs_and_sidebars_menu,
            "menu_viewAsLanguage": self._fill_view_as_language_menu,
            "menu_recentlyClosedTabs": self._fill_recently_closed_tabs_menu,
            "menu_mruFiles": self._fill_recent_files_menu,
            "menu_recentProjects": self._fill_recent_projects_menu,
        })
        self._menu_builder.build(self.menuBar(), extra_menus=[("View", self._build_debug_menu())])
        # Keybindings of commands that have no menu item.
        bindings = load_bindings()
        for command_id in ("cmd_findPrevious", "cmd_viewBottomPane", "cmd_focusEditor",
                           "cmd_reopenLastClosedTab"):
            add_window_shortcut(self, bindings[command_id], self._komodo_commands()[command_id].run)
        self._build_toolbar()

    def _editor_call(self, method_name, *args):
        """Command body that forwards to the current editor."""
        def run():
            editor = self.tabs.currentWidget()
            if editor is not None:
                getattr(editor, method_name)(*args)
        return run

    def _on_editor(self, func, *args):
        """Command body calling func(current editor, *args)."""
        def run():
            editor = self.tabs.currentWidget()
            if editor is not None:
                func(editor, *args)
        return run

    def _comment_delimiters(self):
        editor = self.tabs.currentWidget()
        return editor_commands.comment_delimiters(editor.language_names()) if editor is not None else None

    def _comment(self, commenting):
        info = self._comment_delimiters()
        if info is not None:
            (editor_commands.comment if commenting else editor_commands.uncomment)(
                self.tabs.currentWidget(), info)

    def _convert(self, converter):
        editor = self.tabs.currentWidget()
        if editor is None:
            return
        try:
            editor_commands.convert_selection_by_line(editor, converter)
        except ValueError as exc:  # From Hexadecimal on non-hex text
            self.status_bar.showMessage(str(exc), 5000)

    def _tab_width(self):
        return get_global_prefs().get("tabWidth") or 8

    def _bookmark_goto(self, func, message):
        editor = self.tabs.currentWidget()
        if editor is not None and not func(editor):
            self.status_bar.showMessage(message, 5000)

    def _komodo_commands(self):
        if getattr(self, "_commands", None) is not None:
            return self._commands
        editor = self.tabs.currentWidget
        has_project = lambda: self._project is not None  # noqa: E731
        has_editor = lambda: editor() is not None  # noqa: E731
        can_fold = lambda: editor() is not None and editor().marginWidthN(FOLD_MARGIN) > 0  # noqa: E731

        def view_toggle(getter, setter):
            return Command(
                run=lambda: editor() is not None and setter(editor(), not getter(editor())),
                checked=lambda: editor() is not None and bool(getter(editor())),
            )

        self._commands = {
            # File
            "cmd_new": Command(self.new_file),
            "cmd_newTab": Command(self.new_file),
            "cmd_open": Command(self.open_file_dialog),
            "cmd_bufferClose": Command(lambda: self._close_tab(self.tabs.currentIndex())),
            "cmd_bufferCloseOthers": Command(self._close_other_tabs),
            "cmd_closeAll": Command(self._close_all_tabs),
            "cmd_save": Command(self.save_current),
            "cmd_saveAs": Command(self.save_current_as),
            "cmd_saveAll": Command(self._save_all),
            "cmd_quit": Command(self.close),
            "cmd_revert": Command(self._revert, enabled=lambda: (
                editor() is not None and bool(editor().filepath) and bool(editor().modify()))),
            "cmd_reopenLastClosedTab": Command(self._reopen_last_closed_tab),
            # Edit
            "cmd_undo": Command(self._editor_call("undo")),
            "cmd_redo": Command(self._editor_call("redo")),
            "cmd_cut": Command(self._editor_call("cut")),
            "cmd_copy": Command(self._editor_call("copy")),
            "cmd_paste": Command(self._editor_call("paste")),
            "cmd_selectAll": Command(self._editor_call("selectAll")),
            "cmd_find": Command(self.open_find_bar),
            "cmd_replace": Command(lambda: self.open_find_bar(replace=True)),
            "cmd_findInFiles": Command(self.open_find_in_files),
            "cmd_replaceInFiles": Command(lambda: self.open_find_bar(replace=True, search_in=SEARCH_FILES)),
            "cmd_findInCurrProject": Command(
                lambda: self.open_find_bar(search_in=SEARCH_PROJECT), enabled=has_project),
            "cmd_replaceInCurrProject": Command(
                lambda: self.open_find_bar(replace=True, search_in=SEARCH_PROJECT), enabled=has_project),
            "cmd_findNext": Command(self._find_bar.find_next),
            "cmd_findPrevious": Command(self._find_bar.find_previous),
            "cmd_startIncrementalSearch": Command(self.start_incremental_search),
            "cmd_editPrefs": Command(self.open_preferences),
            # Code
            "cmd_comment": Command(lambda: self._comment(True),
                                   enabled=lambda: self._comment_delimiters() is not None),
            "cmd_uncomment": Command(lambda: self._comment(False),
                                     enabled=lambda: self._comment_delimiters() is not None),
            "cmd_indent": Command(self._editor_call("tab")),
            "cmd_dedent": Command(self._editor_call("backTab")),
            "cmd_tabify": Command(lambda: self._on_editor(editor_commands.tabify, self._tab_width())()),
            "cmd_untabify": Command(lambda: self._on_editor(editor_commands.untabify, self._tab_width())()),
            "cmd_editReflow": Command(lambda: self._on_editor(
                editor_commands.reflow_paragraph, get_global_prefs().get("editAutoWrapColumn"))()),
            "cmd_join": Command(self._on_editor(editor_commands.join_lines)),
            "cmd_cleanLineEndings": Command(self._on_editor(editor_commands.clean_line_endings)),
            "cmd_removeTrailingWhitespace": Command(
                self._on_editor(editor_commands.remove_trailing_whitespace)),
            "cmd_convertUpperCase": Command(lambda: self._convert(str.upper)),
            "cmd_convertLowerCase": Command(lambda: self._convert(str.lower)),
            "cmd_convertTitleCase": Command(lambda: self._convert(editor_commands.title_case)),
            "cmd_convertToHex": Command(lambda: self._convert(editor_commands.to_hex)),
            "cmd_convertFromHex": Command(lambda: self._convert(editor_commands.from_hex)),
            # Komodo's Ctrl+Space is word completion and Ctrl+J codeintel;
            # qtedit has only codeintel completion, so both trigger it.
            "cmd_completeWord": Command(self.trigger_autocomplete),
            "cmd_triggerPrecedingCompletion": Command(self.trigger_autocomplete),
            # Navigation
            "cmd_gotoLine": Command(self._goto_line),
            "cmd_jumpToMatchingBrace": Command(self._jump_to_matching_brace),
            "cmd_historyBack": Command(lambda: self._history.go_back(editor()),
                                       enabled=self._history.can_go_back),
            "cmd_historyForward": Command(lambda: self._history.go_forward(editor()),
                                          enabled=self._history.can_go_forward),
            "cmd_editCenterVertically": Command(self._editor_call("verticalCentreCaret")),
            "cmd_editMoveCurrentLineToTop": Command(
                self._on_editor(editor_commands.move_current_line_to_top)),
            "cmd_jumpToParentFold": Command(
                self._on_editor(editor_commands.jump_to_parent_fold), enabled=can_fold),
            "cmd_jumpToPreviousFold": Command(
                self._on_editor(editor_commands.jump_to_previous_fold), enabled=can_fold),
            "cmd_jumpToNextFold": Command(
                self._on_editor(editor_commands.jump_to_next_fold), enabled=can_fold),
            "cmd_bookmarkToggle": Command(
                self._on_editor(editor_commands.toggle_bookmark), enabled=has_editor),
            "cmd_bookmarkGotoNext": Command(lambda: self._bookmark_goto(
                editor_commands.goto_next_bookmark, "No next bookmark can be found")),
            "cmd_bookmarkGotoPrevious": Command(lambda: self._bookmark_goto(
                editor_commands.goto_previous_bookmark, "No previous bookmark can be found")),
            "cmd_bookmarkRemoveAll": Command(
                self._on_editor(editor_commands.remove_all_bookmarks), enabled=has_editor),
            "cmd_focusEditor": Command(self._return_focus_to_editor),
            # View
            "cmd_toggleToolbars": Command(
                lambda: self._toolbar.setVisible(not self._toolbar.isVisible()),
                checked=lambda: self._toolbar.isVisible()),
            "cmd_toggleTabBar": Command(
                lambda: self.tabs.tabBar().setVisible(not self.tabs.tabBar().isVisible()),
                checked=lambda: self.tabs.tabBar().isVisible()),
            "cmd_viewWhitespace": view_toggle(
                lambda e: e.viewWS(), lambda e, on: e.setViewWS(1 if on else 0)),
            "cmd_viewIndentationGuides": view_toggle(
                lambda e: e.indentationGuides(), lambda e, on: e.setIndentationGuides(3 if on else 0)),
            "cmd_viewLineNumbers": view_toggle(
                lambda e: e.marginWidthN(LINE_NUMBER_MARGIN),
                lambda e, on: e.set_line_numbers_visible(on)),
            "cmd_viewEOL": view_toggle(lambda e: e.viewEOL(), lambda e, on: e.setViewEOL(on)),
            "cmd_wordWrap": view_toggle(
                lambda e: e.wrapMode(), lambda e, on: e.setWrapMode(1 if on else 0)),
            "cmd_fontZoomIn": Command(self._editor_call("zoomIn")),
            "cmd_fontZoomOut": Command(self._editor_call("zoomOut")),
            "cmd_viewFullScreen": Command(
                lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen(),
                checked=self.isFullScreen),
            "cmd_foldExpandAll": Command(self._editor_call("foldAll", Scintilla.FoldAction.Expand)),
            "cmd_foldCollapseAll": Command(self._editor_call("foldAll", Scintilla.FoldAction.Contract)),
            "cmd_viewLeftPane": Command(self.left_pane.toggle),
            "cmd_viewRightPane": Command(self.right_pane.toggle),
            "cmd_viewBottomPane": Command(self.bottom_pane.toggle),
            # Project
            "cmd_openProject": Command(self.open_project),
            "cmd_newProject": Command(self.new_project),
            "cmd_closeProject": Command(self.close_project, enabled=has_project),
            "cmd_closeAllProjects": Command(self.close_project, enabled=has_project),
            # Help
            "cmd_helpAbout": Command(self._about),
        }
        return self._commands

    def _build_debug_menu(self):
        debug_menu = QMenu("&Debug", self)

        self._start_debug_action = QAction("&Start Debugging", self)
        self._start_debug_action.setShortcut(QKeySequence("F5"))
        self._start_debug_action.triggered.connect(self.start_debugging)
        debug_menu.addAction(self._start_debug_action)

        toggle_bp_action = QAction("Toggle &Breakpoint", self)
        toggle_bp_action.setShortcut(QKeySequence("F9"))
        toggle_bp_action.triggered.connect(self.toggle_breakpoint)
        debug_menu.addAction(toggle_bp_action)

        edit_bp_condition_action = QAction("Edit Breakpoint &Condition...", self)
        edit_bp_condition_action.triggered.connect(self.edit_breakpoint_condition)
        debug_menu.addAction(edit_bp_condition_action)

        debug_menu.addSeparator()

        self._continue_action = QAction("&Continue", self)
        self._continue_action.setShortcut(QKeySequence("F6"))
        self._continue_action.setEnabled(False)
        self._continue_action.triggered.connect(self._debug_continue)
        debug_menu.addAction(self._continue_action)

        self._step_over_action = QAction("Step &Over", self)
        self._step_over_action.setShortcut(QKeySequence("F10"))
        self._step_over_action.setEnabled(False)
        self._step_over_action.triggered.connect(self._debug_step_over)
        debug_menu.addAction(self._step_over_action)

        self._step_into_action = QAction("Step &Into", self)
        self._step_into_action.setShortcut(QKeySequence("F11"))
        self._step_into_action.setEnabled(False)
        self._step_into_action.triggered.connect(self._debug_step_into)
        debug_menu.addAction(self._step_into_action)

        self._step_out_action = QAction("Step Ou&t", self)
        self._step_out_action.setShortcut(QKeySequence("Shift+F11"))
        self._step_out_action.setEnabled(False)
        self._step_out_action.triggered.connect(self._debug_step_out)
        debug_menu.addAction(self._step_out_action)

        self._stop_debug_action = QAction("S&top", self)
        self._stop_debug_action.setShortcut(QKeySequence("Shift+F5"))
        self._stop_debug_action.setEnabled(False)
        self._stop_debug_action.triggered.connect(self._debug_stop)
        debug_menu.addAction(self._stop_debug_action)
        return debug_menu

    def _build_toolbar(self):
        """#main-toolboxrow: Komodo's standard toolbar buttons and the
        workspace pane toggles, each with the glyph its CSS class or id
        gets in the skin."""
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("main-toolboxrow")
        toolbar.setMovable(False)
        self._toolbar = toolbar
        css = komodo_stylesheet()
        for command_id, selector, tooltip in (
            ("cmd_undo", ".native-undo-icon:before", "Undo"),
            ("cmd_redo", ".native-redo-icon:before", "Redo"),
            (None, None, None),
            ("cmd_new", ".native-new-file-icon:before", "New File"),
            ("cmd_open", ".native_open_icon:before", "Open File"),
            ("cmd_save", ".native-save-icon:before", "Save File"),
            (None, None, None),
            ("cmd_viewLeftPane", "#toggleLeftPane:before", "Show/Hide Left Pane"),
            ("cmd_viewBottomPane", "#toggleBottomPane:before", "Show/Hide Bottom Pane"),
            ("cmd_viewRightPane", "#toggleRightPane:before", "Show/Hide Right Pane"),
        ):
            if command_id is None:
                toolbar.addSeparator()
                continue
            action = QAction(icons.glyph(icons.css_glyph(css.value(selector, "content"))), tooltip, self)
            action.triggered.connect(lambda _c=False, c=command_id: self._commands[c].run())
            toolbar.addAction(action)
        self.addToolBar(toolbar)

    def _fill_tabs_and_sidebars_menu(self, menu):
        """ko.widgets.updateMenu: each pane's widgets in tab order,
        separated by pane; picking one shows it."""
        for pane in (self.left_pane, self.right_pane, self.bottom_pane):
            for widget_id, label in pane.visible_widgets():
                action = menu.addAction(label)
                action.triggered.connect(
                    lambda _c=False, p=pane, w=widget_id: p.show_widget(w))
            menu.addSeparator()
        actions = menu.actions()
        if actions and actions[-1].isSeparator():
            menu.removeAction(actions[-1])

    def _fill_view_as_language_menu(self, menu):
        editor = self.tabs.currentWidget()
        current = editor.language_name() if editor is not None else None
        for name in UDL_LANGUAGES:
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name == current)
            action.triggered.connect(lambda _c=False, n=name: self._set_language(n))

    def _set_language(self, name):
        editor = self.tabs.currentWidget()
        if editor is None:
            return
        editor.set_lexer_by_name(name)
        self._update_tab_icon(editor)
        self.status_bar.refresh()

    def _close_other_tabs(self):
        current = self.tabs.currentWidget()
        others = [self.tabs.widget(i) for i in range(self.tabs.count())
                  if self.tabs.widget(i) is not current]
        if self._offer_to_save(others):
            for editor in others:
                self._close_tab(self.tabs.indexOf(editor), offer_to_save=False)

    def _close_all_tabs(self):
        editors = [self.tabs.widget(i) for i in range(self.tabs.count())]
        if self._offer_to_save(editors):
            for editor in editors:
                self._close_tab(self.tabs.indexOf(editor), offer_to_save=False)

    def _mru_icon(self, path):
        return file_icon(language_for_filename(path))

    def _fill_recent_files_menu(self, menu):
        mru.fill_menu(menu, get_global_prefs(), mru.FILE_LIST, self.open_file, icon_for=self._mru_icon)

    def _fill_recent_projects_menu(self, menu):
        # uilayout: limit 5, then "More", plus the manage item (whose
        # dialog qtedit doesn't have yet).
        mru.fill_menu(menu, get_global_prefs(), mru.PROJECT_LIST, self.open_project_path, limit=5,
                      manage=("&Manage the Most Recent Projects List", None))

    def _fill_recently_closed_tabs_menu(self, menu):
        self._closed_tabs.fill_menu(menu, self._reopen_closed_tab,
                                    load_bindings().get("cmd_reopenLastClosedTab"))

    def _open_history_location(self, loc):
        """history.js view_and_line_from_loc: the buffer's tab, reopening
        the file if it was closed."""
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if editor is loc.key or (editor.filepath and os.path.abspath(editor.filepath) == loc.key):
                self.tabs.setCurrentIndex(i)
                return editor
        if isinstance(loc.key, str) and os.path.isfile(loc.key):
            self.open_file(loc.key)
            return self.tabs.currentWidget()
        return None

    def _reopen_closed_tab(self, path):
        self._closed_tabs.discard(path)
        self.open_file(path)

    def _reopen_last_closed_tab(self):
        path = self._closed_tabs.pop()
        if path is not None:
            self.open_file(path)

    def _save_all(self):
        current = self.tabs.currentIndex()
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if editor.filepath or editor.toolbox_item is not None:
                self.tabs.setCurrentIndex(i)
                self.save_current()
        self.tabs.setCurrentIndex(current)

    def _goto_line(self):
        editor = self.tabs.currentWidget()
        if editor is None:
            return
        line, ok = QInputDialog.getInt(
            self, "Go to Line", "Line:", editor.lineFromPosition(editor.currentPos()) + 1,
            1, max(1, editor.lineCount()))
        if ok:
            editor.gotoLine(line - 1)
            editor.verticalCentreCaret()

    def _jump_to_matching_brace(self):
        editor = self.tabs.currentWidget()
        if editor is None:
            return
        pos = editor.currentPos()
        match = editor.braceMatch(pos, 0)
        if match < 0 and pos > 0:
            match = editor.braceMatch(pos - 1, 0)
        if match >= 0:
            editor.gotoPos(match)

    def _about(self):
        QMessageBox.about(
            self, "About Komodo",
            "KomodoEdit (Qt)\n\nA Qt/PySide6 rewrite of the Komodo Edit 12 user interface.",
        )

    def open_preferences(self):
        if self._prefs_dialog is None:
            self._prefs_dialog = PreferencesDialog(self)
        self._prefs_dialog.show()
        self._prefs_dialog.raise_()
        self._prefs_dialog.activateWindow()

    def _on_current_tab_changed(self, _index):
        self._history.view_changed(self.tabs.currentWidget())
        self._find_bar.set_editor(self.tabs.currentWidget())
        self._isearch_bar.set_editor(self.tabs.currentWidget())
        self.status_bar.set_editor(self.tabs.currentWidget())

    def start_incremental_search(self):
        self._isearch_bar.start(self.tabs.currentWidget())

    def _isearch_to_find_frame(self, pattern):
        """findController.convertToDialog(): carry the pattern over."""
        self._isearch_bar.close_bar()
        self.open_find_bar()
        self._find_bar.set_pattern(pattern)

    def open_find_bar(self, replace=False, search_in=None):
        self._find_bar.set_editor(self.tabs.currentWidget())
        self._find_bar.show_bar(replace=replace, search_in=search_in)

    def _return_focus_to_editor(self):
        editor = self.tabs.currentWidget()
        if editor is not None:
            # ScintillaEdit.setFocus(bool) shadows QWidget.setFocus(); see
            # the same note in _insert_completion.
            QWidget.setFocus(editor)

    def _build_find_results(self):
        self._all_find_hits = []  # unfiltered, so the filter box can re-apply without re-searching

        self._results_filter_edit = QLineEdit()
        self._results_filter_edit.setPlaceholderText("Filter results...")
        self._results_filter_edit.textChanged.connect(self._apply_find_results_filter)

        self._results_view = QTreeWidget()
        self._results_view.setHeaderLabels(["File", "Line", "Text"])
        self._results_view.itemDoubleClicked.connect(self._on_find_result_double_clicked)

        # Komodo's find results tab carries the undo for a Replace All.
        self._undo_replace_btn = QPushButton("Undo Replacements")
        self._undo_replace_btn.setEnabled(False)
        self._undo_replace_btn.clicked.connect(self.undo_last_find_replace)
        results_bar = QHBoxLayout()
        results_bar.addWidget(self._results_filter_edit, 1)
        results_bar.addWidget(self._undo_replace_btn)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(results_bar)
        layout.addWidget(self._results_view)

        # Komodo registers find results as "findresults_tabpanel<N>" in the
        # bottom pane, shown only once there are results.
        self.bottom_pane.add_widget(
            "findresults_tabpanel", "Find Results", container, "search", visible=False
        )

    def _build_vcs(self):
        # Source control isn't part of Komodo Edit; Komodo IDE shows it as
        # a side-pane widget, so it lives in the left pane here.
        self._vcs_panel = None
        self.left_pane.add_widget("scc-widget", "Git", QWidget(), "code-fork", visible=False)

        self._diff_view = QPlainTextEdit()
        self._diff_view.setReadOnly(True)
        font = self._diff_view.font()
        font.setFamily("monospace")
        self._diff_view.setFont(font)
        self.bottom_pane.add_widget("diff-widget", "Diff", self._diff_view, "code", visible=False)

    def _refresh_vcs(self):
        if self._project is not None and vcs.is_git_repo(self._project.base_dir):
            if self._vcs_panel is None or self._vcs_panel.base_dir != self._project.base_dir:
                self._vcs_panel = VCSPanel(self._project.base_dir, self)
                self._vcs_panel.diff_requested.connect(self._show_diff)
                self.left_pane.set_widget("scc-widget", self._vcs_panel)
            else:
                self._vcs_panel.refresh()
            self.left_pane.set_widget_visible("scc-widget", True)
        else:
            self.left_pane.set_widget_visible("scc-widget", False)
            self.bottom_pane.set_widget_visible("diff-widget", False)

    def _show_diff(self, path, staged):
        diff_text = vcs.git_diff(self._project.base_dir, path, staged=staged)
        self._diff_view.setPlainText(diff_text or "(no changes)")
        self.bottom_pane.set_label("diff-widget", f"Diff: {path}")
        self.bottom_pane.show_widget("diff-widget")

    def _build_debugger(self):
        # Multiple simultaneous debug sessions: keyed by script path, since
        # only one session per file makes sense (matches start_debugging's
        # own "already running for this file" guard). Only the "active"
        # session's stack/locals/watch panels are shown at a time --
        # switching the combo box changes which one; a background session
        # keeps running and auto-activates itself the next time it stops
        # (see _on_debug_stopped), same as most IDEs bring a breakpoint hit
        # to the foreground.
        self._debug_sessions = {}  # path -> DebugSession|DbgpSession
        self._active_debug_path = None
        self._debug_current_editors = {}  # path -> editor showing that session's execution-line marker

        self._debug_session_combo = QComboBox()
        self._debug_session_combo.currentIndexChanged.connect(self._on_debug_session_switched)

        self._stack_view = QTreeWidget()
        self._stack_view.setHeaderLabels(["Function", "Line"])
        self._stack_view.itemClicked.connect(self._on_stack_item_clicked)

        self._locals_view = QTreeWidget()
        self._locals_view.setHeaderLabels(["Name", "Type", "Value"])
        self._debug_locals_frame_index = 0
        self._locals_view.itemChanged.connect(self._on_locals_item_changed)

        self._watch_view = QTreeWidget()
        self._watch_view.setHeaderLabels(["Expression", "Value"])
        self._watch_expressions = []  # list[str], in display order

        self._watch_add_edit = QLineEdit()
        self._watch_add_edit.setPlaceholderText("Add watch expression...")
        self._watch_add_edit.returnPressed.connect(self._on_add_watch)
        remove_watch_btn = QPushButton("Remove")
        remove_watch_btn.clicked.connect(self._on_remove_watch)
        watch_add_row = QHBoxLayout()
        watch_add_row.addWidget(self._watch_add_edit, 1)
        watch_add_row.addWidget(remove_watch_btn)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._debug_session_combo)
        layout.addWidget(self._stack_view, 1)
        layout.addWidget(self._locals_view, 1)
        layout.addLayout(watch_add_row)
        layout.addWidget(self._watch_view, 1)

        # Komodo IDE's debug session widget ("debugsession<N>") sits in the
        # bottom pane, using the breakpoints widget's glyph here.
        self.bottom_pane.add_widget("breakpoints-tabpanel", "Debug", panel, "bug", visible=False)

    def toggle_breakpoint(self):
        editor = self.tabs.currentWidget()
        if editor is None:
            return
        editor.toggle_breakpoint(editor.lineFromPosition(editor.currentPos()))

    def _save_breakpoints_for(self, editor):
        if not editor.filepath:
            return
        abspath = os.path.abspath(editor.filepath)
        breakpoints = [
            {
                "line": line,
                "condition": editor.breakpoint_conditions.get(line),
                "ignore_count": editor.breakpoint_ignore_counts.get(line, 0),
            }
            for line in sorted(editor.breakpoints)
        ]
        breakpoint_store.save_breakpoints(self._breakpoints_path, abspath, breakpoints)

    def edit_breakpoint_condition(self):
        editor = self.tabs.currentWidget()
        if editor is None:
            return
        line = editor.lineFromPosition(editor.currentPos())
        dialog = BreakpointConditionDialog(
            condition=editor.breakpoint_conditions.get(line, ""),
            ignore_count=editor.breakpoint_ignore_counts.get(line, 0),
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            editor.set_breakpoint_condition(line, dialog.condition(), dialog.ignore_count())

    def start_debugging(self):
        editor = self.tabs.currentWidget()
        path = editor.filepath if editor is not None else None
        session_cls = None
        if path is not None:
            if path.endswith(".py"):
                session_cls = DebugSession
            elif path.endswith(".php"):
                session_cls = DbgpSession
        if session_cls is None:
            self.status_bar.showMessage(
                "Start Debugging benötigt eine gespeicherte .py- oder .php-Datei im aktiven Tab",
                4000,
            )
            return
        existing = self._debug_sessions.get(path)
        if existing is not None and existing.is_running():
            self.status_bar.showMessage("Für diese Datei läuft bereits eine Debug-Sitzung", 3000)
            return

        sess = session_cls(self)
        self._debug_sessions[path] = sess
        self._connect_session_signals(path, sess)

        self._debug_session_combo.blockSignals(True)
        self._debug_session_combo.addItem(os.path.basename(path), path)
        self._debug_session_combo.setCurrentIndex(self._debug_session_combo.count() - 1)
        self._debug_session_combo.blockSignals(False)
        self._active_debug_path = path
        self._stack_view.clear()
        self._locals_view.clear()

        # bdb (Python) and DBGP (PHP) both use 1-based line numbers;
        # Scintilla's own line indices (editor.breakpoints) are 0-based.
        breakpoints = [
            {
                "line": line + 1,
                "condition": editor.breakpoint_conditions.get(line),
                "ignore_count": editor.breakpoint_ignore_counts.get(line, 0),
            }
            for line in sorted(editor.breakpoints)
        ]
        sess.start(path, breakpoints)

        self._set_debug_actions_running(True)
        self.bottom_pane.show_widget("breakpoints-tabpanel")

    def _connect_session_signals(self, path, sess):
        # Every handler below is path-tagged (via the `p=path` default-arg
        # trick, since PySide6 signals don't carry any sender identity on
        # their own) so a background session's events don't clobber the
        # currently active session's panels -- only `stopped` is allowed to
        # change which session is active (see _on_debug_stopped).
        sess.stopped.connect(lambda reason, stack, p=path: self._on_debug_stopped(p, reason, stack))
        sess.localsReceived.connect(
            lambda frame_index, variables, p=path: self._on_debug_locals(p, frame_index, variables)
        )
        sess.watchResult.connect(
            lambda expr, text, is_error, p=path: self._on_watch_result(p, expr, text, is_error)
        )
        sess.localError.connect(lambda message, p=path: self._on_debug_local_error(p, message))
        sess.output.connect(lambda text, is_stderr, p=path: self._on_debug_output(p, text, is_stderr))
        sess.terminated.connect(lambda exit_code, p=path: self._on_debug_terminated(p, exit_code))

    def _current_session(self):
        return self._debug_sessions.get(self._active_debug_path)

    def _on_debug_session_switched(self, index):
        self._active_debug_path = self._debug_session_combo.itemData(index) if index >= 0 else None
        # v1 doesn't cache each session's last-known stack/locals across a
        # switch -- panels go blank until that session's own next `stopped`
        # (or a manual stack-item click) repopulates them.
        self._stack_view.clear()
        self._locals_view.blockSignals(True)
        self._locals_view.clear()
        self._locals_view.blockSignals(False)
        for i in range(self._watch_view.topLevelItemCount()):
            self._watch_view.topLevelItem(i).setText(1, "")

    def _set_debug_actions_running(self, running):
        self._start_debug_action.setEnabled(True)  # starting a session for a *different* file is fine
        self._continue_action.setEnabled(running)
        self._step_over_action.setEnabled(running)
        self._step_into_action.setEnabled(running)
        self._step_out_action.setEnabled(running)
        self._stop_debug_action.setEnabled(running)

    def _debug_continue(self):
        session = self._current_session()
        if session is not None:
            session.continue_()

    def _debug_step_over(self):
        session = self._current_session()
        if session is not None:
            session.step_over()

    def _debug_step_into(self):
        session = self._current_session()
        if session is not None:
            session.step_into()

    def _debug_step_out(self):
        session = self._current_session()
        if session is not None:
            session.step_out()

    def _debug_stop(self):
        session = self._current_session()
        if session is not None:
            session.stop()

    def _on_debug_stopped(self, path, _reason, stack):
        if self._active_debug_path != path:
            # Bring a background session's breakpoint hit to the front,
            # same as most IDEs -- without re-triggering
            # _on_debug_session_switched's panel-clearing (redundant, since
            # this method repopulates them immediately below anyway).
            idx = self._debug_session_combo.findData(path)
            if idx != -1:
                self._debug_session_combo.blockSignals(True)
                self._debug_session_combo.setCurrentIndex(idx)
                self._debug_session_combo.blockSignals(False)
            self._active_debug_path = path

        self._stack_view.clear()
        for entry in stack:
            self._stack_view.addTopLevelItem(
                QTreeWidgetItem([entry["function"], str(entry["line"])])
            )
        old_editor = self._debug_current_editors.get(path)
        if old_editor is not None:
            old_editor.clear_current_line()
            del self._debug_current_editors[path]
        if stack:
            top = stack[0]
            self.open_file(top["filename"])
            editor = self.tabs.currentWidget()
            if editor is not None:
                editor.set_current_line(top["line"] - 1)  # bdb is 1-based
                self._debug_current_editors[path] = editor
            session = self._debug_sessions.get(path)
            if session is not None:
                session.get_locals(0)
                self._refresh_watches(0)

    def _on_stack_item_clicked(self, _item, _column):
        session = self._current_session()
        if session is not None:
            frame_index = self._stack_view.indexOfTopLevelItem(_item)
            session.get_locals(frame_index)
            self._refresh_watches(frame_index)

    def _on_debug_locals(self, path, frame_index, variables):
        if path != self._active_debug_path:
            return
        self._debug_locals_frame_index = frame_index
        # blockSignals so repopulating the tree doesn't re-trigger
        # itemChanged (and thus a spurious set_local() round-trip) for
        # every row -- only a real user edit should do that.
        self._locals_view.blockSignals(True)
        self._locals_view.clear()
        for var in variables:
            item = QTreeWidgetItem([var["name"], var["type"], var["value"]])
            # Editable as a whole (Qt has no clean per-column editable
            # flag for QTreeWidgetItem) -- _on_locals_item_changed ignores
            # edits to columns other than Value, so an accidental edit to
            # Name/Type is a harmless no-op that a subsequent refresh
            # overwrites.
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self._locals_view.addTopLevelItem(item)
        self._locals_view.blockSignals(False)

    def _on_locals_item_changed(self, item, column):
        session = self._current_session()
        if column != 2 or session is None:
            return
        name = item.text(0)
        value_expr = item.text(2)
        session.set_local(self._debug_locals_frame_index, name, value_expr)

    def _on_debug_local_error(self, path, message):
        if path != self._active_debug_path:
            return
        self.status_bar.showMessage(message, 5000)

    def _on_add_watch(self):
        expr = self._watch_add_edit.text().strip()
        if not expr or expr in self._watch_expressions:
            self._watch_add_edit.clear()
            return
        self._watch_add_edit.clear()
        self._watch_expressions.append(expr)
        self._watch_view.addTopLevelItem(QTreeWidgetItem([expr, ""]))
        session = self._current_session()
        if session is not None and session.is_running():
            session.evaluate(expr, 0)

    def _on_remove_watch(self):
        item = self._watch_view.currentItem()
        if item is None:
            return
        expr = item.text(0)
        if expr in self._watch_expressions:
            self._watch_expressions.remove(expr)
        self._watch_view.takeTopLevelItem(self._watch_view.indexOfTopLevelItem(item))

    def _refresh_watches(self, frame_index):
        session = self._current_session()
        if session is None:
            return
        for expr in self._watch_expressions:
            session.evaluate(expr, frame_index)

    def _on_watch_result(self, path, expr, text, _is_error):
        if path != self._active_debug_path:
            return
        for i in range(self._watch_view.topLevelItemCount()):
            item = self._watch_view.topLevelItem(i)
            if item.text(0) == expr:
                item.setText(1, text)

    def _on_debug_output(self, path, text, _is_stderr):
        stripped = text.rstrip("\n")
        if not stripped:
            return
        # Prefix with the originating script only when more than one
        # session is (or, at the moment this fires, was still) running --
        # keeps the common single-session case's output uncluttered.
        if len(self._debug_sessions) > 1:
            stripped = f"[{os.path.basename(path)}] {stripped}"
        self._output_view.appendPlainText(stripped)

    def _on_debug_terminated(self, path, exit_code):
        editor = self._debug_current_editors.pop(path, None)
        if editor is not None:
            editor.clear_current_line()
        self._debug_sessions.pop(path, None)
        idx = self._debug_session_combo.findData(path)
        if idx != -1:
            # If `path` was the active selection, removeItem's own
            # currentIndexChanged fires _on_debug_session_switched, which
            # clears the panels (or repopulates the combo box's newly
            # current session's -- empty -- panel state); if it wasn't
            # active, nothing else needs to happen here.
            self._debug_session_combo.removeItem(idx)
        self._set_debug_actions_running(bool(self._debug_sessions))
        self.status_bar.showMessage(
            f"{os.path.basename(path)}: Debuggee exited with code {exit_code}", 5000
        )

    def _default_search_dir(self):
        if self._project is not None:
            return self._project.base_dir
        return self._project_root_path

    def open_find_in_files(self):
        """cmd_findInFiles: the find frame in "Files" mode."""
        self.open_find_bar(search_in=SEARCH_FILES)

    def _on_find_in_files_replaced(self, undo_record):
        self._last_replace_undo = undo_record
        self._undo_replace_btn.setEnabled(bool(undo_record))

    def undo_last_find_replace(self):
        if not self._last_replace_undo:
            return
        find_in_files.undo_replacements(self._last_replace_undo)
        # Reload any of the restored files that happen to be open so the
        # editor doesn't keep showing the (now reverted) replaced text.
        restored_paths = {path for path, _ in self._last_replace_undo}
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if editor.filepath in restored_paths:
                try:
                    with open(editor.filepath, "r", encoding="utf-8", errors="replace") as f:
                        editor.setText(f.read())
                    editor.setSavePoint()  # matches disk again
                except OSError:
                    continue
        self.status_bar.showMessage(
            f"Reverted {len(self._last_replace_undo)} file(s)", 4000
        )
        self._last_replace_undo = []
        self._undo_replace_btn.setEnabled(False)

    def _on_find_in_files_hits(self, hits):
        self._all_find_hits = hits
        self._results_filter_edit.clear()  # also triggers _apply_find_results_filter
        self.bottom_pane.show_widget("findresults_tabpanel")
        self.status_bar.showMessage(f"{len(hits)} match(es) found", 5000)

    def _apply_find_results_filter(self, text):
        self._results_view.clear()
        needle = text.strip().lower()
        base_dir = self._default_search_dir()
        for hit in self._all_find_hits:
            rel_path = os.path.relpath(hit.path, base_dir)
            if needle and needle not in rel_path.lower() and needle not in hit.line_text.lower():
                continue
            item = QTreeWidgetItem([rel_path, str(hit.line_no), hit.line_text.strip()])
            item.setData(0, Qt.ItemDataRole.UserRole, hit)
            self._results_view.addTopLevelItem(item)
        for column in range(3):
            self._results_view.resizeColumnToContents(column)

    def _on_find_result_double_clicked(self, item, _column):
        hit = item.data(0, Qt.ItemDataRole.UserRole)
        if hit is None:
            return
        self.open_file(hit.path)
        editor = self.tabs.currentWidget()
        if editor is None:
            return
        line = hit.line_no - 1
        start = editor.findColumn(line, hit.column)
        end = editor.findColumn(line, hit.column + (hit.match_end - hit.match_start))
        editor.setSel(start, end)
        editor.ensureVisible(line)
        editor.scrollCaret()
        QWidget.setFocus(editor)

    def _build_project_tree(self, root_path):
        self._project = None
        self._project_root_path = root_path
        self._fs_model = None
        self._project_tree = QTreeView()
        self._project_tree.setHeaderHidden(True)
        self._project_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._project_tree.customContextMenuRequested.connect(
            self._show_project_context_menu
        )
        # One connection for the tree's whole lifetime -- _on_tree_double_clicked
        # dispatches on self._project instead of us disconnecting/reconnecting
        # a different handler each time the dock switches between folder-
        # browser and project-tree mode.
        self._project_tree.doubleClicked.connect(self._on_tree_double_clicked)

        # Komodo's Places widget (modules/places), first in the left pane.
        self.left_pane.add_widget("placesViewbox", "Places", self._project_tree)

        self._show_folder_browser(root_path)

    def _show_folder_browser(self, root_path):
        """No-project fallback: a plain live folder browser, same behavior
        this dock always had before Projects existed -- legacy Komodo can
        run without any project open too."""
        self._fs_model = QFileSystemModel(self)
        self._fs_model.setRootPath(root_path)
        self._fs_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        self._project_tree.setModel(self._fs_model)
        self._project_tree.setRootIndex(self._fs_model.index(root_path))
        for column in (1, 2, 3):
            self._project_tree.hideColumn(column)
        self.left_pane.set_label("placesViewbox", "Places")

    def _show_project_tree(self):
        self._fs_model = None
        self._project_tree.setModel(build_project_model(self._project, self._git_status_map()))
        self.left_pane.set_label("placesViewbox", f"Places: {self._project.name}")

    def _git_status_map(self):
        if self._project is None or not vcs.is_git_repo(self._project.base_dir):
            return {}
        return {
            s.path: f"{s.index_code}{s.worktree_code}"
            for s in vcs.git_status(self._project.base_dir)
        }

    def _on_tree_double_clicked(self, index):
        if self._project is None:
            self._open_from_tree(self._fs_model, index)
            return
        if not index.data(IS_FILE_ROLE):
            return  # a folder/group row -- let the view's expand/collapse handle it
        node = index.data(NODE_ROLE)
        self.open_file(os.path.join(self._project.base_dir, node.url))

    def new_project(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "New Project", filter=f"Komodo Project (*{project_model.PROJECT_EXTENSION})"
        )
        if not path:
            return
        if not path.endswith(project_model.PROJECT_EXTENSION):
            path += project_model.PROJECT_EXTENSION
        name = os.path.splitext(os.path.basename(path))[0]
        self._project = project_model.create_project(path, name)
        mru.add(get_global_prefs(), mru.PROJECT_LIST, os.path.abspath(path))
        self._show_project_tree()
        self._refresh_toolbox()
        self._refresh_vcs()
        self._restore_session()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", filter=f"Komodo Project (*{project_model.PROJECT_EXTENSION})"
        )
        if path:
            self.open_project_path(path)

    def open_project_path(self, path):
        try:
            self._project = project_model.load_project(path)
        except OSError as exc:
            QMessageBox.warning(self, "Open Project", f"Could not open {path}:\n{exc}")
            return
        mru.add(get_global_prefs(), mru.PROJECT_LIST, os.path.abspath(path))
        self._show_project_tree()
        self._refresh_toolbox()
        self._refresh_vcs()
        self._restore_session()

    def close_project(self):
        if self._project is None:
            return
        self._save_session()
        self._project = None
        self._show_folder_browser(self._project_root_path)
        self._refresh_toolbox()
        self._refresh_vcs()

    def _show_project_context_menu(self, pos):
        menu = QMenu(self)
        if self._project is None:
            menu.addAction(icons.icon("archive"), "New Project...").triggered.connect(
                self.new_project
            )
            menu.addAction(icons.icon("folder2"), "Open Project...").triggered.connect(
                self.open_project
            )
            menu.exec(self._project_tree.viewport().mapToGlobal(pos))
            return

        index = self._project_tree.indexAt(pos)
        node = index.data(NODE_ROLE) if index.isValid() else None

        menu.addAction(icons.icon("file-plus2"), "Add File...").triggered.connect(
            self._add_file_to_project
        )
        menu.addAction(icons.icon("folder-plus"), "Add Folder...").triggered.connect(
            self._add_folder_to_project
        )
        menu.addAction(icons.icon("plus-square"), "New Group...").triggered.connect(
            self._add_group_to_project
        )
        if node is not None:
            menu.addSeparator()
            menu.addAction(
                icons.icon("minus-square"), "Remove from Project"
            ).triggered.connect(lambda: self._remove_project_node(node))
        menu.addSeparator()
        menu.addAction(icons.icon("close"), "Close Project").triggered.connect(
            self.close_project
        )
        menu.exec(self._project_tree.viewport().mapToGlobal(pos))

    def _add_file_to_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add File to Project")
        if path:
            project_model.add_file(self._project, path)
            self._show_project_tree()

    def _add_folder_to_project(self):
        path = QFileDialog.getExistingDirectory(self, "Add Folder to Project")
        if path:
            project_model.import_folder_snapshot(self._project, path)
            self._show_project_tree()

    def _add_group_to_project(self):
        name, ok = QInputDialog.getText(self, "New Group", "Name:")
        if ok and name:
            project_model.add_group(self._project, name)
            self._show_project_tree()

    def _remove_project_node(self, node):
        project_model.remove_node(self._project, node)
        self._show_project_tree()

    def _build_toolbox(self):
        config_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppConfigLocation
        )
        self._toolbox_root = os.path.join(config_dir, "toolbox")
        toolbox_model.ensure_default_toolbox(self._toolbox_root)
        self._session_path = os.path.join(config_dir, session.FILENAME)
        self._breakpoints_path = os.path.join(config_dir, breakpoint_store.FILENAME)

        self._toolbox_view = QTreeView()
        self._toolbox_view.setHeaderHidden(True)
        self._toolbox_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._toolbox_view.customContextMenuRequested.connect(
            self._show_toolbox_context_menu
        )
        self._toolbox_view.doubleClicked.connect(self._on_toolbox_double_clicked)
        self._refresh_toolbox()

        self.right_pane.add_widget("toolbox2viewbox", "Toolbox", self._toolbox_view)

        self._output_view = QPlainTextEdit()
        self._output_view.setReadOnly(True)
        self.bottom_pane.add_widget("runoutput-desc-tabpanel", "Command Output", self._output_view)

    def _refresh_toolbox(self):
        project_toolbox_root = None
        if self._project is not None:
            project_toolbox_root = os.path.join(self._project.base_dir, ".komodotools")
            os.makedirs(project_toolbox_root, exist_ok=True)
        self._toolbox_view.setModel(
            build_toolbox_model(self._toolbox_root, project_toolbox_root)
        )

    def _on_toolbox_double_clicked(self, index):
        item = index.data(TOOLBOX_ITEM_ROLE)
        if item is None:
            return  # a folder row -- let the view's default expand/collapse handle it
        if item.type == toolbox_model.SNIPPET:
            self._insert_snippet(item)
        elif item.type == toolbox_model.COMMAND:
            self._run_toolbox_command(item)

    def _insert_snippet(self, item):
        editor = self.tabs.currentWidget()
        if editor is None:
            return
        pos = editor.currentPos()
        editor.insertText(pos, item.value)
        new_pos = pos + len(item.value.encode("utf-8"))
        editor.setSel(new_pos, new_pos)
        QWidget.setFocus(editor)

    def _run_toolbox_command(self, item):
        proc = QProcess(self)
        if item.cwd:
            proc.setWorkingDirectory(item.cwd)
        proc.finished.connect(
            lambda code, _status, proc=proc, item=item: self._on_command_finished(
                proc, item, code
            )
        )
        self._output_view.appendPlainText(f"$ {item.value}")
        self._running_processes.append(proc)
        proc.start("/bin/sh", ["-c", item.value])

    def _on_command_finished(self, proc, item, exit_code):
        output = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        errors = bytes(proc.readAllStandardError()).decode("utf-8", errors="replace")
        if output:
            self._output_view.appendPlainText(output.rstrip("\n"))
        if errors:
            self._output_view.appendPlainText(errors.rstrip("\n"))
        self._output_view.appendPlainText(f"[{item.name}] exited with code {exit_code}\n")
        self._running_processes.remove(proc)
        proc.deleteLater()

    def _show_toolbox_context_menu(self, pos):
        index = self._toolbox_view.indexAt(pos)
        if index.isValid():
            item = index.data(TOOLBOX_ITEM_ROLE)
            target_folder = index.data(FOLDER_PATH_ROLE)
            delete_path = item.path if item is not None else target_folder
        else:
            target_folder = self._toolbox_root
            delete_path = None

        menu = QMenu(self)
        menu.addAction(icons.svg_icon("snippet.svg"), "New Snippet...").triggered.connect(
            lambda: self._create_toolbox_item(target_folder, toolbox_model.SNIPPET)
        )
        menu.addAction(icons.svg_icon("command.svg"), "New Command...").triggered.connect(
            lambda: self._create_toolbox_item(target_folder, toolbox_model.COMMAND)
        )
        menu.addAction(icons.icon("folder-plus"), "New Folder...").triggered.connect(
            lambda: self._create_toolbox_folder(target_folder)
        )
        menu.addSeparator()
        edit_item = index.data(TOOLBOX_ITEM_ROLE) if index.isValid() else None
        edit_action = menu.addAction(icons.icon("pencil-square"), "Edit...")
        edit_action.setEnabled(edit_item is not None)
        edit_action.triggered.connect(lambda: self._edit_toolbox_item(edit_item))
        delete_action = menu.addAction(icons.icon("trash"), "Delete")
        delete_action.setEnabled(delete_path is not None)
        delete_action.triggered.connect(lambda: self._delete_toolbox_entry(delete_path))
        menu.addSeparator()
        menu.addAction(icons.icon("refresh"), "Refresh").triggered.connect(
            self._refresh_toolbox
        )
        menu.exec(self._toolbox_view.viewport().mapToGlobal(pos))

    def _create_toolbox_item(self, folder_path, item_type):
        dialog = ToolboxItemDialog(item_type, editing_name=True, parent=self)
        if dialog.exec() != ToolboxItemDialog.DialogCode.Accepted:
            return
        name = dialog.name()
        if not name:
            return
        toolbox_model.create_item(folder_path, name, item_type, dialog.value(), dialog.cwd())
        self._refresh_toolbox()

    def _edit_toolbox_item(self, item):
        # Matches legacy Komodo: snippets (and macros, not implemented here)
        # open in the main editor via a virtual URL scheme so the full
        # editor is available; commands stay on a small properties-style
        # dialog (legacy has no in-editor command-edit path at all, only
        # "Edit Properties").
        if item.type == toolbox_model.SNIPPET:
            self._open_snippet_editor(item)
            return
        dialog = ToolboxItemDialog(
            item.type,
            name=item.name,
            value=item.value,
            cwd=item.cwd,
            editing_name=False,
            parent=self,
        )
        if dialog.exec() != ToolboxItemDialog.DialogCode.Accepted:
            return
        toolbox_model.update_item(item.path, item.name, item.type, dialog.value(), dialog.cwd())
        self._refresh_toolbox()

    def _open_snippet_editor(self, item):
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            existing = editor.toolbox_item
            if existing is not None and existing.path == item.path:
                self.tabs.setCurrentIndex(i)
                return

        editor = CodeEditor(self)
        editor.setText(item.value)
        editor.emptyUndoBuffer()
        editor.setSavePoint()
        editor.toolbox_item = item
        index = self._add_editor_tab(editor, f"Snippet: {item.name}")
        self.tabs.setTabToolTip(index, item.path)
        self.tabs.setCurrentIndex(index)

    def _create_toolbox_folder(self, parent_path):
        name, ok = QInputDialog.getText(self, "New Folder", "Name:")
        if ok and name:
            toolbox_model.create_folder(parent_path, name)
            self._refresh_toolbox()

    def _delete_toolbox_entry(self, path):
        reply = QMessageBox.question(
            self, "Delete", f"Delete {os.path.basename(path)}?"
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            toolbox_model.delete_path(path)
        except OSError as exc:
            QMessageBox.warning(self, "Delete", f"Could not delete {path}:\n{exc}")
            return
        self._refresh_toolbox()

    def _build_codeintel(self):
        # Drives the codeintel3 OOP engine (Python 3 port of codeintel2,
        # runs in-process-family via a plain subprocess of this same
        # interpreter) via the OOP protocol -- see codeintel_client.py.
        # Scoped to saved Python files only for this MVP.
        self.codeintel = CodeIntelClient(parent=self)
        self.codeintel.errorOccurred.connect(
            lambda msg: self.status_bar.showMessage(msg, 5000)
        )
        self.completion_popup = CompletionPopup(self)
        self.completion_popup.accepted.connect(self._insert_completion)
        self._pending_editor = None
        self._pending_pos = None


    def trigger_autocomplete(self):
        editor = self.tabs.currentWidget()
        if editor is None:
            return
        path = editor.filepath
        if not path:
            self.status_bar.showMessage(
                "Autocomplete nur für gespeicherte Python-Dateien (Datei erst speichern)",
                4000,
            )
            return
        pos = editor.currentPos()
        text = editor.current_text()
        # The OOP round-trip is async and, on a cold codeintel3 cache (first
        # import-resolving request in a session -- has to scan site-packages
        # and parse the ~9MB stdlib catalog), can take several real seconds
        # with otherwise zero visual feedback. Show something immediately so
        # it doesn't look stuck, and snapshot the edit generation so a
        # response that arrives after further edits gets dropped instead of
        # being applied at a now-wrong position (see _on_eval).
        self.status_bar.showMessage("Suche Vervollständigungen…")
        generation = editor.edit_generation
        self.codeintel.scan_document(
            path, text, "Python",
            callback=lambda resp: self._on_scanned(editor, path, pos, generation),
        )

    def _drop_stale_completion(self):
        # Called wherever an in-flight completion request turns out to be
        # stale (the buffer changed since it was triggered). Only clears
        # the "Suche Vervollständigungen…" placeholder, not some unrelated
        # message that may have shown up in the meantime.
        if self.status_bar.currentMessage() == "Suche Vervollständigungen…":
            self.status_bar.clearMessage()

    def _on_scanned(self, editor, path, pos, generation):
        if editor.edit_generation != generation:
            self._drop_stale_completion()
            return
        self.codeintel.trg_from_pos(
            path, pos, lambda resp: self._on_trg(editor, pos, resp, generation), implicit=False
        )

    def _on_trg(self, editor, pos, resp, generation):
        if editor.edit_generation != generation:
            self._drop_stale_completion()
            return
        trg = resp.get("trg")
        if not trg:
            self.status_bar.showMessage("Keine Vervollständigung an dieser Position", 3000)
            return
        self.codeintel.eval_trigger(trg, lambda resp: self._on_eval(editor, pos, resp, generation))

    def _on_eval(self, editor, pos, resp, generation):
        if editor.edit_generation != generation:
            # The buffer changed while this request was in flight -- pos
            # (and possibly the whole trigger) no longer applies. Drop it
            # silently rather than inserting/popping up at a stale position;
            # the user can just re-trigger (fast now that the codeintel3
            # process has warmed its caches for this session).
            self._drop_stale_completion()
            return
        cplns = resp.get("cplns")
        if not cplns:
            self.status_bar.showMessage(
                resp.get("message", "Keine Vervollständigungen gefunden"), 3000
            )
            return
        self.status_bar.clearMessage()
        self._pending_editor = editor
        self._pending_pos = pos
        x = editor.pointXFromPosition(pos)
        y = editor.pointYFromPosition(pos) + 20
        # completion_popup is a plain child widget of this window (see its
        # docstring for why -- not a top-level Qt.WindowType.Popup), so it
        # needs a position in *this window's* coordinate system, not a
        # global/screen one.
        local_pos = self.mapFromGlobal(editor.mapToGlobal(QPoint(x, y)))
        self.completion_popup.show_completions(cplns, local_pos)

    def _insert_completion(self, name):
        editor, pos = self._pending_editor, self._pending_pos
        if editor is None or pos is None:
            return
        editor.insertText(pos, name)
        new_pos = pos + len(name.encode("utf-8"))
        editor.setSel(new_pos, new_pos)
        # ScintillaEdit.setFocus(bool) shadows QWidget.setFocus() (it's the
        # SCI_SETFOCUS message, an unrelated internal flag) -- call the
        # QWidget version explicitly to actually give it keyboard focus.
        QWidget.setFocus(editor)

    def closeEvent(self, event):
        if not self._offer_to_save([self.tabs.widget(i) for i in range(self.tabs.count())]):
            event.ignore()
            return
        self._save_workspace()
        for path in reversed(self._open_file_paths()):
            mru.add(get_global_prefs(), mru.FILE_LIST, os.path.abspath(path))
        if self._project is not None:
            self._save_session()
        for sess in list(self._debug_sessions.values()):
            if sess.is_running():
                sess.stop()
        self.codeintel.shutdown()
        self._history.close()
        super().closeEvent(event)

    def _restore_session(self):
        open_files, active_file = session.load_session(self._session_path, self._project.path)
        # Remember the blank "untitled" placeholder tab (if that's all that's
        # open) so it can be dropped *after* the real files are open --
        # closing it first would trip _close_tab's "keep at least one tab"
        # safety net and just recreate another blank tab in its place.
        placeholder_index = None
        if open_files and self.tabs.count() == 1:
            placeholder = self.tabs.widget(0)
            if placeholder.filepath is None and not placeholder.current_text():
                placeholder_index = 0
        for path in open_files:
            if os.path.isfile(path):
                self.open_file(path)
        if placeholder_index is not None and self.tabs.count() > 1:
            self._close_tab(placeholder_index)
        if active_file:
            for i in range(self.tabs.count()):
                if self.tabs.widget(i).filepath == active_file:
                    self.tabs.setCurrentIndex(i)
                    break

    def _save_session(self):
        open_files = [
            self.tabs.widget(i).filepath
            for i in range(self.tabs.count())
            if self.tabs.widget(i).filepath
        ]
        current = self.tabs.currentWidget()
        active_file = current.filepath if current is not None else None
        session.save_session(self._session_path, self._project.path, open_files, active_file)

    def _open_from_tree(self, model, index):
        path = model.filePath(index)
        if os.path.isfile(path):
            self.open_file(path)

    def _add_editor_tab(self, editor, title):
        """A file tab as scrolltabs.xml#file-status-tab draws it: the
        language's file icon, the name, and a `.tab-close-button` glyph."""
        index = self.tabs.addTab(editor, title)
        editor.tab_title = title
        editor.savePointChanged.connect(lambda _dirty, ed=editor: self._update_tab_title(ed))
        self._history.watch(editor)
        self._update_tab_icon(editor)
        css = komodo_stylesheet()
        close = QToolButton()
        close.setObjectName("tab-close-button")
        close.setIcon(icons.glyph(
            icons.css_glyph(css.value(".tab-close-button:before", "content")),
            int(css.value(".tab-close-button", "font-size", "16px").rstrip("px")),
            QColor(css.value(".tab-close-button:before", "color")),
        ))
        close.setToolTip("Close")
        close.clicked.connect(lambda _c=False, e=editor: self._close_tab(self.tabs.indexOf(e)))
        self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, close)
        return index

    def _update_tab_title(self, editor):
        """scrolltabs.xml: a separate "*" label shows unless the tab is
        clean (views-tabbed.xml updateDirtyStatus)."""
        index = self.tabs.indexOf(editor)
        if index >= 0:
            self.tabs.setTabText(index, editor.tab_title + ("*" if editor.modify() else ""))

    def _revert(self):
        """views-editor.p.xml revert(): ask, then koDocument.revert(),
        which reloads as one undoable edit keeping caret and scroll."""
        editor = self.tabs.currentWidget()
        if editor is None or not editor.filepath:
            return
        answer = QMessageBox.question(
            self, "Komodo",
            f"Do you wish to revert to the last saved version of '{os.path.basename(editor.filepath)}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with open(editor.filepath, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as exc:
            QMessageBox.warning(self, "Revert", f"Could not read {editor.filepath}:\n{exc}")
            return
        pos, anchor = editor.currentPos(), editor.anchor()
        first_visible, x_offset = editor.firstVisibleLine(), editor.xOffset()
        editor.beginUndoAction()
        editor.setText(text)
        editor.endUndoAction()
        length = editor.textLength()
        editor.setSel(min(anchor, length), min(pos, length))
        editor.setFirstVisibleLine(first_visible)
        editor.setXOffset(x_offset)
        editor.setSavePoint()

    def _update_tab_icon(self, editor):
        self.tabs.setTabIcon(self.tabs.indexOf(editor), file_icon(editor.language_name()))

    def new_file(self):
        editor = CodeEditor(self)
        editor.set_lexer_by_name("python")
        index = self._add_editor_tab(editor, "untitled")
        self.tabs.setCurrentIndex(index)
        editor.filepath = None

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File")
        if path:
            self.open_file(path)

    def open_file(self, path):
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if editor.filepath == path:
                self.tabs.setCurrentIndex(i)
                return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as exc:
            QMessageBox.warning(self, "Open File", f"Could not open {path}:\n{exc}")
            return

        editor = CodeEditor(self)
        editor.setText(text)
        # koDocument._loadfile: loading isn't an undoable edit, and the
        # buffer starts clean.
        editor.emptyUndoBuffer()
        editor.setSavePoint()
        editor.set_lexer_for_filename(path, text)
        editor.filepath = path
        abspath = os.path.abspath(path)
        editor.restore_breakpoints(breakpoint_store.load_breakpoints(self._breakpoints_path, abspath))
        editor.breakpointsChanged.connect(lambda ed=editor: self._save_breakpoints_for(ed))

        index = self._add_editor_tab(editor, os.path.basename(path))
        self.tabs.setTabToolTip(index, path)
        self.tabs.setCurrentIndex(index)

    def save_current(self):
        editor = self.tabs.currentWidget()
        if editor is not None:
            self._save_editor(editor)

    def save_current_as(self):
        editor = self.tabs.currentWidget()
        if editor is not None:
            self._save_editor_as(editor)

    def _save_editor(self, editor):
        """Returns whether the buffer got saved (False on cancel/error)."""
        item = editor.toolbox_item
        if item is not None:
            new_value = editor.current_text()
            toolbox_model.update_item(item.path, item.name, item.type, new_value, item.cwd)
            item.value = new_value
            editor.setSavePoint()
            return True
        if not editor.filepath:
            return self._save_editor_as(editor)
        return self._write(editor, editor.filepath)

    def _save_editor_as(self, editor):
        path, _ = QFileDialog.getSaveFileName(self, "Save File As")
        if not path or not self._write(editor, path):
            return False
        editor.filepath = path
        editor.set_lexer_for_filename(path, editor.current_text())
        editor.tab_title = os.path.basename(path)
        self._update_tab_title(editor)
        self.tabs.setTabToolTip(self.tabs.indexOf(editor), path)
        self._update_tab_icon(editor)
        self.status_bar.refresh()
        return True

    def _write(self, editor, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(editor.current_text())
        except OSError as exc:
            QMessageBox.warning(self, "Save File", f"Could not save {path}:\n{exc}")
            return False
        editor.setSavePoint()
        return True

    def _offer_to_save_editor(self, editor):
        """views-editor.p.xml close(): "Save changes to X?" for a dirty
        buffer. Returns False if the close should be cancelled."""
        if not editor.modify():
            return True
        self.tabs.setCurrentWidget(editor)
        answer = QMessageBox.question(
            self, "Komodo", f"Save changes to {editor.tab_title}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Yes:
            return self._save_editor(editor)
        return True

    def _offer_to_save(self, editors):
        """viewManager.offerToSave: one list of all dirty buffers, every
        one selected, with Save / Do Not Save / Cancel. Returns False if
        cancelled (or a save failed)."""
        dirty = [e for e in editors if e.modify()]
        if not dirty:
            return True
        dialog = SaveModifiedDialog([self._editor_display_path(e) for e in dirty], self)
        selected = dialog.ask()
        if selected is None:
            return False
        return all(self._save_editor(dirty[i]) for i in selected)

    def _editor_display_path(self, editor):
        return editor.filepath or editor.tab_title

    def _close_tab(self, index, offer_to_save=True):
        if index < 0:
            return False
        widget = self.tabs.widget(index)
        if offer_to_save and not self._offer_to_save_editor(widget):
            return False
        self._history.view_closing(widget)
        if widget.filepath:
            # views-editor.p.xml closeUnconditionally: files enter the MRU
            # when their view closes.
            mru.add(get_global_prefs(), mru.FILE_LIST, os.path.abspath(widget.filepath))
            self._closed_tabs.note(widget.filepath)
        self.tabs.removeTab(index)
        widget.deleteLater()
        if self.tabs.count() == 0:
            self.new_file()
        return True
