"""Security regressions for deleting a single subject through SAF."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import file_manager
import storage_backend


class SubjectFolderDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tree_uri = f"mock_saf://{self.root}"
        self.target = storage_backend.TargetLocation(
            storage_type="sdcard", is_saf=True, tree_uri=self.tree_uri, is_valid=True,
        )
        history_patch = patch.object(file_manager, "remove_transfer_history_records_by_dest")
        self.history = history_patch.start()
        self.addCleanup(history_patch.stop)

    def media(self, relative_path):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic media")
        return path

    def test_reserved_subject_deletion_preserves_archives(self):
        for name in (storage_backend.ORGANIZED_FOLDER_NAME, "صور الاختبارات", "صور اختبارات"):
            with self.subTest(name=name):
                subject = Path(storage_backend.ORGANIZED_FOLDER_NAME) / "صور الاختبارات" / name
                payload = self.media(subject / "nested" / "payload.jpg")
                unrelated = self.media(Path(storage_backend.ORGANIZED_FOLDER_NAME) / "صوري" / "keep.jpg")
                sibling = self.media(subject.parent / "فيزياء" / "keep.jpg")
                listed = file_manager.list_subjects(target_location=self.target)
                self.assertIn(name, [s["name"] for s in listed])
                result = file_manager.delete_subject_folder(name, target_location=self.target)
                self.assertTrue(result)
                self.assertEqual(result.deleted_files_count, 1)
                self.assertFalse(payload.parent.parent.exists())
                self.assertTrue(unrelated.exists())
                self.assertTrue(sibling.exists())
                self.history.assert_called_with([f"mock_doc://{payload}"])

    def test_normal_subjects_in_supported_layouts(self):
        prefixes = (
            Path(storage_backend.ORGANIZED_FOLDER_NAME) / "صور الاختبارات",
            Path("صور الاختبارات"),
            Path(storage_backend.ORGANIZED_FOLDER_NAME) / "صور اختبارات",
            Path("صور اختبارات"),
            Path(storage_backend.ORGANIZED_FOLDER_NAME),
            Path(),
        )
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                payload = self.media(prefix / "رياضيات" / "payload.jpg")
                result = file_manager.delete_subject_folder("رياضيات", target_location=self.target)
                self.assertTrue(result)
                self.assertFalse(payload.parent.exists())

    def test_archive_ancestors_are_rejected_without_deletion(self):
        archive_file = self.media(Path(storage_backend.ORGANIZED_FOLDER_NAME) / "keep.jpg")
        exam_file = self.media(Path(storage_backend.ORGANIZED_FOLDER_NAME) / "صور الاختبارات" / "keep.jpg")
        for name in (storage_backend.ORGANIZED_FOLDER_NAME, "صور الاختبارات", "", ".", ".."):
            with self.subTest(name=name), patch.object(storage_backend, "delete_media_item") as delete:
                self.assertFalse(file_manager.delete_subject_folder(name, target_location=self.target))
                delete.assert_not_called()
                self.assertTrue(archive_file.exists())
                self.assertTrue(exam_file.exists())

    def test_ambiguous_subject_is_rejected_before_deleting_files(self):
        first = self.media(Path(storage_backend.ORGANIZED_FOLDER_NAME) / "صور الاختبارات" / "رياضيات" / "first.jpg")
        second = self.media(Path("رياضيات") / "second.jpg")
        with patch.object(storage_backend, "delete_media_item") as delete:
            self.assertFalse(file_manager.delete_subject_folder("رياضيات", target_location=self.target))
            delete.assert_not_called()
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_subject_name_is_not_sanitized_for_destructive_lookup(self):
        selected = self.media(Path("a?b") / "payload.jpg")
        other = self.media(Path("a b") / "keep.jpg")
        self.assertTrue(file_manager.delete_subject_folder("a?b", target_location=self.target))
        self.assertFalse(selected.parent.exists())
        self.assertTrue(other.exists())

    def test_failed_resolution_preserves_files(self):
        payload = self.media(Path("رياضيات") / "payload.jpg")
        with (
            patch.object(storage_backend, "saf_find_directory", return_value=""),
            patch.object(storage_backend, "delete_media_item") as delete,
        ):
            self.assertFalse(file_manager.delete_subject_folder("رياضيات", target_location=self.target))
            delete.assert_not_called()
        self.assertTrue(payload.exists())

    def test_exact_lookup_preserves_path_and_does_not_fall_back(self):
        payload = self.media(Path("الملفات المنظمة") / "صور الاختبارات" / "الملفات المنظمة" / "payload.jpg")
        spaced = self.media(Path(" spaced ") / "payload.jpg")
        for path in ("", "/", ".", "..", "../outside", "a//b", "a/../b", "a\\b"):
            with self.subTest(path=path):
                self.assertEqual(storage_backend.saf_find_directory(self.tree_uri, path, exact=True), "")
        self.assertEqual(storage_backend.saf_find_directory(self.tree_uri, "الملفات المنظمة"), "")
        self.assertEqual(storage_backend.saf_find_directory(self.tree_uri, "spaced", exact=True), "")
        self.assertEqual(
            storage_backend.saf_find_directory(self.tree_uri, " spaced ", exact=True), f"mock_doc://{spaced.parent}",
        )
        self.assertEqual(
            storage_backend.saf_find_directory(self.tree_uri, str(payload.parent.relative_to(self.root)), exact=True),
            f"mock_doc://{payload.parent}",
        )

    def test_android_subject_deletion_uses_exact_document_for_both_backends(self):
        # Document IDs are opaque, so the lookup must walk names from the granted tree.
        class Uri:
            def __init__(self, document_id):
                self.document_id = document_id

            def toString(self):
                return f"content://provider/tree/grant/document/{self.document_id}"

        class Document:
            def __init__(self, document_id, children=None):
                self.uri = Uri(document_id)
                self.children = children or {}

            def findFile(self, name):
                return self.children.get(name)

            def getUri(self):
                return self.uri

        subject = Document("opaque-subject")
        exams = Document("opaque-exams", {"الملفات المنظمة": subject})
        archive = Document("opaque-archive", {"صور الاختبارات": exams})
        root = Document("grant", {"الملفات المنظمة": archive})
        by_id = {doc.uri.document_id: doc for doc in (root, archive, exams, subject)}
        uri_class = SimpleNamespace(parse=lambda value: value)
        document_class = SimpleNamespace(fromTreeUri=lambda *_: root)
        deleted = []
        contract = SimpleNamespace(
            getTreeDocumentId=lambda _: "grant",
            buildDocumentUriUsingTree=lambda _, doc_id: by_id[doc_id].uri,
            deleteDocument=lambda _, uri: deleted.append(uri) or True,
        )
        android = SimpleNamespace(mActivity=SimpleNamespace(getContentResolver=lambda: object()))
        jnius = SimpleNamespace(autoclass=lambda name: uri_class if name == "android.net.Uri" else contract)

        def find_child(_resolver, _tree, parent, name):
            child = by_id[parent.document_id].findFile(name)
            return child.uri if child else None

        item = storage_backend.MediaItem(
            id="payload", source_type="saf_document", uri="content://provider/document/payload",
            relative_path="الملفات المنظمة/صور الاختبارات/الملفات المنظمة/payload.jpg",
        )
        target = storage_backend.TargetLocation(storage_type="sdcard", is_saf=True, tree_uri="content://provider/tree/grant")
        for backend in (document_class, None):
            deleted.clear()
            with (
                self.subTest(backend="DocumentFile" if backend else "DocumentsContract"),
                patch.dict(sys.modules, {"android": android, "jnius": jnius}),
                patch.object(storage_backend, "_get_platform", return_value="android"),
                patch.object(storage_backend, "is_saf_uri_valid", return_value=True),
                patch.object(storage_backend, "_saf_get_document_file_class", return_value=backend),
                patch.object(storage_backend, "_contract_find_child_only", side_effect=find_child),
                patch.object(storage_backend, "scan_saf_tree_recursively", return_value=[item]),
                patch.object(file_manager, "delete_image_file", return_value=True),
            ):
                self.assertTrue(file_manager.delete_subject_folder("الملفات المنظمة", target_location=target))
                self.assertEqual(deleted, [subject.uri.toString()])
                for invalid in ("", "/", "الملفات المنظمة"):
                    self.assertEqual(storage_backend.saf_find_directory(target.tree_uri, invalid), "")


if __name__ == "__main__":
    unittest.main()
