"""Filesystem regression tests for the trust boundary of executable undo history."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import file_manager
import storage_backend


class TransferHistorySecurityTests(unittest.TestCase):
    def test_legacy_records_cannot_delete_or_export_private_files(self) -> None:
        for already_imported in (False, True):
            for is_copy in (True, False):
                for bulk in (False, True):
                    with self.subTest(imported=already_imported, copy=is_copy, bulk=bulk):
                        self._check_legacy_record(already_imported, is_copy, bulk)

    def _check_legacy_record(self, already_imported: bool, is_copy: bool, bulk: bool) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private = root / "private"
            shared = root / "shared"
            private.mkdir()
            shared.mkdir()
            secret = private / "secret.txt"
            secret.write_bytes(b"private contents")
            exported = shared / "exported.txt"
            payload = json.dumps([{
                "id": 123,
                "source": str(exported),
                "destination": str(secret),
                "is_copy": is_copy,
                "is_saf_dest": False,
            }])
            shared_log = shared / "transfer_history.json"
            shared_log.write_text(payload, encoding="utf-8")
            if already_imported:
                (private / "transfer_history.json").write_text(payload, encoding="utf-8")

            with (
                patch.object(file_manager, "get_app_private_storage_dir", return_value=private),
                patch.object(file_manager, "get_internal_media_sorter_base_path", return_value=shared),
            ):
                if bulk:
                    result = file_manager.undo_all_transfers()
                else:
                    result = file_manager.undo_transfer(123)
                self.assertTrue(secret.exists(), "Forged history deleted or moved a private file")
                self.assertEqual(secret.read_bytes(), b"private contents")
                self.assertFalse(exported.exists(), "Forged history exported private contents")
                self.assertEqual(result, 0 if bulk else False)
                self.assertEqual(file_manager.get_transfer_history(), [])
                self.assertEqual(shared_log.read_text(encoding="utf-8"), payload)
                if already_imported:
                    self.assertEqual(
                        (private / "transfer_history.json").read_text(encoding="utf-8"), payload
                    )

    def test_new_private_transfers_remain_undoable(self) -> None:
        for is_copy in (True, False):
            for bulk in (False, True):
                with self.subTest(copy=is_copy, bulk=bulk), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    private = root / "private"
                    shared = root / "shared"
                    private.mkdir()
                    shared.mkdir()
                    # Neither shared history nor a previously imported private log may be reused.
                    for directory in (private, shared):
                        (directory / "transfer_history.json").write_text('[{"id": 123}]', encoding="utf-8")
                    source = root / "source.jpg"
                    source.write_bytes(b"media contents")
                    target = storage_backend.TargetLocation(
                        storage_type="custom", is_saf=False, path=shared, is_valid=True
                    )
                    with (
                        patch.object(file_manager, "get_app_private_storage_dir", return_value=private),
                        patch.object(file_manager, "get_internal_media_sorter_base_path", return_value=shared),
                    ):
                        dest = Path(file_manager.move_to_category(
                            source, "صوري", target_location=target, copy_only=is_copy
                        ))
                        self.assertEqual(dest.read_bytes(), b"media contents")
                        self.assertEqual(source.exists(), is_copy)
                        history = file_manager.get_transfer_history()
                        self.assertEqual(len(history), 1)
                        self.assertEqual(history[0]["source"], str(source))
                        self.assertEqual(history[0]["destination"], str(dest))
                        self.assertEqual(history[0]["is_copy"], is_copy)
                        self.assertEqual(file_manager.get_transfer_log_path().parent, private)
                        if bulk:
                            self.assertEqual(file_manager.undo_all_transfers(), 1)
                        else:
                            self.assertTrue(file_manager.undo_transfer(history[0]["id"]))
                        self.assertEqual(source.read_bytes(), b"media contents")
                        self.assertFalse(dest.exists())
                        self.assertEqual(file_manager.get_transfer_history(), [])


if __name__ == "__main__":
    unittest.main()
