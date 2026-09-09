import unittest
from unittest.mock import patch

from app import SCCMToolboxApp


def _find_button_by_text(root, text):
    for child in root.winfo_children():
        if child.winfo_class() == "Button":
            try:
                if child.cget("text") == text:
                    return child
            except Exception:
                pass
        found = _find_button_by_text(child, text)
        if found is not None:
            return found
    return None


class RunScriptButtonTests(unittest.TestCase):
    def test_run_script_button_invokes_run_selected_ps1(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ), patch.object(SCCMToolboxApp, "run_selected_ps1", autospec=True) as mocked_run:
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                run_button = _find_button_by_text(app, "Run Script")
                self.assertIsNotNone(run_button, "Le bouton 'Run Script' est introuvable.")
                run_button.invoke()
                mocked_run.assert_called_once_with(app)
            finally:
                if app is not None:
                    app.destroy()

    def test_responsive_layout_switches_between_compact_and_wide(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                app._apply_responsive_layout(width=980)
                self.assertEqual(app.tools_layout_mode, "compact")
                self.assertEqual(app.infra_layout_mode, "compact")
                self.assertEqual(app.ps1_body_pane.cget("orient"), "vertical")

                app._apply_responsive_layout(width=1280)
                self.assertEqual(app.tools_layout_mode, "wide")
                self.assertEqual(app.infra_layout_mode, "wide")
                self.assertEqual(app.ps1_body_pane.cget("orient"), "horizontal")
            finally:
                if app is not None:
                    app.destroy()

    def test_collvariable_next_name_starts_at_01(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                app.collvariable_names_values = []
                self.assertEqual(app._build_next_collvariable_name("[var]"), "[var]01")
            finally:
                if app is not None:
                    app.destroy()

    def test_collvariable_next_name_increments_existing_suffix(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                app.collvariable_names_values = [
                    ("[var]01", "one"),
                    ("[var]02", "two"),
                ]
                self.assertEqual(app._build_next_collvariable_name("[var]"), "[var]03")
            finally:
                if app is not None:
                    app.destroy()

    def test_collvariable_renumber_button_invokes_handler(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ), patch.object(SCCMToolboxApp, "renumber_collvariable_variables", autospec=True) as mocked_renumber:
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                renumber_button = _find_button_by_text(app, "RE-NUMBER")
                self.assertIsNotNone(renumber_button, "Le bouton 'RE-NUMBER' est introuvable.")
                renumber_button.invoke()
                mocked_renumber.assert_called_once_with(app)
            finally:
                if app is not None:
                    app.destroy()

    def test_collvariable_replace_button_invokes_handler(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ), patch.object(SCCMToolboxApp, "replace_collvariable_variable", autospec=True) as mocked_replace:
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                replace_button = _find_button_by_text(app, "REPLACE")
                self.assertIsNotNone(replace_button, "Le bouton 'REPLACE' est introuvable.")
                replace_button.invoke()
                mocked_replace.assert_called_once_with(app)
            finally:
                if app is not None:
                    app.destroy()

    def test_copy_deplmt_tool_is_registered_and_switches_mode(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                copy_button = _find_button_by_text(app, "Copy Deplmt")
                self.assertIsNotNone(copy_button, "Le bouton 'Copy Deplmt' est introuvable.")
                copy_button.invoke()
                app.update_idletasks()
                self.assertEqual(app.tools_mode, "CopyDeplmt")
                self.assertEqual(app.copydeplmt_panel.winfo_manager(), "pack")
            finally:
                if app is not None:
                    app.destroy()

    def test_copy_deplmt_select_column_label_is_select(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                heading = app.copydeplmt_candidates_tree.heading("checked").get("text")
                self.assertEqual(heading, "Select")
            finally:
                if app is not None:
                    app.destroy()

    def test_copy_deplmt_copies_multiple_deployment_names(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                for var in app.copydeplmt_source_type_vars.values():
                    var.set(False)
                app.copydeplmt_source_type_vars["App"].set(True)
                app.copydeplmt_source_collection_var.set("SRC-COL")
                app.copydeplmt_destination_collection_var.set("DST-COL")
                app.copydeplmt_all_candidates = [
                    {"Name": "DEP1", "Type": "Application", "Start": "-", "Collection": "SRC-COL"},
                    {"Name": "DEP2", "Type": "Application", "Start": "-", "Collection": "SRC-COL"},
                ]
                app.copydeplmt_filtered_candidates = list(app.copydeplmt_all_candidates)
                app.copydeplmt_checked_candidates = {
                    app._candidate_key(app.copydeplmt_all_candidates[0]),
                    app._candidate_key(app.copydeplmt_all_candidates[1]),
                }
                with patch.object(app, "clipboard_clear") as mocked_clear, patch.object(app, "clipboard_append") as mocked_append:
                    app.copy_deployment_value()
                mocked_clear.assert_called_once()
                mocked_append.assert_called_once_with("DEP1\nDEP2")
            finally:
                if app is not None:
                    app.destroy()

    def test_copy_deplmt_supports_multiple_checked_source_types(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                for var in app.copydeplmt_source_type_vars.values():
                    var.set(False)
                app.copydeplmt_source_type_vars["TS"].set(True)
                app.copydeplmt_source_type_vars["SUG"].set(True)
                app.copydeplmt_source_collection_var.set("SRC-COL")
                app.copydeplmt_destination_collection_var.set("DST-COL")
                app.copydeplmt_all_candidates = [
                    {"Name": "DEP-TS", "Type": "Task Sequence", "Start": "-", "Collection": "SRC-COL"},
                    {"Name": "DEP-SUG", "Type": "Software Update Group", "Start": "-", "Collection": "SRC-COL"},
                ]
                app.copydeplmt_filtered_candidates = list(app.copydeplmt_all_candidates)
                app.copydeplmt_checked_candidates = {
                    app._candidate_key(app.copydeplmt_all_candidates[0]),
                    app._candidate_key(app.copydeplmt_all_candidates[1]),
                }
                with patch.object(app, "clipboard_clear"), patch.object(app, "clipboard_append") as mocked_append:
                    app.copy_deployment_value()
                mocked_append.assert_called_once_with("DEP-TS\nDEP-SUG")
            finally:
                if app is not None:
                    app.destroy()

    def test_copy_deplmt_uses_selected_deployments_from_filtered_list(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                for var in app.copydeplmt_source_type_vars.values():
                    var.set(False)
                app.copydeplmt_source_type_vars["Program"].set(True)
                app.copydeplmt_source_collection_var.set("SRC-COL")
                app.copydeplmt_destination_collection_var.set("DST-COL")
                app.copydeplmt_all_candidates = [
                    {"Name": "DEP-A", "Type": "Program", "Start": "-", "Collection": "SRC-COL"},
                    {"Name": "DEP-B", "Type": "Program", "Start": "-", "Collection": "SRC-COL"},
                ]
                app.copydeplmt_filtered_candidates = list(app.copydeplmt_all_candidates)
                app.copydeplmt_checked_candidates = {
                    app._candidate_key(app.copydeplmt_all_candidates[0]),
                    app._candidate_key(app.copydeplmt_all_candidates[1]),
                }
                with patch.object(app, "clipboard_clear"), patch.object(app, "clipboard_append") as mocked_append:
                    app.copy_deployment_value()
                mocked_append.assert_called_once_with("DEP-A\nDEP-B")
            finally:
                if app is not None:
                    app.destroy()

    def test_copy_deplmt_collection_filter_updates_dropdown(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                app.copydeplmt_collections = ["COL-A-Servers", "COL-B-Clients", "LAB-TEST"]
                app.copydeplmt_source_collection_filter_var.set("col-")
                app._filter_copydeplmt_collections()
                values = list(app.copydeplmt_source_collection_combo.cget("values"))
                self.assertEqual(values, ["COL-A-Servers", "COL-B-Clients"])
                self.assertEqual(app.copydeplmt_source_collection_var.get(), "COL-A-Servers")
            finally:
                if app is not None:
                    app.destroy()

    def test_copy_deplmt_details_script_uses_specific_cmdlets(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                script = app._build_copy_deployment_candidates_script(
                    "SRC-COL",
                    ["Task Sequence", "Software Update Group", "Application", "Program", "Baseline"],
                )
                self.assertIn("Get-CMDeployment -CollectionName $sourceCollectionName", script)
                self.assertIn("Get-CMTaskSequenceDeployment -Name $DeploymentName -CollectionName $CollectionName", script)
                self.assertIn("Get-CMBaselineDeployment -Name $DeploymentName -CollectionName $CollectionName", script)
                self.assertIn("Get-CMSoftwareUpdateDeployment -Name $DeploymentName -CollectionName $CollectionName", script)
                self.assertIn("Get-CMApplicationDeployment -Name $DeploymentName -CollectionName $CollectionName", script)
                self.assertIn("Get-CMPackageDeployment -Name $DeploymentName -CollectionName $CollectionName", script)
                self.assertIn("Get-DeploymentConfigSource", script)
                self.assertIn("Get-CMTaskSequence -Name $DeploymentName -Fast -ErrorAction SilentlyContinue", script)
                self.assertIn("Get-CMBaseline -Name $DeploymentName -Fast -ErrorAction SilentlyContinue", script)
                self.assertIn("Get-CMApplication -Name $DeploymentName -Fast -ErrorAction SilentlyContinue", script)
                self.assertIn("Get-CMPackage -Name $DeploymentName -Fast -ErrorAction SilentlyContinue", script)
                self.assertIn("Get-CMProgram -PackageName $DeploymentName -ProgramName $ProgramName", script)
                self.assertIn("function Add-DetailProperties", script)
                self.assertIn("function Get-FirstDeploymentPropertyValue", script)
                self.assertIn("function Convert-ApplicationDeploymentAction", script)
                self.assertIn("function Convert-ApplicationDeploymentPurpose", script)
                self.assertIn("function Convert-TaskSequenceDeploymentPurpose", script)
                self.assertIn("function Convert-BaselineDeploymentPurpose", script)
                self.assertIn("function Convert-BoolToText", script)
                self.assertIn("-PropertyNames @('Action', 'DeployAction', 'OfferTypeID', 'AssignmentAction')", script)
                self.assertIn("-PropertyNames @('Purpose', 'DeployPurpose', 'DesiredConfigType')", script)
                self.assertIn("$detail['Action'] = Convert-ApplicationDeploymentAction $actionValue", script)
                self.assertIn("$detail['Purpose'] = Convert-ApplicationDeploymentPurpose $purposeValue", script)
                self.assertIn("if ($resolvedType -eq 'Task Sequence')", script)
                self.assertIn("if ($resolvedType -eq 'Baseline')", script)
            finally:
                if app is not None:
                    app.destroy()

    def test_copy_deplmt_detail_order_includes_detail_cmdlet(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                details = app._build_ordered_copydeplmt_details(
                    "Application",
                    {
                        "Type": "Application",
                        "DetailCmdlet": "Get-CMApplicationDeployment",
                        "Purpose": "Available",
                    },
                )
                self.assertEqual(list(details.keys())[:2], ["Type", "DetailCmdlet"])
                self.assertEqual(details["DetailCmdlet"], "Get-CMApplicationDeployment")
            finally:
                if app is not None:
                    app.destroy()

    def test_copy_deplmt_type_resolution_script_supports_multiple_property_names(self):
        with patch.object(SCCMToolboxApp, "refresh_ps1_list", autospec=True), patch.object(
            SCCMToolboxApp, "show_home", autospec=True
        ):
            app = None
            try:
                app = SCCMToolboxApp()
                app.withdraw()
                script = app._build_copy_deployment_candidates_script(
                    "SRC-COL",
                    ["Task Sequence", "Software Update Group", "Application", "Program", "Baseline"],
                )
                self.assertIn("function Convert-DeploymentTypeName", script)
                self.assertIn("function Resolve-DeploymentType", script)
                self.assertIn("'DeploymentObjectType'", script)
                self.assertIn("'SoftwareUpdateGroupName'", script)
                self.assertIn("'TypeName'", script)
            finally:
                if app is not None:
                    app.destroy()


if __name__ == "__main__":
    unittest.main()
