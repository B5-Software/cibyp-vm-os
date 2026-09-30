"""Behavior regression tests for desktop state, real file operations and safe math."""
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote
sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'recipes/overlay/desktop/lib'))
import campus_core as core
import campus_trash as trash


def set_preference(directory, key):
    core.CONFIG_DIR, core.CONFIG_FILE = Path(directory), Path(directory)/'desktop.json'
    core.update_config(**{key: True})


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.patch = patch.multiple(core, CONFIG_DIR=self.root, CONFIG_FILE=self.root/'desktop.json')
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temporary.cleanup()

    def test_invalid_preferences_are_normalized(self):
        core.CONFIG_FILE.write_text(json.dumps({'theme': 'broken', 'accent': 'broken', 'wallpaper': None, 'pinned': ['files', 'files', {}, 7]}))
        value = core.load_config()
        self.assertEqual((value['theme'], value['accent'], value['wallpaper'], value['pinned']), ('light', 'blue', 'campus', ['files']))

    def test_corrupt_preferences_use_defaults(self):
        core.CONFIG_FILE.write_text('{bad')
        self.assertEqual(core.load_config()['theme'], 'light')

    def test_app_colors_are_exact_and_preserve_desktop_preferences(self):
        core.update_config(wallpaper='notebook', pinned=['files', 'calc'])
        core.update_config(theme='dark', accent_color='#A55EEA', background_color='#1B1433', appearance_source='app')
        state = core.load_config()
        self.assertEqual(core.accent_color(state), '#a55eea')
        self.assertEqual(core.appearance_palette(state)['bg'], '#1b1433')
        self.assertEqual(core.appearance_palette(state)['surface'], '#2f2847')
        self.assertEqual((state['wallpaper'], state['pinned']), ('notebook', ['files', 'calc']))

    def test_custom_color_validation_and_light_background_shades(self):
        core.update_config(accent_color='red; background: black', background_color='#F0FFF4')
        state = core.load_config()
        self.assertIsNone(state['accent_color'])
        self.assertEqual(core.appearance_palette(state)['surface'], '#e6f5ea')

    def test_settings_survive_concurrent_app_updates(self):
        processes = [multiprocessing.Process(target=set_preference, args=(str(self.root), f'app-{index}')) for index in range(6)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(5)
            self.assertEqual(process.exitcode, 0)
        value = core.load_config()
        self.assertTrue(all(value[f'app-{index}'] for index in range(6)))

    def test_failed_atomic_save_preserves_original(self):
        target = self.root/'note.txt'
        target.write_text('original')
        with patch.object(core.os, 'replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                core.atomic_write(target, 'new')
        self.assertEqual(target.read_text(), 'original')
        self.assertEqual(list(self.root.iterdir()), [target])

    def test_atomic_save_keeps_permissions(self):
        target = self.root/'note.txt'
        target.write_text('original')
        target.chmod(0o640)
        core.atomic_write(target, 'new')
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_copy_collision_preserves_both_files(self):
        source = self.root/'note.txt'
        source.write_text('original')
        self.assertTrue(core.paste_items([source], 'copy', self.root)[0][0])
        self.assertEqual(source.read_text(), 'original')
        self.assertEqual((self.root/'note (副本 1).txt').read_text(), 'original')

    def test_folder_cannot_be_pasted_into_itself(self):
        source = self.root/'folder'
        source.mkdir()
        child = source/'child'
        child.mkdir()
        self.assertFalse(core.paste_items([source], 'copy', child)[0][0])
        self.assertFalse((child/'folder').exists())

    def test_cut_in_same_folder_does_not_rename(self):
        source = self.root/'note.txt'
        source.write_text('hello')
        self.assertEqual(core.paste_items([source], 'cut', self.root), [(True, str(source))])
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_paste_reports_partial_failures(self):
        source = self.root/'note.txt'
        source.write_text('hello')
        result = core.paste_items([source, self.root/'missing'], 'copy', self.root)
        self.assertEqual([row[0] for row in result], [True, False])

    def test_symlink_copy_preserves_link(self):
        source = self.root/'link'
        source.symlink_to('/nonexistent')
        self.assertTrue(core.paste_items([source], 'copy', self.root)[0][0])
        self.assertTrue((self.root/'link (副本 1)').is_symlink())

    def test_invalid_names_cannot_escape_directory(self):
        for name in ['', '.', '..', '../file', 'a\0b']:
            with self.assertRaises(ValueError):
                core.valid_name(name)

    def test_scientific_calculation(self):
        self.assertEqual(core.evaluate('(12+8)/5'), 4)
        self.assertAlmostEqual(core.evaluate('sin(90)', degrees=True), 1)
        self.assertEqual(core.evaluate('sqrt(81)+2^3'), 17)

    def test_calculator_rejects_code_and_unbounded_power(self):
        for expression in ['__import__("os")', '(1).__class__', '[1,2]', '9**9999999', 'sqrt(-1)', '1/0']:
            with self.assertRaises((ValueError, ZeroDivisionError)):
                core.evaluate(expression)

    def test_minimized_windows_stay_in_taskbar(self):
        tree = {'nodes': [{'type': 'workspace', 'name': '__i3_scratch', 'floating_nodes': [{'id': 42, 'pid': 11, 'app_id': 'com.b5software.cibyp.editor', 'name': 'notes', 'visible': False}]}]}
        rows = core.collect_windows(tree)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['minimized'])
        self.assertEqual(rows[0]['id'], 42)

    def test_restore_from_trash_avoids_overwriting(self):
        files, info = self.root/'Trash/files', self.root/'Trash/info'
        files.mkdir(parents=True)
        info.mkdir()
        original = self.root/'课堂笔记.txt'
        original.write_text('new note')
        trashed = files/'note.txt'
        trashed.write_text('old note')
        metadata = info/'note.txt.trashinfo'
        metadata.write_text('[Trash Info]\nPath='+quote(str(original))+'\nDeletionDate=2026-09-30T10:00:00\n')
        self.assertTrue(trash.restore([trashed])[0][0])
        self.assertEqual(original.read_text(), 'new note')
        self.assertEqual((self.root/'课堂笔记 (副本 1).txt').read_text(), 'old note')
        self.assertFalse(metadata.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
