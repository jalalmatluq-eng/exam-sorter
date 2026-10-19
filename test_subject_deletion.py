"""Regression checks for subject deletion without a GUI or Android provider."""

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import file_manager
import storage_backend


def load_subject_screen():
    """Load real screen logic with only its GUI imports replaced."""
    imports = {
        "kivy.core.window": {"Window": None},
        "kivy.metrics": {"dp": lambda value: value},
        "kivy.uix.boxlayout": {"BoxLayout": object},
        "kivy.uix.button": {"Button": object},
        "kivy.uix.image": {"Image": object},
        "kivy.uix.popup": {"Popup": object},
        "kivy.uix.screenmanager": {"Screen": object},
        "kivymd.uix.card": {"MDCard": object},
        "kivymd.uix.label": {"MDIcon": object, "MDLabel": object},
        "utils.arabic_helper": {"ar": lambda text: text},
        "utils.ui_helper": {
            "get_category_ui_details": lambda name: {"stats_unit": "files"},
            "show_app_dialog": Mock(),
        },
    }
    modules = {}
    for name, attributes in imports.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        modules[name] = module
    source = Path(__file__).parent / "screens" / "subject_detail_screen.py"
    spec = importlib.util.spec_from_file_location("subject_detail_test", source)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class SubjectDeletionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.internal = self.root / "internal"
        self.sd = self.root / "sd"
        for base in (self.internal, self.sd):
            folder = base / "Math"
            folder.mkdir(parents=True)
            (folder / "exam.jpg").write_bytes(b"preserve unless confirmed")
        self.internal_target = storage_backend.TargetLocation("internal", path=self.internal)
        self.sd_target = storage_backend.TargetLocation("sdcard", path=self.sd)
        self.history = self.enterContext(patch.object(file_manager, "remove_transfer_history_records_by_dest"))
        self.enterContext(patch.object(file_manager, "get_internal_media_sorter_base_path", side_effect=AssertionError("storage fallback")))

    def test_invalid_targets_never_use_internal_or_base_path(self):
        targets = [
            storage_backend.TargetLocation("sdcard", is_valid=False),
            storage_backend.TargetLocation("sdcard", path=self.internal, is_valid=False),
            storage_backend.TargetLocation("sdcard"),
            storage_backend.TargetLocation("sdcard", is_saf=True, tree_uri=f"mock_saf://{self.sd}", is_valid=False),
        ]
        for target in targets:
            with self.subTest(target=target):
                result = file_manager.delete_subject_folder("Math", base_path=self.internal, target_location=target)
                self.assertFalse(result.files_deleted)
                self.assertFalse(result.folder_deleted)
                self.assertTrue((self.internal / "Math" / "exam.jpg").exists())
                self.assertTrue((self.sd / "Math" / "exam.jpg").exists())
        with patch.object(storage_backend, "get_active_target_location", return_value=targets[0]):
            self.assertFalse(file_manager.delete_subject_folder("Math"))
        self.history.assert_not_called()

    def test_unavailable_path_fails(self):
        self.sd.rename(self.root / "removed_sd")
        self.assertFalse(file_manager.delete_subject_folder("Math", target_location=self.sd_target))
        self.history.assert_not_called()

    def test_explicit_and_default_local_deletion(self):
        for name, kwargs in (
            ("direct", {"target_location": self.sd_target}),
            ("legacy", {"base_path": self.sd}),
            ("default", {}),
        ):
            folder = self.sd / "صور الاختبارات" / name
            folder.mkdir(parents=True)
            image = folder / "exam.jpg"
            image.write_bytes(b"confirmed")
            with patch.object(storage_backend, "get_active_target_location", return_value=self.sd_target):
                result = file_manager.delete_subject_folder(name, **kwargs)
            self.assertTrue(result)
            self.assertEqual(result.deleted_files_count, 1)
            self.assertFalse(folder.exists())
            self.history.assert_called_with([str(image)])
        self.assertTrue((self.internal / "Math" / "exam.jpg").exists())

    def test_saf_deletion(self):
        folder = self.sd / "Math"
        target = storage_backend.TargetLocation("sdcard", is_saf=True, tree_uri=f"mock_saf://{self.sd}")
        self.assertTrue(file_manager.delete_subject_folder("Math", target_location=target))
        self.assertFalse(folder.exists())
        self.assertTrue((self.internal / "Math" / "exam.jpg").exists())

    def make_screen(self):
        module = load_subject_screen()
        screen = module.SubjectDetailScreen()
        screen.ids = types.SimpleNamespace(images_grid=Mock(), info_label=Mock(), empty_box=Mock())
        screen.apply_arabic_texts = Mock()
        screen.create_image_card = Mock()
        screen.go_back = Mock()
        return module, screen

    def test_storage_changes_before_or_after_confirmation_abort(self):
        for when in ("before", "after"):
            for change in ("missing", "internal", "other_path", "saf", "replaced"):
                with self.subTest(when=when, change=change):
                    module, screen = self.make_screen()
                    current = self.sd_target
                    with (
                        patch.object(storage_backend, "get_active_target_location", side_effect=lambda: current),
                        patch.object(storage_backend, "detect_storage_locations") as detect,
                        patch.object(file_manager, "delete_subject_folder") as delete,
                    ):
                        screen.load_subject("Math")
                        self.assertEqual(screen.ids.images_grid.add_widget.call_count, 1)
                        if when == "after":
                            screen.confirm_delete_subject()
                            confirm = module.show_app_dialog.call_args.kwargs["on_confirm"]
                        if change == "missing":
                            current = storage_backend.TargetLocation("sdcard", is_valid=False)
                        elif change == "internal":
                            current = self.internal_target
                        elif change == "other_path":
                            current = storage_backend.TargetLocation("sdcard", path=self.internal)
                        elif change == "saf":
                            current = storage_backend.TargetLocation("sdcard", is_saf=True, tree_uri=f"mock_saf://{self.sd}")
                        else:
                            self.sd.rename(self.root / "old_sd")
                            self.sd.mkdir()
                        if when == "before":
                            screen.confirm_delete_subject()
                            confirm = module.show_app_dialog.call_args.kwargs["on_confirm"]
                        confirm()
                        delete.assert_not_called()
                        detect.assert_called_once_with(force_refresh=True)
                        self.history.assert_not_called()
                        self.assertTrue((self.internal / "Math" / "exam.jpg").exists())
                        if change == "replaced":
                            self.sd.rmdir()
                            (self.root / "old_sd").rename(self.sd)

    def test_confirmation_keeps_displayed_subject_and_target(self):
        module, screen = self.make_screen()
        with (
            patch.object(storage_backend, "get_active_target_location", return_value=self.sd_target),
            patch.object(storage_backend, "detect_storage_locations"),
        ):
            screen.load_subject("Math")
            screen.confirm_delete_subject()
            confirm = module.show_app_dialog.call_args.kwargs["on_confirm"]
            # Loading another subject must not retarget an already open confirmation.
            screen.load_subject("Other")
            confirm()
        self.assertFalse((self.sd / "Math").exists())
        self.assertTrue((self.internal / "Math" / "exam.jpg").exists())
        screen.go_back.assert_called_once()

    def test_invalid_display_never_reads_internal(self):
        module, screen = self.make_screen()
        with (
            patch.object(storage_backend, "get_active_target_location", return_value=storage_backend.TargetLocation("sdcard", is_valid=False)),
            patch.object(storage_backend, "detect_storage_locations"),
            patch.object(file_manager, "get_subject_images") as images,
            patch.object(file_manager, "delete_subject_folder") as delete,
        ):
            screen.load_subject("Math")
            screen.confirm_delete_subject()
            module.show_app_dialog.call_args.kwargs["on_confirm"]()
        images.assert_not_called()
        delete.assert_not_called()


def run_subject_deletion_tests():
    """Include these regressions in the repository's test_modules.py runner."""
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(SubjectDeletionTests))
    assert result.wasSuccessful(), "Subject deletion regression checks failed"


if __name__ == "__main__":
    unittest.main()
