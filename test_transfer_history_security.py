"""Regression checks for shared history crossing the destructive undo boundary."""

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

import file_manager
import storage_backend


class TransferHistorySecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / 'private'
        self.shared = self.root / 'shared'
        self.archive = self.root / 'archive'
        for directory in (self.private, self.shared, self.archive):
            directory.mkdir()
        self.enterContext(patch.object(file_manager, 'get_app_private_storage_dir', return_value=self.private))
        self.enterContext(patch.object(file_manager, 'get_internal_media_sorter_base_path', return_value=self.shared))
        self.source = self.root / 'source.jpg'
        self.source.write_bytes(b'original photo')
        self.victim = self.private / 'settings.json'
        self.victim.write_bytes(b'private settings')

    def forged_record(self, is_copy=True):
        return {'id': -1, 'source': str(self.source), 'destination': str(self.victim),
                'is_copy': is_copy, 'undo_allowed': True, 'archive_root': str(self.private),
                'undo_signature': 'forged signature'}

    def read_log(self):
        return json.loads(file_manager.get_transfer_log_path().read_text())

    def write_log(self, records):
        file_manager.get_transfer_log_path().write_text(json.dumps(records))

    def assert_rejected(self, record):
        with patch.object(storage_backend, 'delete_media_item') as delete, patch.object(file_manager.shutil, 'move') as move:
            self.assertFalse(file_manager.undo_transfer(record['id']))
            self.assertEqual(file_manager.undo_all_transfers(), 0)
            delete.assert_not_called()
            move.assert_not_called()
        self.assertEqual(self.victim.read_bytes(), b'private settings')
        self.assertEqual(self.source.read_bytes(), b'original photo')
        self.assertEqual(len(self.read_log()), 1)

    def test_imported_records_cannot_authorize_copy_or_move_undo(self):
        for is_copy in (True, False):
            with self.subTest(is_copy=is_copy):
                private_log = self.private / 'transfer_history_v2.json'
                private_log.unlink(missing_ok=True)
                record = self.forged_record(is_copy)
                (self.shared / 'transfer_history.json').write_text(json.dumps([record]))
                history = file_manager.get_transfer_history()
                self.assertEqual(history[0]['destination'], str(self.victim))
                self.assertIs(history[0]['undo_allowed'], False)
                self.assert_rejected(record)
                # Reloading the private copy must not promote imported history.
                self.assertFalse(file_manager.can_undo_transfer(self.read_log()[0]))

    def test_previously_migrated_private_history_cannot_forge_authorization(self):
        # Generate a real private key first, then simulate an old unvalidated import.
        file_manager.copy_to_category(self.source, 'photos', target_location=self.location())
        record = self.forged_record()
        self.write_log([record])
        self.assert_rejected(record)
        record.pop('undo_signature')
        record.pop('undo_allowed')
        self.write_log([record])
        self.assert_rejected(record)
        record['undo_allowed'] = True
        record['undo_signature'] = 'توقيع مزور'
        self.write_log([record])
        self.assert_rejected(record)

    def location(self):
        return storage_backend.TargetLocation(storage_type='custom', path=self.archive)

    def test_interrupted_key_creation_can_retry_without_publishing_partial_key(self):
        record = self.forged_record()
        key_file = self.private / 'transfer_undo.key'
        with patch.object(file_manager.os, 'fsync', side_effect=OSError('disk error')):
            self.assertEqual(file_manager._transfer_undo_signature(record, create_key=True), '')
        self.assertFalse(key_file.exists())
        self.assertEqual(sorted(p.name for p in self.private.iterdir()), ['.transfer_undo.lock', 'settings.json'])
        signature = file_manager._transfer_undo_signature(record, create_key=True)
        self.assertEqual(len(signature), 64)
        self.assertEqual(key_file.stat().st_mode & 0o777, 0o600)

    def test_competing_key_creators_use_same_fully_written_key(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event

        record = self.forged_record()
        real_replace = os.replace
        real_connect = file_manager.sqlite3.connect
        ready_to_publish, competitor_started = Event(), Event()

        def connect(*args, **kwargs):
            competitor_started.set()
            return real_connect(*args, **kwargs)

        def publish(candidate, key_file):
            self.assertFalse(key_file.exists())
            self.assertEqual(len(Path(candidate).read_bytes()), 32)
            self.assertEqual(Path(candidate).stat().st_mode & 0o777, 0o600)
            ready_to_publish.set()
            self.assertTrue(competitor_started.wait(5))
            return real_replace(candidate, key_file)

        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(file_manager.os, 'replace', side_effect=publish) as rename:
            first = pool.submit(file_manager._transfer_undo_signature, record, create_key=True)
            self.assertTrue(ready_to_publish.wait(5))
            with patch.object(file_manager.sqlite3, 'connect', side_effect=connect):
                second = pool.submit(file_manager._transfer_undo_signature, record, create_key=True)
                signature = first.result(timeout=5)
                self.assertEqual(second.result(timeout=5), signature)
            rename.assert_called_once()
        self.assertEqual(len(signature), 64)
        self.assertEqual(sorted(p.name for p in self.private.iterdir()),
                         ['.transfer_undo.lock', 'settings.json', 'transfer_undo.key'])

    def test_key_creation_and_undo_work_when_hard_links_are_denied(self):
        with patch.object(file_manager.os, 'link', side_effect=PermissionError('Android policy')) as hard_link:
            destination = file_manager.copy_to_category(self.source, 'photos', target_location=self.location())
            record = self.read_log()[0]
            self.assertTrue(file_manager.can_undo_transfer(record))
            self.assertTrue(file_manager.undo_transfer(record['id']))
            self.assertFalse(Path(destination).exists())
            hard_link.assert_not_called()

    def test_new_copy_and_move_remain_undoable_after_reload(self):
        for is_copy in (True, False):
            with self.subTest(is_copy=is_copy):
                destination = file_manager.move_to_category(
                    self.source, 'photos', target_location=self.location(), copy_only=is_copy)
                record = self.read_log()[0]
                self.assertTrue(file_manager.can_undo_transfer(record))
                self.assertTrue(file_manager.undo_transfer(record['id']))
                self.assertFalse(Path(destination).exists())
                self.assertEqual(self.source.read_bytes(), b'original photo')
                self.assertEqual(self.read_log(), [])

    def test_bulk_undo_preserves_untrusted_and_failed_records(self):
        imported = self.forged_record()
        (self.shared / 'transfer_history.json').write_text(json.dumps([imported]))
        destination = file_manager.copy_to_category(self.source, 'photos', target_location=self.location())
        with patch.object(storage_backend, 'delete_media_item', return_value=False):
            self.assertEqual(file_manager.undo_all_transfers(), 0)
        self.assertEqual(len(self.read_log()), 2)
        self.assertEqual(file_manager.undo_all_transfers(), 1)
        self.assertFalse(Path(destination).exists())
        self.assertEqual(self.read_log()[0]['id'], -1)
        self.assertEqual(self.victim.read_bytes(), b'private settings')

    def test_signed_record_cannot_be_redirected(self):
        file_manager.copy_to_category(self.source, 'photos', target_location=self.location())
        record = self.read_log()[0]
        record['destination'] = str(self.victim)
        record['archive_root'] = str(self.private)
        self.write_log([record])
        self.assert_rejected(record)

    def test_symlink_escape_is_rejected_even_with_valid_signature(self):
        destination = file_manager.copy_to_category(self.source, 'photos', target_location=self.location())
        record = self.read_log()[0]
        folder = Path(destination).parent
        Path(destination).unlink()
        folder.rmdir()
        outside = self.root / 'outside'
        outside.mkdir()
        outside.joinpath(self.source.name).write_bytes(b'outside file')
        folder.symlink_to(outside, target_is_directory=True)
        self.assert_rejected(record)
        self.assertEqual(outside.joinpath(self.source.name).read_bytes(), b'outside file')

    def test_local_containment_rejects_traversal_root_and_uri_confusion(self):
        for destination in (self.archive, self.archive / '..' / 'private' / 'settings.json',
                            self.root / 'archive-sibling' / 'photo.jpg', 'content://provider/document/id'):
            with self.subTest(destination=destination):
                self.assertFalse(storage_backend.is_within_archive_root(str(destination), str(self.archive)))
        self.assertTrue(storage_backend.is_within_archive_root(str(self.archive / 'photos' / 'missing.jpg'), str(self.archive)))

    def test_archive_root_replacement_is_rejected_with_valid_signature(self):
        destination = Path(file_manager.copy_to_category(self.source, 'photos', target_location=self.location()))
        record = self.read_log()[0]
        replacement = self.private / destination.relative_to(self.archive)
        replacement.parent.mkdir(parents=True, exist_ok=True)
        replacement.write_bytes(b'private replacement')
        self.archive.rename(self.root / 'original_archive')
        self.archive.symlink_to(self.private, target_is_directory=True)
        self.assertEqual(record['undo_signature'], file_manager._transfer_undo_signature(record))
        self.assert_rejected(record)
        self.assertEqual(replacement.read_bytes(), b'private replacement')

    def test_mock_saf_undo_rejects_destination_replaced_by_directory(self):
        target = storage_backend.TargetLocation(storage_type='custom', is_saf=True,
                                               tree_uri=f'mock_saf://{self.archive}')
        destination = file_manager.copy_to_category(self.source, 'photos', target_location=target)
        record = self.read_log()[0]
        path = Path(destination.removeprefix('mock_doc://'))
        path.unlink()
        path.mkdir()
        child = path / 'keep.txt'
        child.write_bytes(b'keep directory contents')
        self.assertEqual(record['undo_signature'], file_manager._transfer_undo_signature(record))
        self.assert_rejected(record)
        self.assertEqual(child.read_bytes(), b'keep directory contents')

    def test_mock_saf_copy_undo_uses_recorded_tree(self):
        target = storage_backend.TargetLocation(storage_type='custom', is_saf=True,
                                               tree_uri=f'mock_saf://{self.archive}')
        destination = file_manager.copy_to_category(self.source, 'photos', target_location=target)
        record = self.read_log()[0]
        self.assertTrue(file_manager.undo_transfer(record['id']))
        self.assertFalse(Path(destination.removeprefix('mock_doc://')).exists())
        self.assertTrue(self.source.exists())
        self.assertFalse(storage_backend.is_within_archive_root(f'mock_doc://{self.victim}', target.tree_uri))

    def test_saf_containment_uses_provider_descendant_check_and_fails_closed(self):
        tree = Mock()
        tree.getAuthority.return_value = 'provider'
        child = Mock()
        child.getAuthority.return_value = 'provider'
        uri = Mock()
        uri.parse.side_effect = [tree, child] * 6
        contract = Mock()
        contract.getTreeDocumentId.return_value = 'root'
        contract.getDocumentId.return_value = 'child'
        contract.isChildDocument.return_value = True
        activity = Mock()
        modules = {'android': SimpleNamespace(mActivity=activity),
                   'jnius': SimpleNamespace(autoclass=lambda name: uri if name == 'android.net.Uri' else contract)}
        with patch.dict(sys.modules, modules), patch.object(storage_backend, '_get_platform', return_value='android'), \
                patch.object(storage_backend, 'is_saf_uri_valid', return_value=True) as valid:
            def check():
                return storage_backend.is_within_archive_root('content://provider/document/child', 'content://provider/tree/root')
            self.assertTrue(check())
            contract.isChildDocument.assert_called_once_with(activity.getContentResolver(), contract.buildDocumentUriUsingTree(), child)
            contract.isChildDocument.return_value = False
            self.assertFalse(check())
            contract.isChildDocument.side_effect = PermissionError('revoked')
            self.assertFalse(check())
            contract.isChildDocument.reset_mock()
            valid.return_value = False
            self.assertFalse(check())
            valid.return_value = True
            child.getAuthority.return_value = 'other-provider'
            self.assertFalse(check())
            child.getAuthority.return_value = 'provider'
            contract.getDocumentId.return_value = 'root'
            self.assertFalse(check())
            contract.isChildDocument.assert_not_called()


if __name__ == '__main__':
    unittest.main()
