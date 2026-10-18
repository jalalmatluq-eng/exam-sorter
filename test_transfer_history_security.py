"""Regression tests for the trust boundary between shared history and Undo."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import file_manager
import storage_backend


class TransferHistorySecurityTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory()
        self.addCleanup(self.sandbox.cleanup)
        self.root = Path(self.sandbox.name)
        self.private = self.root / "private"
        self.shared = self.root / "shared"
        self.private.mkdir()
        self.shared.mkdir()
        for name, value in (
            ("get_app_private_storage_dir", self.private),
            ("get_internal_media_sorter_base_path", self.shared),
        ):
            patcher = patch.object(file_manager, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_records(self, records, directory=None):
        log = (directory or self.private) / "transfer_history.json"
        log.write_text(json.dumps(records), encoding="utf-8")

    def test_unauthenticated_history_cannot_write_or_delete(self):
        for already_imported in (False, True):
            for bulk in (False, True):
                for is_copy in (False, True):
                    with self.subTest(already_imported=already_imported, bulk=bulk, is_copy=is_copy):
                        victim = self.private / "sorter_prefs.json"
                        victim.write_bytes(b"private data")
                        payload = self.shared / "payload.jpg"
                        payload.write_bytes(b"attacker bytes")
                        record = {
                            "id": 1,
                            "source": str(victim),
                            "destination": str(victim) if is_copy else "content://provider/document/payload",
                            "is_copy": is_copy,
                            "undo_allowed": True,
                            "can_undo": True,
                            "undo_signature": "forged",
                        }
                        (self.private / "transfer_history.json").unlink(missing_ok=True)
                        self.write_records([record], self.private if already_imported else self.shared)
                        with patch.object(storage_backend, "copy_uri_to_path") as copy_uri, \
                                patch.object(storage_backend, "delete_media_item") as delete, \
                                patch.object(storage_backend, "is_saf_uri_valid", return_value=True):
                            result = file_manager.undo_all_transfers() if bulk else file_manager.undo_transfer(1)
                            self.assertEqual(result, 0)
                            copy_uri.assert_not_called()
                            delete.assert_not_called()
                        self.assertEqual(victim.read_bytes(), b"private data")
                        history = file_manager.get_transfer_history()
                        self.assertEqual(len(history), 1)
                        self.assertIs(history[0].get("can_undo"), False)

    def test_unsigned_local_move_cannot_create_directories(self):
        target = self.root / "outside_media" / "new" / "file"
        payload = self.shared / "payload.jpg"
        payload.write_bytes(b"attacker bytes")
        self.write_records([{"id": 1, "source": str(target), "destination": str(payload), "is_copy": False}])
        self.assertFalse(file_manager.undo_transfer(1))
        self.assertEqual(file_manager.undo_all_transfers(), 0)
        self.assertFalse(target.parent.exists())
        self.assertTrue(payload.exists())

    def test_new_transfers_support_single_and_bulk_undo(self):
        for bulk in (False, True):
            for is_copy in (False, True):
                with self.subTest(bulk=bulk, is_copy=is_copy):
                    source = self.shared / "source.jpg"
                    source.write_bytes(b"original media")
                    destination = self.shared / "sorted.jpg"
                    destination.write_bytes(source.read_bytes())
                    record_id = file_manager._log_transfer_record(
                        str(source), str(destination), "media", source.stat().st_size, is_copy=is_copy,
                    )
                    if not is_copy:
                        source.unlink()
                    self.assertIs(file_manager.get_transfer_history()[0].get("can_undo"), True)
                    result = file_manager.undo_all_transfers() if bulk else file_manager.undo_transfer(record_id)
                    self.assertEqual(result, 1)
                    self.assertEqual(source.read_bytes(), b"original media")
                    self.assertFalse(destination.exists())
                    self.assertEqual(file_manager.get_transfer_history(), [])

    def test_new_uri_move_can_restore_after_reload(self):
        source = self.shared / "source.jpg"
        payload = self.shared / "provider.jpg"
        payload.write_bytes(b"original media")
        record_id = file_manager._log_transfer_record(
            str(source), "content://provider/document/media", "media", 14, is_copy=False,
        )
        real_copy = storage_backend.copy_uri_to_path
        with patch.object(storage_backend, "is_saf_uri_valid", return_value=True), \
                patch.object(storage_backend, "get_saf_persisted_uri", return_value="content://provider/tree"), \
                patch.object(storage_backend, "copy_uri_to_path", side_effect=lambda uri, dest: real_copy(str(payload), dest)), \
                patch.object(storage_backend, "delete_media_item", return_value=True):
            self.assertTrue(file_manager.undo_transfer(record_id))
        self.assertEqual(source.read_bytes(), b"original media")

    def test_tampered_records_and_missing_key_fail_closed(self):
        source = self.shared / "source.jpg"
        destination = self.shared / "sorted.jpg"
        destination.write_bytes(b"media")
        record_id = file_manager._log_transfer_record(str(source), str(destination), "media", 5)
        original = json.loads((self.private / "transfer_history.json").read_text())[0]
        for field, value in (
            ("source", str(self.private / "sorter_prefs.json")),
            ("destination", str(self.private / "sorter_prefs.json")),
            ("is_copy", False),
            ("undo_signature", "\u00e9" * 64),
        ):
            with self.subTest(field=field):
                self.write_records([{**original, field: value}])
                self.assertFalse(file_manager.undo_transfer(record_id))
                self.assertEqual(file_manager.undo_all_transfers(), 0)
        self.write_records([original])
        (self.private / "transfer_history.key").unlink()
        self.assertFalse(file_manager.undo_transfer(record_id))
        self.assertTrue(destination.exists())

    def test_legacy_import_does_not_preserve_even_a_valid_signature(self):
        destination = self.shared / "sorted.jpg"
        destination.write_bytes(b"media")
        record_id = file_manager._log_transfer_record("original.jpg", str(destination), "media", 5)
        log = self.private / "transfer_history.json"
        (self.shared / log.name).write_bytes(log.read_bytes())
        log.unlink()
        self.assertIs(file_manager.get_transfer_history()[0].get("can_undo"), False)
        self.assertFalse(file_manager.undo_transfer(record_id))
        self.assertTrue(destination.exists())

    def test_record_updates_preserve_authentication_without_trusting_legacy(self):
        for updater in ("update_transfer_record_to_move", "update_transfer_record_by_src_to_move"):
            with self.subTest(updater=updater):
                source = str(self.shared / "source.jpg")
                record_id = file_manager._log_transfer_record(source, "sorted.jpg", "media", 5)
                argument = record_id if updater.endswith("record_to_move") else source
                self.assertTrue(getattr(file_manager, updater)(argument))
                history = file_manager.get_transfer_history()
                self.assertIs(history[0]["is_copy"], False)
                self.assertIs(history[0].get("can_undo"), True)
                file_manager._update_last_transfer_record_to_copy()
                self.assertIs(file_manager.get_transfer_history()[0].get("can_undo"), True)
                self.assertIs(file_manager.get_transfer_history()[0]["is_copy"], True)
                self.write_records([{"id": record_id, "source": source, "destination": "forged", "is_copy": True}])
                self.assertFalse(getattr(file_manager, updater)(argument))
                self.assertIs(file_manager.get_transfer_history()[0].get("can_undo"), False)

    def test_bulk_undo_retains_legacy_records_when_new_records_succeed(self):
        victim = self.private / "preferences.json"
        victim.write_bytes(b"private data")
        self.write_records([{"id": 1, "source": "unused", "destination": str(victim), "is_copy": True}])
        destination = self.shared / "sorted.jpg"
        destination.write_bytes(b"media")
        file_manager._log_transfer_record("source.jpg", str(destination), "media", 5)
        self.assertEqual(file_manager.undo_all_transfers(), 1)
        self.assertEqual(victim.read_bytes(), b"private data")
        self.assertFalse(destination.exists())
        self.assertEqual(len(file_manager.get_transfer_history()), 1)

    def test_explicit_log_directory_never_controls_the_private_key(self):
        source = self.shared / "source.jpg"
        destination = self.shared / "sorted.jpg"
        destination.write_bytes(b"media")
        record_id = file_manager._log_transfer_record(
            str(source), str(destination), "media", 5, base_path=self.shared,
        )
        self.assertTrue((self.private / "transfer_history.key").exists())
        self.assertFalse((self.shared / "transfer_history.key").exists())
        records = json.loads((self.shared / "transfer_history.json").read_text())
        records[0]["destination"] = str(self.private / "sorter_prefs.json")
        self.write_records(records, self.shared)
        self.assertFalse(file_manager.undo_transfer(record_id, base_path=self.shared))
        self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
