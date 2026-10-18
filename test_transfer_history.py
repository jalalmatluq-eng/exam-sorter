"""Security regressions for history imported from shared storage (no GUI required)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import file_manager
import storage_backend


class TransferHistorySecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / "private"
        self.shared = self.root / "shared"
        self.private.mkdir()
        self.shared.mkdir()
        for name, directory in (
            ("get_app_private_storage_dir", self.private),
            ("get_internal_media_sorter_base_path", self.shared),
        ):
            patcher = patch.object(file_manager, name, return_value=directory)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.log = self.private / "transfer_history.json"
        self.source = self.root / "source.jpg"
        self.source.write_bytes(b"original media")

    def write_records(self, records: list[dict], path: Path | None = None) -> None:
        (path or self.log).write_text(json.dumps(records), encoding="utf-8")

    def test_forged_imports_and_prior_migrations_are_display_only(self) -> None:
        victim = self.private / "sorter_prefs.json"
        victim.write_bytes(b"private settings")
        for already_migrated in (False, True):
            for bulk in (False, True):
                for is_copy in (False, True):
                    with self.subTest(already_migrated=already_migrated, bulk=bulk, is_copy=is_copy):
                        self.log.unlink(missing_ok=True)
                        forged = {
                            "id": 1, "source": str(self.source), "destination": str(victim),
                            "is_copy": is_copy, "undo_signature": "forged", "undo_allowed": True,
                        }
                        path = self.log if already_migrated else self.shared / self.log.name
                        self.write_records([forged], path)
                        self.assertEqual(file_manager.get_transfer_history(), [forged])
                        self.assertFalse(file_manager.can_undo_transfer(forged))
                        with patch.object(storage_backend, "delete_media_item") as delete:
                            result = file_manager.undo_all_transfers() if bulk else file_manager.undo_transfer(1)
                            self.assertFalse(result)
                            delete.assert_not_called()
                        self.assertEqual(victim.read_bytes(), b"private settings")
                        self.assertEqual(self.source.read_bytes(), b"original media")
                        self.assertEqual(file_manager.get_transfer_history(), [forged])

    def test_logging_and_move_updates_do_not_authenticate_imports(self) -> None:
        forged = {"id": 1, "source": str(self.source), "destination": "content://forged", "is_copy": True}
        self.write_records([forged], self.shared / self.log.name)
        file_manager.copy_to_category(self.source, "photos", base_path=self.root / "outputs")
        # Even with a new private key, an existing imported record has no authority.
        file_manager.get_transfer_history()
        self.assertFalse(file_manager.update_transfer_record_to_move(1))
        self.assertFalse(file_manager.update_transfer_record_by_src_to_move(str(self.source)))
        file_manager._update_last_transfer_record_to_copy()
        self.assertEqual(file_manager.get_transfer_history(), [forged])
        with patch.object(storage_backend, "delete_media_item") as delete:
            self.assertFalse(file_manager.undo_transfer(1))
            self.assertEqual(file_manager.undo_all_transfers(), 0)
            delete.assert_not_called()

    def test_authenticated_copy_and_move_undo(self) -> None:
        for bulk in (False, True):
            for is_copy in (False, True):
                with self.subTest(bulk=bulk, is_copy=is_copy):
                    dest = file_manager.move_to_category(
                        self.source, "photos", base_path=self.shared, copy_only=is_copy,
                    )
                    record = file_manager.get_transfer_history(self.shared)[0]
                    self.assertTrue(file_manager.can_undo_transfer(record))
                    self.assertEqual(self.source.exists(), is_copy)
                    result = file_manager.undo_all_transfers(self.shared) if bulk else file_manager.undo_transfer(
                        record["id"], self.shared,
                    )
                    self.assertTrue(result)
                    self.assertFalse(Path(dest).exists())
                    self.assertEqual(self.source.read_bytes(), b"original media")
                    self.assertEqual(file_manager.get_transfer_history(self.shared), [])

    def test_tampering_invalidates_the_entire_record(self) -> None:
        dest = file_manager.copy_to_category(self.source, "photos", base_path=self.shared)
        record = file_manager.get_transfer_history(self.shared)[0]
        changes = {
            "id": 42, "destination": str(self.private / "sorter_prefs.json"),
            "source": str(self.private / "sorter_prefs.json"),
            "is_copy": False, "is_saf_dest": True, "undo_signature": "غير موثوق",
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                tampered = {**record, field: value}
                self.write_records([tampered], self.shared / self.log.name)
                self.assertFalse(file_manager.can_undo_transfer(tampered))
                self.assertFalse(file_manager.undo_transfer(tampered["id"], self.shared))
                self.assertEqual(file_manager.undo_all_transfers(self.shared), 0)
                self.assertTrue(Path(dest).exists())

    def test_authenticated_saf_copy_undo(self) -> None:
        target = storage_backend.TargetLocation(
            storage_type="sdcard", is_saf=True, tree_uri=f"mock_saf://{self.shared}",
        )
        for bulk in (False, True):
            with self.subTest(bulk=bulk):
                dest = file_manager.copy_to_category(self.source, "photos", target_location=target)
                record = file_manager.get_transfer_history()[0]
                self.assertTrue(file_manager.can_undo_transfer(record))
                result = file_manager.undo_all_transfers() if bulk else file_manager.undo_transfer(record["id"])
                self.assertTrue(result)
                self.assertFalse(Path(dest.removeprefix("mock_doc://")).exists())
                self.assertTrue(self.source.exists())

    def test_private_paths_and_symlink_aliases_are_excluded(self) -> None:
        victim = self.private / "sorter_prefs.json"
        victim.write_bytes(b"private settings")
        alias = self.root / "alias"
        alias.symlink_to(self.private, target_is_directory=True)
        for path in (victim, alias / victim.name):
            for private_source in (False, True):
                with self.subTest(path=path, private_source=private_source):
                    record_id = file_manager._log_transfer_record(
                        str(path if private_source else self.source),
                        str(self.source if private_source else path), "photos", 14,
                        is_copy=not private_source,
                    )
                    self.assertFalse(file_manager.can_undo_transfer(file_manager.get_transfer_history()[0]))
                    self.assertFalse(file_manager.undo_transfer(record_id))
                    self.assertEqual(file_manager.undo_all_transfers(), 0)
                    self.assertEqual(victim.read_bytes(), b"private settings")
                    self.assertEqual(self.source.read_bytes(), b"original media")

    def test_copy_mode_updates_preserve_authentication(self) -> None:
        for update in (
            lambda record: file_manager.update_transfer_record_to_move(record["id"], self.shared),
            lambda record: file_manager.update_transfer_record_by_src_to_move(str(self.source), self.shared),
        ):
            with self.subTest(update=update):
                file_manager.copy_to_category(self.source, "photos", base_path=self.shared)
                self.assertTrue(update(file_manager.get_transfer_history(self.shared)[0]))
                record = file_manager.get_transfer_history(self.shared)[0]
                self.assertFalse(record["is_copy"])
                self.assertTrue(file_manager.can_undo_transfer(record))
                file_manager._update_last_transfer_record_to_copy(self.shared)
                record = file_manager.get_transfer_history(self.shared)[0]
                self.assertTrue(record["is_copy"])
                self.assertTrue(file_manager.can_undo_transfer(record))
                self.assertTrue(file_manager.undo_transfer(record["id"], self.shared))

    def test_missing_or_invalid_key_disables_undo(self) -> None:
        dest = file_manager.copy_to_category(self.source, "photos", base_path=self.shared)
        record = file_manager.get_transfer_history(self.shared)[0]
        key = self.private / ".transfer_history.key"
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        for data in (None, b"invalid"):
            with self.subTest(data=data):
                if data is None:
                    key.unlink()
                else:
                    key.write_bytes(data)
                self.assertFalse(file_manager.undo_transfer(record["id"], self.shared))
                self.assertEqual(file_manager.undo_all_transfers(self.shared), 0)
                self.assertTrue(Path(dest).exists())

    def test_bulk_undo_keeps_untrusted_records(self) -> None:
        forged = {"id": 1, "source": str(self.source), "destination": str(self.source), "is_copy": True}
        self.write_records([forged], self.shared / self.log.name)
        dest = file_manager.copy_to_category(self.source, "photos")
        self.assertEqual(file_manager.undo_all_transfers(), 1)
        self.assertFalse(Path(dest).exists())
        self.assertTrue(self.source.exists())
        self.assertEqual(file_manager.get_transfer_history(), [forged])


def test_transfer_history_security() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TransferHistorySecurityTests)
    result = unittest.TextTestRunner().run(suite)
    assert result.wasSuccessful(), "Transfer history security regression failed"


if __name__ == "__main__":
    unittest.main()
