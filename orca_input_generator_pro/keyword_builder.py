from PyQt6 import QtCore
from PyQt6 import QtCore
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QSpinBox, 
    QPushButton, QGroupBox, QHBoxLayout, QComboBox, QTextEdit, 
    QTabWidget, QCheckBox, QWidget, QFormLayout, QTableWidget, 
    QTableWidgetItem, QCompleter, QPlainTextEdit, QGridLayout, QSizePolicy)
from PyQt6.QtCore import Qt, QRegularExpression
from rdkit.Chem import rdMolTransforms

from .constants import ALL_ORCA_METHODS, ALL_ORCA_BASIS_SETS
from .mixins import Dialog3DPickingMixin

class OrcaKeywordBuilderDialog(Dialog3DPickingMixin, QDialog):
    """
    Dialog to construct the ORCA Job keywords line.
    """
    def __init__(self, parent=None, current_route="", mol=None, main_window=None):
        QDialog.__init__(self, parent)
        Dialog3DPickingMixin.__init__(self)
        self.setWindowTitle("ORCA Keyword Builder")
        self.resize(800, 700)
        self.setModal(False)
        self.ui_ready = False
        self.current_route = current_route
        self.mol = mol
        self.main_window = main_window
        self.selected_atoms = []
        self.constraints = [] # List of (type, indices, value, start, end, steps, is_scan)
        self.setup_ui()
        self.parse_route(current_route)
        
        # Connect tab change to picking trigger
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def setup_ui(self):
        layout = QVBoxLayout()
        
        self.tabs = QTabWidget()
        
        # --- Tab 1: Method & Basis ---
        self.tab_method = QWidget()
        self.setup_method_tab()
        self.tabs.addTab(self.tab_method, "Method/Basis")
        
        # --- Tab 2: Job Type ---
        self.tab_job = QWidget()
        self.setup_job_tab()
        self.tabs.addTab(self.tab_job, "Job Type")
        
        # --- Tab 3: Solvation & Disp ---
        self.tab_solvation = QWidget()
        self.setup_solvation_tab()
        self.tabs.addTab(self.tab_solvation, "Solvation/Dispersion")
        
        # --- Tab 4: TD-DFT ---
        self.tab_tddft = QWidget()
        self.setup_tddft_tab()
        self.tabs.addTab(self.tab_tddft, "TD-DFT")
        
        # --- Tab 5: Constraints/Scan ---
        self.tab_constraints = QWidget()
        self.setup_constraints_tab()
        self.tabs.addTab(self.tab_constraints, "Constraints/Scan")

        # --- Tab 6: Advanced (formerly Properties) ---
        self.tab_props = QWidget()
        self.setup_props_tab()
        self.tabs.addTab(self.tab_props, "Advanced")

        layout.addWidget(self.tabs)

        # --- Preview ---
        preview_group = QGroupBox("Keyword Preview")
        preview_layout = QVBoxLayout()
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("font-weight: bold; color: blue; font-size: 14px;")
        preview_layout.addWidget(self.preview_label)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Close")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.btn_ok = QPushButton("Apply")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_ok.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)

        self.setLayout(layout)
        
        self.connect_signals()
        self.ui_ready = True
        self.update_ui_state() # Initial UI state update
        self.update_preview()

    def reject(self):
        self.restore_state()
        super().reject()

    def _capture_constraints(self):
        data = []
        for r in range(self.constraint_table.rowCount()):
            c_type = self.constraint_table.item(r, 0).text()
            idx_str = self.constraint_table.item(r, 1).text()
            val = self.constraint_table.item(r, 2).text()
            chk_widget = self.constraint_table.cellWidget(r, 3)
            is_scan = chk_widget.findChild(QCheckBox).isChecked() if chk_widget else False
            start = self.constraint_table.item(r, 4).text()
            end = self.constraint_table.item(r, 5).text()
            steps = self.constraint_table.item(r, 6).text()
            data.append((c_type, idx_str, val, is_scan, start, end, steps))
        return data

    def _restore_constraints(self, data):
        self.constraint_table.setRowCount(0)
        for row_data in data:
            c_type, idx_str, val, is_scan, start, end, steps = row_data
            row = self.constraint_table.rowCount()
            self.constraint_table.insertRow(row)
            
            def create_centered_item(text):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                return item
                
            self.constraint_table.setItem(row, 0, create_centered_item(c_type))
            self.constraint_table.setItem(row, 1, create_centered_item(idx_str))
            self.constraint_table.setItem(row, 2, create_centered_item(val))
            
            chk_scan = QCheckBox()
            chk_scan.setChecked(is_scan)
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.addWidget(chk_scan)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0,0,0,0)
            self.constraint_table.setCellWidget(row, 3, chk_widget)
            
            self.constraint_table.setItem(row, 4, create_centered_item(start))
            self.constraint_table.setItem(row, 5, create_centered_item(end))
            self.constraint_table.setItem(row, 6, create_centered_item(steps))

            def sync_scan_state(r=row, chk=chk_scan):
                is_on = chk.isChecked()
                for col in [4, 5, 6]:
                    it = self.constraint_table.item(r, col)
                    if it:
                        if is_on:
                            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEnabled)
                            it.setForeground(Qt.GlobalColor.black)
                        else:
                            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                            it.setForeground(Qt.GlobalColor.gray)
                self.update_preview()

            chk_scan.stateChanged.connect(sync_scan_state)
            sync_scan_state()

    def store_state(self):
        self._saved_state = {}
        for name, widget in self.__dict__.items():
            if isinstance(widget, QComboBox):
                self._saved_state[name] = widget.currentText()
            elif isinstance(widget, QCheckBox):
                self._saved_state[name] = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                self._saved_state[name] = widget.value()
        self._saved_constraints = self._capture_constraints()

    def restore_state(self):
        if not hasattr(self, "_saved_state"): return
        self.ui_ready = False
        for name, val in self._saved_state.items():
            widget = getattr(self, name, None)
            if not widget: continue
            if isinstance(widget, QComboBox):
                widget.setCurrentText(val)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(val)
            elif isinstance(widget, QSpinBox):
                widget.setValue(val)
        if hasattr(self, "_saved_constraints"):
            self._restore_constraints(self._saved_constraints)
        self.ui_ready = True
        self.update_preview()

    def get_inferred_category(self, text):
        if not text: return "All Methods"
        text_upper = text.upper()
        
        if text_upper in [m.upper() for m in ['CAM-B3LYP', 'LC-wPBE', 'wB97', 'wB97M-V', 'wB97X', 'wB97X-D3', 'wB97X-V', 'wPBE', 'wPBEh']]:
            return "DFT (Range-Separated)"
        elif text_upper in [m.upper() for m in ['B2GP-PLYP', 'B2PLYP', 'DSD-BLYP', 'DSD-PBEP86', 'mPW2PLYP', 'PTPSS-D3', 'PWPB95']]:
            return "DFT (Double Hybrid)"
        elif text_upper in [m.upper() for m in ['B3LYP', 'B3PW91', 'B97-3c', 'B97M-rV', 'B97M-V', 'BHandHLYP', 'BLYP', 'BP', 'BP86', 'M06', 'M06-2X', 'M06-HF', 'M06-L', 'O3LYP', 'PBE', 'PBE0', 'PBEh-3c', 'PW91', 'r2SCAN-3c', 'SCAN', 'TPSS', 'TPSSh', 'X3LYP']]:
            return "DFT (GGA/Hybrid/Meta)"
        elif text_upper in [m.upper() for m in ['HF', 'MP2', 'MP3', 'DLPNO-MP2', 'DLPNO-SCS-MP2', 'DLPNO-SOS-MP2', 'F12-DLPNO-MP2', 'F12-MP2', 'F12-RI-MP2', 'F12/D-DLPNO-MP2', 'F12/D-RI-MP2', 'OO-RI-MP2', 'OO-RI-SCS-MP2', 'OO-RI-SOS-MP2', 'RI-MP2', 'RI-SCS-MP2', 'RI-SOS-MP2', 'ROHF', 'SCS-MP2', 'SCS-MP3', 'UHF']]:
            return "Wavefunction (HF/MP2)"
        elif text_upper in [m.upper() for m in ['ACPF', 'AQCC', 'BD', 'CCSD', 'CCSD(T)', 'CCSD(T)-F12', 'CCSD(T)-F12/RI', 'CCSD(T)-F12D/RI', 'CCSD-F12', 'CCSD-F12/RI', 'CCSD-F12D/RI', 'CEPA/1', 'CEPA/2', 'CEPA/3', 'DLPNO-CCSD', 'DLPNO-CCSD(T)', 'DLPNO-CCSD(T)-F12', 'DLPNO-CCSD(T)-F12/D', 'DLPNO-CCSD(T1)', 'DLPNO-CCSD(T1)-F12', 'DLPNO-CCSD(T1)-F12/D', 'DLPNO-CCSD-F12', 'DLPNO-CCSD-F12/D', 'NCEPA/1', 'NCPF/1', 'QCISD', 'QCISD(T)', 'QCISD(T)-F12', 'QCISD(T)-F12/RI', 'QCISD-F12', 'QCISD-F12/RI', 'RI-CEPA/1-F12']]:
            return "Wavefunction (Coupled Cluster)"
        elif text_upper in [m.upper() for m in ['CASSCF', 'NEVPT2', 'DLPNO-NEVPT2', 'MRCI']]:
            return "Wavefunction (Multireference)"
        elif text_upper in [m.upper() for m in ['AM1', 'GFN-FF', 'GFN0-XTB', 'GFN1-XTB', 'GFN1-xTB', 'GFN2-XTB', 'GFN2-xTB', 'MNDO', 'NATIVE-GFN-XTB', 'NATIVE-GFN1-XTB', 'NATIVE-GFN2-XTB', 'NATIVE-spGFN-XTB', 'NATIVE-spGFN1-XTB', 'NATIVE-spGFN2-XTB', 'NATIVE-spXTB', 'NATIVE-spXTB1', 'NATIVE-spXTB2', 'NATIVE-XTB', 'NATIVE-XTB1', 'NATIVE-XTB2', 'PM3', 'PM6', 'XTB', 'XTB0', 'XTB1', 'XTB2', 'XTBFF', 'ZINDO/1', 'ZINDO/2', 'ZINDO/S', 'ZNDDO/1', 'ZNDDO/2']]:
            return "Semi-Empirical"
            
        return "All Methods"

    def setup_method_tab(self):
        layout = QFormLayout()

        self.method_type = QComboBox()
        self.method_type.addItems([
            "DFT (GGA/Hybrid/Meta)", 
            "DFT (Range-Separated)", 
            "DFT (Double Hybrid)",
            "Wavefunction (HF/MP2)",
            "Wavefunction (Coupled Cluster)",
            "Wavefunction (Multireference)",
            "Semi-Empirical",
            "All Methods"
        ])
        self.method_type.currentIndexChanged.connect(self.update_method_list)
        layout.addRow("Method Type:", self.method_type)
        
        self.method_name = QComboBox()
        self.method_name.setEditable(True)
        m_completer = QCompleter(ALL_ORCA_METHODS, self)
        m_completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        m_completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        self.method_name.setCompleter(m_completer)
        self.update_method_list()
        layout.addRow("Method:", self.method_name)
        
        self.basis_set = QComboBox()
        self.basis_set.setEditable(True)
        self.basis_set.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        basis_groups = [
            "--- Karlsruhe (Def2) ---",
            "def2-SV(P)", "def2-SVP", "def2-TZVP", "def2-QZVP",
            "def2-SVPD", "def2-TZVPD", "def2-QZVPD",
            "ma-def2-SVP", "ma-def2-TZVP", "ma-def2-QZVP",
            "def2-TZVPP", "def2-QZVPP", "def2-TZVPPD", "def2-QVPPD",
            "--- Dunning (cc-pV) ---",
            "cc-pVDZ", "cc-pVTZ", "cc-pVQZ", "cc-pV5Z",
            "aug-cc-pVDZ", "aug-cc-pVTZ", "aug-cc-pVQZ", "aug-cc-pV5Z",
            "--- Pople ---",
            "6-31G", "6-31G*", "6-311G", "6-311G*", "6-311G**", 
            "6-31+G*", "6-311+G**", "6-31++G**",
            "--- Jensen (pc) ---",
            "pc-0", "pc-1", "pc-2", "pc-3", "aug-pc-1", "aug-pc-2",
            "--- Other ---",
            "EPR-II", "EPR-III", "IGLO-II", "IGLO-III"
        ]
        self.basis_set.addItems(basis_groups)
        b_completer = QCompleter(ALL_ORCA_BASIS_SETS, self)
        b_completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        b_completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        self.basis_set.setCompleter(b_completer)
        self.basis_set.setCurrentText("def2-SVP")
        layout.addRow("Basis Set:", self.basis_set)
        
        # Auxiliary Basis (RI/RIJCOSX)
        self.aux_basis = QComboBox()
        self.aux_basis.addItems([
            "Auto (Def2/J, etc)", "None", "Def2/J", "Def2/JK", 
            "AutoAux", "NoAux"
        ])
        layout.addRow("Aux Basis (RI):", self.aux_basis)

        self.tab_method.setLayout(layout)

    def update_method_list(self):
        mtype = self.method_type.currentText()
        current_text = self.method_name.currentText()
        
        self.method_name.blockSignals(True)
        self.method_name.clear()
        
        if "GGA/Hybrid" in mtype:
             self.method_name.addItems(['B3LYP', 'B3PW91', 'B97-3c', 'B97M-rV', 'B97M-V', 'BHandHLYP', 'BLYP', 'BP', 'BP86', 'M06', 'M06-2X', 'M06-HF', 'M06-L', 'O3LYP', 'PBE', 'PBE0', 'PBEh-3c', 'PW91', 'r2SCAN-3c', 'SCAN', 'TPSS', 'TPSSh', 'X3LYP'])
        elif "Range-Separated" in mtype:
             self.method_name.addItems(['CAM-B3LYP', 'LC-wPBE', 'wB97', 'wB97M-V', 'wB97X', 'wB97X-D3', 'wB97X-V', 'wPBE', 'wPBEh'])
        elif "Double Hybrid" in mtype:
             self.method_name.addItems(['B2GP-PLYP', 'B2PLYP', 'DSD-BLYP', 'DSD-PBEP86', 'mPW2PLYP', 'PTPSS-D3', 'PWPB95'])
        elif "HF/MP2" in mtype:
             self.method_name.addItems(['HF', 'MP2', 'MP3', 'DLPNO-MP2', 'DLPNO-SCS-MP2', 'DLPNO-SOS-MP2', 'F12-DLPNO-MP2', 'F12-MP2', 'F12-RI-MP2', 'F12/D-DLPNO-MP2', 'F12/D-RI-MP2', 'OO-RI-MP2', 'OO-RI-SCS-MP2', 'OO-RI-SOS-MP2', 'RI-MP2', 'RI-SCS-MP2', 'RI-SOS-MP2', 'ROHF', 'SCS-MP2', 'SCS-MP3', 'UHF'])
        elif "Coupled Cluster" in mtype:
             self.method_name.addItems(['ACPF', 'AQCC', 'BD', 'CCSD', 'CCSD(T)', 'CCSD(T)-F12', 'CCSD(T)-F12/RI', 'CCSD(T)-F12D/RI', 'CCSD-F12', 'CCSD-F12/RI', 'CCSD-F12D/RI', 'CEPA/1', 'CEPA/2', 'CEPA/3', 'DLPNO-CCSD', 'DLPNO-CCSD(T)', 'DLPNO-CCSD(T)-F12', 'DLPNO-CCSD(T)-F12/D', 'DLPNO-CCSD(T1)', 'DLPNO-CCSD(T1)-F12', 'DLPNO-CCSD(T1)-F12/D', 'DLPNO-CCSD-F12', 'DLPNO-CCSD-F12/D', 'NCEPA/1', 'NCPF/1', 'QCISD', 'QCISD(T)', 'QCISD(T)-F12', 'QCISD(T)-F12/RI', 'QCISD-F12', 'QCISD-F12/RI', 'RI-CEPA/1-F12'])
        elif "Multireference" in mtype:
             self.method_name.addItems(['CASSCF', 'NEVPT2', 'DLPNO-NEVPT2', 'MRCI'])
        elif "Semi-Empirical" in mtype:
             self.method_name.addItems(['AM1', 'GFN-FF', 'GFN0-XTB', 'GFN1-XTB', 'GFN1-xTB', 'GFN2-XTB', 'GFN2-xTB', 'MNDO', 'NATIVE-GFN-XTB', 'NATIVE-GFN1-XTB', 'NATIVE-GFN2-XTB', 'NATIVE-spGFN-XTB', 'NATIVE-spGFN1-XTB', 'NATIVE-spGFN2-XTB', 'NATIVE-spXTB', 'NATIVE-spXTB1', 'NATIVE-spXTB2', 'NATIVE-XTB', 'NATIVE-XTB1', 'NATIVE-XTB2', 'PM3', 'PM6', 'XTB', 'XTB0', 'XTB1', 'XTB2', 'XTBFF', 'ZINDO/1', 'ZINDO/2', 'ZINDO/S', 'ZNDDO/1', 'ZNDDO/2'])
        elif mtype == "All Methods":
             self.method_name.addItems(ALL_ORCA_METHODS)
             
        if mtype == "All Methods":
            if current_text:
                self.method_name.setCurrentText(current_text)
        else:
            if self.method_name.count() > 0:
                 self.method_name.setCurrentIndex(0)
             
        self.method_name.blockSignals(False)
        self.update_ui_state()
        self.update_preview()

    def setup_job_tab(self):
        layout = QVBoxLayout()
        
        self.job_type = QComboBox()
        self.job_type.addItems([
            "Optimization + Freq (Opt Freq)", 
            "Optimization Only (Opt)", 
            "Frequency Only (Freq)", 
            "Single Point Energy (SP)",
            "NMR",
            "Scan (Relaxed Surface)",
            "Transition State Opt (OptTS)",
            "Gradient",
            "Hessian"
        ])
        layout.addWidget(QLabel("Job Task:"))
        layout.addWidget(self.job_type)
        self.job_type.currentIndexChanged.connect(self.update_ui_state)
        
        # SCF Options (Moved to below Task)
        self.scf_group = QGroupBox("SCF Convergence")
        scf_layout = QGridLayout()
        
        self.scf_sloppy = QCheckBox("Sloppy")
        self.scf_loose = QCheckBox("Loose")
        self.scf_normal = QCheckBox("Normal")
        self.scf_strong = QCheckBox("Strong")
        self.scf_tight = QCheckBox("Tight")
        self.scf_verytight = QCheckBox("VeryTight")
        self.scf_extreme = QCheckBox("Extreme")
        
        # Row 1
        scf_layout.addWidget(self.scf_sloppy, 0, 0)
        scf_layout.addWidget(self.scf_loose, 0, 1)
        scf_layout.addWidget(self.scf_normal, 0, 2)
        scf_layout.addWidget(self.scf_strong, 0, 3)
        # Row 2
        scf_layout.addWidget(self.scf_tight, 1, 0)
        scf_layout.addWidget(self.scf_verytight, 1, 1)
        scf_layout.addWidget(self.scf_extreme, 1, 2)
        
        self.scf_group.setLayout(scf_layout)
        layout.addWidget(self.scf_group)
        
        # Opt Options
        self.opt_group = QGroupBox("Optimization Options")
        opt_layout = QGridLayout()
        self.opt_tight = QCheckBox("TightOpt")
        self.opt_verytight = QCheckBox("VeryTightOpt")
        self.opt_loose = QCheckBox("LooseOpt")
        self.opt_cart = QCheckBox("COpt (Cartesian)")
        self.opt_calcfc = QCheckBox("CalcFC")
        self.opt_ts_mode = QCheckBox("CalcHess (for TS)")
        
        # Row 1: Convergence
        opt_layout.addWidget(self.opt_tight, 0, 0)
        opt_layout.addWidget(self.opt_verytight, 0, 1)
        opt_layout.addWidget(self.opt_loose, 0, 2)
        # Row 2: Methods/Hessian
        opt_layout.addWidget(self.opt_cart, 1, 0)
        opt_layout.addWidget(self.opt_calcfc, 1, 1)
        
        self.iter256_chk = QCheckBox("MaxIter 256")
        self.iter256_chk.stateChanged.connect(self.update_preview)
        opt_layout.addWidget(self.iter256_chk, 1, 2)
        
        self.opt_group.setLayout(opt_layout)
        layout.addWidget(self.opt_group)
        
        # Freq Options
        self.freq_group = QGroupBox("Freq Options")
        freq_layout = QHBoxLayout()
        self.freq_num = QCheckBox("NumFreq")
        self.freq_raman = QCheckBox("Raman")
        freq_layout.addWidget(self.freq_num)
        freq_layout.addWidget(self.freq_raman)
        self.freq_group.setLayout(freq_layout)
        layout.addWidget(self.freq_group)
        
        layout.addStretch()
        self.tab_job.setLayout(layout)

    def setup_solvation_tab(self):
        layout = QFormLayout()
        
        self.solv_model = QComboBox()
        self.solv_model.addItems(["None", "CPCM", "SMD", "IEFPCM", "CPC(Water) (Short)"])
        self.solv_model.currentIndexChanged.connect(self.update_ui_state)
        layout.addRow("Solvation Model:", self.solv_model)
        
        self.solvent = QComboBox()
        solvents = [
            "Water", "Acetonitrile", "Methanol", "Ethanol", 
            "Chloroform", "Dichloromethane", "Toluene", 
            "THF", "DMSO", "Cyclohexane", "Benzene", "Acetone",
            "CCl4", "DMF", "HMPA", "Pyridine"
        ]
        self.solvent.addItems(solvents)
        layout.addRow("Solvent:", self.solvent)
        
        layout.addRow(QLabel(" "))
        
        self.dispersion = QComboBox()
        self.dispersion.addItems(["None", "D3BJ", "D3Zero", "D4", "D2", "NL"])
        layout.addRow("Dispersion Correction:", self.dispersion)
        
        self.tab_solvation.setLayout(layout)

    def setup_props_tab(self):
        layout = QFormLayout()
        
        self.rijcosx = QCheckBox("RIJCOSX / RI approximation")
        self.rijcosx.setChecked(True)
        layout.addRow(self.rijcosx)
        
        self.grid_combo = QComboBox()
        self.grid_combo.addItems(["Default", "defgrid1", "defgrid2", "defgrid3", "Grid4", "Grid5", "Grid6", "NoGrid"])
        self.grid_combo.setCurrentText("Default")
        layout.addRow("Grid:", self.grid_combo)


        # NBO
        self.pop_nbo = QCheckBox("NBO Analysis (! NBO)")
        layout.addRow(self.pop_nbo)

        self.tab_props.setLayout(layout)

    def setup_tddft_tab(self):
        layout = QFormLayout()
        
        self.tddft_enable = QCheckBox("Enable TD-DFT (%)")
        self.tddft_enable.toggled.connect(self.update_preview)
        layout.addRow(self.tddft_enable)
        
        self.tddft_nroots = QSpinBox()
        self.tddft_nroots.setRange(1, 500)
        self.tddft_nroots.setValue(10)
        layout.addRow("Number of Roots (NRoots):", self.tddft_nroots)
        
        self.tddft_singlets = QCheckBox("Singlets")
        self.tddft_singlets.setChecked(True)
        self.tddft_triplets = QCheckBox("Triplets")
        self.tddft_triplets.setChecked(False)
        
        s_layout = QHBoxLayout()
        s_layout.addWidget(self.tddft_singlets)
        s_layout.addWidget(self.tddft_triplets)
        layout.addRow("States:", s_layout)
        
        self.tddft_tda = QCheckBox("Use TDA (Tamm-Dancoff Approximation)")
        self.tddft_tda.setChecked(True)
        layout.addRow(self.tddft_tda)
        
        self.tddft_iroot = QSpinBox()
        self.tddft_iroot.setRange(1, 500)
        self.tddft_iroot.setValue(1)
        layout.addRow("Root for Polar./Grad. (IRoot):", self.tddft_iroot)

        self.tab_tddft.setLayout(layout)

    def setup_constraints_tab(self):
        layout = QVBoxLayout()
        
        info_label = QLabel("Select 1-4 atoms in the 3D view to add constraints or scans.\n"
                            "1: Position, 2: Distance, 3: Angle, 4: Dihedral")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.selection_label = QLabel("Selected atoms: None")
        self.selection_label.setStyleSheet("font-weight: bold; color: #D32F2F;")
        layout.addWidget(self.selection_label)

        self.constraint_table = QTableWidget()
        self.constraint_table.setColumnCount(7)
        self.constraint_table.setHorizontalHeaderLabels(["Type", "Indices", "Value", "Scan?", "Start", "End", "Steps"])
        self.constraint_table.itemSelectionChanged.connect(self.update_selection_display)
        self.constraint_table.itemChanged.connect(self.update_preview)
        layout.addWidget(self.constraint_table)

        btn_layout = QHBoxLayout()
        self.btn_add_const = QPushButton("Add Constraint")
        self.btn_add_const.setEnabled(False)
        self.btn_add_const.clicked.connect(self.add_constraint)
        btn_layout.addWidget(self.btn_add_const)

        self.btn_remove_const = QPushButton("Remove Selected")
        self.btn_remove_const.clicked.connect(self.remove_constraint)
        btn_layout.addWidget(self.btn_remove_const)
        
        self.btn_clear_const = QPushButton("Clear All")
        self.btn_clear_const.clicked.connect(self.clear_all_constraints)
        btn_layout.addWidget(self.btn_clear_const)

        layout.addLayout(btn_layout)
        
        layout.addWidget(QLabel("<font color='gray'>Note: Indices are 0-based.</font>"))
        self.tab_constraints.setLayout(layout)

    def on_tab_changed(self, index):
        # Index 5 is Constraints/Scan
        if index == 5:
            self.enable_picking()
        else:
            self.disable_picking()

    def on_atom_picked(self, atom_idx):
        if atom_idx in self.selected_atoms:
            self.selected_atoms.remove(atom_idx)
        else:
            if len(self.selected_atoms) >= 4:
                self.selected_atoms.pop(0)
            self.selected_atoms.append(atom_idx)
        self.update_selection_display()

    def clear_selection(self):
        self.selected_atoms = []
        self.update_selection_display()

    def update_selection_display(self):
        self.clear_selection_labels()
        
        all_to_label = [] # list of (idx, label_text)
        
        # 1. From active picking
        for i, idx in enumerate(self.selected_atoms):
            all_to_label.append((idx, f"P{i+1}")) # P for Picking
            
        # 2. From table selection
        selected_rows = set(index.row() for index in self.constraint_table.selectedIndexes())
        for row in selected_rows:
            idx_item = self.constraint_table.item(row, 1)
            if idx_item:
                try:
                    row_indices = [int(i) for i in idx_item.text().split()]
                    for i, idx in enumerate(row_indices):
                        all_to_label.append((idx, f"C{row+1}:A{i+1}"))
                except: pass
        
        if all_to_label and self.main_window and hasattr(self.main_window, 'atom_positions_3d'):
            positions = []
            texts = []
            # Keep unique to avoid overlapping labels on same atom? 
            # VTK handles overlapping somewhat, but let's just add them.
            for idx, txt in all_to_label:
                if 0 <= idx < len(self.main_window.atom_positions_3d):
                    positions.append(self.main_window.atom_positions_3d[idx])
                    texts.append(txt)
            if positions:
                label_actor = self.main_window.plotter.add_point_labels(positions, texts, always_visible=True, text_color="yellow")
                self.selection_labels.append(label_actor)

        n = len(self.selected_atoms)
        txt = "None"
        can_add = False
        if n > 0:
            indices_txt = ", ".join(map(str, self.selected_atoms))
            types = {1: "Position", 2: "Distance", 3: "Angle", 4: "Dihedral"}
            txt = f"[{indices_txt}] ({types.get(n, 'Unknown')})"
            can_add = True
            
        self.selection_label.setText(f"Selected atoms: {txt}")
        self.btn_add_const.setEnabled(can_add)

    def add_constraint(self):
        n = len(self.selected_atoms)
        if n == 0 or not self.mol: return
        
        indices = tuple(self.selected_atoms)
        conf = self.mol.GetConformer()
        
        val = 0.0
        c_type = ""
        if n == 1:
            c_type = "Position"
            val = 0.0
        elif n == 2:
            c_type = "Distance"
            val = rdMolTransforms.GetBondLength(conf, *indices)
        elif n == 3:
            c_type = "Angle"
            val = rdMolTransforms.GetAngleDeg(conf, *indices)
        elif n == 4:
            c_type = "Dihedral"
            val = rdMolTransforms.GetDihedralDeg(conf, *indices)
            
        row = self.constraint_table.rowCount()
        self.constraint_table.insertRow(row)
        
        def create_centered_item(text):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            return item

        self.constraint_table.setItem(row, 0, create_centered_item(c_type))
        idx_str = " ".join(map(str, indices))
        self.constraint_table.setItem(row, 1, create_centered_item(idx_str))
        self.constraint_table.setItem(row, 2, create_centered_item(f"{val:.3f}"))
        
        chk_scan = QCheckBox()
        # Center checkbox
        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.addWidget(chk_scan)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk_layout.setContentsMargins(0,0,0,0)
        self.constraint_table.setCellWidget(row, 3, chk_widget)
        
        start_item = create_centered_item(f"{val:.3f}")
        end_item = create_centered_item(f"{val+0.5:.3f}")
        steps_item = create_centered_item("10")
        
        self.constraint_table.setItem(row, 4, start_item)
        self.constraint_table.setItem(row, 5, end_item)
        self.constraint_table.setItem(row, 6, steps_item)

        def sync_scan_state():
            is_on = chk_scan.isChecked()
            for col in [4, 5, 6]:
                it = self.constraint_table.item(row, col)
                if it:
                    if is_on:
                        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEnabled)
                        it.setForeground(Qt.GlobalColor.black)
                    else:
                        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                        it.setForeground(Qt.GlobalColor.gray)
            self.update_preview()

        chk_scan.stateChanged.connect(sync_scan_state)
        sync_scan_state()
        
        self.selected_atoms = []
        self.update_selection_display()
        self.update_preview()

    def remove_constraint(self):
        rows = set(index.row() for index in self.constraint_table.selectedIndexes())
        for row in sorted(list(rows), reverse=True):
            self.constraint_table.removeRow(row)
        self.update_preview()

    def clear_all_constraints(self):
        self.constraint_table.setRowCount(0)
        self.update_preview()

    def get_constraints_text(self):
        """Builds ORCA %geom block parts for constraints and scans."""
        const_lines = []
        scan_lines = []
        
        for r in range(self.constraint_table.rowCount()):
            c_type_item = self.constraint_table.item(r, 0)
            idx_item = self.constraint_table.item(r, 1)
            if not c_type_item or not idx_item: continue
            
            c_type = c_type_item.text()
            idx_str = idx_item.text()
            val_item = self.constraint_table.item(r, 2)
            value = val_item.text() if val_item else "0.0"
            
            chk_widget = self.constraint_table.cellWidget(r, 3)
            if not chk_widget: continue # Should have QCheckBox inside WIdget
            chk_scan = chk_widget.findChild(QCheckBox)
            if not chk_scan: continue
            is_scan = chk_scan.isChecked()
            
            prefix = {"Position": "C", "Distance": "B", "Angle": "A", "Dihedral": "D"}.get(c_type, "B")
            
            if is_scan:
                start_item = self.constraint_table.item(r, 4)
                end_item = self.constraint_table.item(r, 5)
                steps_item = self.constraint_table.item(r, 6)
                if not start_item or not end_item or not steps_item: continue
                
                start = start_item.text()
                end = end_item.text()
                steps = steps_item.text()
                scan_lines.append(f"    {prefix} {idx_str} = {start}, {end}, {steps}")
            else:
                if c_type == "Position":
                    const_lines.append(f"    {{ {prefix} {idx_str} C }}")
                else:
                    const_lines.append(f"    {{ {prefix} {idx_str} {value} C }}")

        res = ""
        if const_lines:
            res += "  Constraints\n" + "\n".join(const_lines) + "\n  end\n"
        if scan_lines:
            res += "  Scan\n" + "\n".join(scan_lines) + "\n  end\n"
        return res

    def connect_signals(self):
        widgets = [
            self.method_type, self.method_name, self.basis_set, self.aux_basis,
            self.job_type, self.opt_tight, self.opt_verytight, self.opt_loose, 
            self.opt_cart, self.opt_calcfc,
            self.freq_num, self.freq_raman,
            self.solv_model, self.solvent, self.dispersion,
            self.rijcosx, self.grid_combo, 
            self.scf_sloppy, self.scf_loose, self.scf_normal, self.scf_strong, 
            self.scf_tight, self.scf_verytight, self.scf_extreme,
            self.pop_nbo, self.tddft_enable, self.tddft_nroots, self.tddft_singlets, 
            self.tddft_triplets, self.tddft_tda, self.tddft_iroot
        ]
        for w in widgets:
            if isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self.update_preview)
                if w.isEditable():
                    w.currentTextChanged.connect(self.update_preview)
            elif isinstance(w, QCheckBox):
                w.toggled.connect(self.update_preview)
                # Mutual exclusivity for SCF
                if w in [self.scf_sloppy, self.scf_loose, self.scf_normal, self.scf_strong, 
                           self.scf_tight, self.scf_verytight, self.scf_extreme]:
                    w.clicked.connect(self.enforce_scf_mutual_exclusion)
                # Mutual exclusivity for Opt
                if w in [self.opt_tight, self.opt_verytight, self.opt_loose]:
                    w.clicked.connect(self.enforce_opt_mutual_exclusion)
            elif isinstance(w, QSpinBox):
                w.valueChanged.connect(self.update_preview)
            elif isinstance(w, (QTextEdit, QPlainTextEdit)):
                w.textChanged.connect(self.update_preview)

    def update_ui_state(self):
        """Update usability of widgets based on current selection."""
        if not getattr(self, 'ui_ready', False): return

        # 1. Method Dependent
        method_text = self.method_name.currentText()
        mtype = self.get_inferred_category(method_text)
        is_semi = "Semi-Empirical" in mtype
        is_3c = "3C" in method_text.upper()
        no_basis = is_semi or is_3c
        
        # Disable Basis Set & Aux Basis for Semi-Empirical and 3c
        self.basis_set.setEnabled(not no_basis)
        self.aux_basis.setEnabled(not no_basis)
        
        # Handling RI / RIJCOSX
        if is_semi:
            self.rijcosx.setEnabled(False)
            self.rijcosx.setChecked(False)
            self.rijcosx.setText("RIJCOSX (N/A)")
        else:
            self.rijcosx.setEnabled(True)
            if "Wavefunction" in mtype:
                self.rijcosx.setText("RI Approximation (! RI ...)")
            else:
                self.rijcosx.setText("RIJCOSX (Speed up Hybrid DFT)")

        # 2. Solvation
        solv = self.solv_model.currentText()
        is_solvated = solv != "None"
        self.solvent.setEnabled(is_solvated)
        if "CPC(Water)" in solv:
             self.solvent.setEnabled(False) # Water is implied

        # 3. Job Type
        job_txt = self.job_type.currentText()
        is_opt = "Opt" in job_txt or "Scan" in job_txt
        is_freq = "Freq" in job_txt
        
        self.opt_group.setVisible(is_opt)
        self.freq_group.setVisible(is_freq)
        
        # 4. TD-DFT (Removed from Route Builder, handled via blocks)

    def enforce_scf_mutual_exclusion(self):
        ctx = self.sender()
        if not ctx.isChecked(): return
        scf_boxes = [
            self.scf_sloppy, self.scf_loose, self.scf_normal, self.scf_strong, 
            self.scf_tight, self.scf_verytight, self.scf_extreme
        ]
        for cb in scf_boxes:
            if cb != ctx:
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
        self.update_preview()

    def enforce_opt_mutual_exclusion(self):
        ctx = self.sender()
        if not ctx.isChecked(): return
        for cb in [self.opt_tight, self.opt_verytight, self.opt_loose]:
            if cb != ctx:
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
        self.update_preview()

    def update_preview(self):
        if not getattr(self, 'ui_ready', False):
            return
        self.update_ui_state()

        route_parts = ["!"]
        
        # Method / Basis
        method = self.method_name.currentText()
        basis = self.basis_set.currentText()
        
        # 3c methods usually don't need basis set
        mtype = self.get_inferred_category(self.method_name.currentText())
        if "Semi-Empirical" in mtype:
            route_parts.append(method)
        elif "3c" in method:
            route_parts.append(method)
        else:
            route_parts.append(method)
            route_parts.append(basis)
            
            # RIJCOSX / RI
            if self.rijcosx.isEnabled() and self.rijcosx.isChecked():
                if "Wavefunction" in mtype:
                     route_parts.append("RI")
                else:
                     route_parts.append("RIJCOSX")
                     
                aux = self.aux_basis.currentText()
                if "Def2/J" in aux: route_parts.append("Def2/J")
                elif "Def2/JK" in aux: route_parts.append("Def2/JK")

        # Job Type and Opt Options
        job_txt = self.job_type.currentText()
        is_opt_job = "Opt" in job_txt or "Scan" in job_txt
        
        # Determine convergence level
        opt_conv = ""
        if self.opt_tight.isChecked(): opt_conv = "TightOpt"
        elif self.opt_verytight.isChecked(): opt_conv = "VeryTightOpt"
        elif self.opt_loose.isChecked(): opt_conv = "LooseOpt"

        if "Opt Freq" in job_txt: 
            route_parts.append(opt_conv if opt_conv else "Opt")
            route_parts.append("Freq")
        elif "Opt Only" in job_txt: 
            route_parts.append(opt_conv if opt_conv else "Opt")
        elif "OptTS" in job_txt: 
            route_parts.append("OptTS")
            if opt_conv: route_parts.append(opt_conv)
        elif "Freq Only" in job_txt: route_parts.append("Freq")
        elif "Scan" in job_txt: 
            route_parts.append("Scan")
            if opt_conv: route_parts.append(opt_conv)
        elif "Gradient" in job_txt: route_parts.append("Gradient")
        elif "Hessian" in job_txt: route_parts.append("Hessian")
        elif "NMR" in job_txt: route_parts.append("NMR")
        elif "SP" in job_txt: pass # No keyword
        
        # Other Opt Options (only if it's an opt job)
        if is_opt_job:
            if self.opt_cart.isChecked(): route_parts.append("COpt")
            if self.opt_calcfc.isChecked(): route_parts.append("CalcFC")
        
        # Freq Options
        if self.freq_group.isVisible():
            if self.freq_num.isChecked(): route_parts.append("NumFreq")
        
        # Solvation
        solv = self.solv_model.currentText()
        if solv != "None":
            if "CPC(Water)" in solv:
                 route_parts.append("CPC(Water)")
            else:
                solvent = self.solvent.currentText()
                if "CPCM" == solv:
                    route_parts.append(f"CPCM({solvent})")
                elif "SMD" == solv:
                    route_parts.append(f"CPCM({solvent})")
                    route_parts.append("SMD")
                elif "IEFPCM" == solv:
                    route_parts.append(f"CPCM({solvent})") 
        
        # Dispersion
        disp = self.dispersion.currentText()
        if disp != "None":
            route_parts.append(disp)

        # SCF / Grid
        if self.scf_sloppy.isChecked(): route_parts.append("SloppySCF")
        elif self.scf_loose.isChecked(): route_parts.append("LooseSCF")
        elif self.scf_normal.isChecked(): route_parts.append("NormalSCF")
        elif self.scf_strong.isChecked(): route_parts.append("StrongSCF")
        elif self.scf_tight.isChecked(): route_parts.append("TightSCF")
        elif self.scf_verytight.isChecked(): route_parts.append("VeryTightSCF")
        elif self.scf_extreme.isChecked(): route_parts.append("ExtremeSCF")
        
        grid = self.grid_combo.currentText()
        if grid != "Default": route_parts.append(grid)
        
        # NBO
        if self.pop_nbo.isChecked(): route_parts.append("NBO")

        self.route_line = " ".join(route_parts)
        self.preview_str = self.route_line
        
        extra = self.get_extra_blocks_text()
        if extra:
            self.preview_str += "\n\n" + extra
        
        self.preview_label.setText(self.preview_str)
        # (Live sync to parent removed by request)

    def get_route(self):
        # When finishing, return the full route + blocks to be saved in the text box
        return self.preview_str

    def get_extra_blocks_text(self):
        """Returns all %blocks (TD-DFT, Geom Constraints/Scans) as a string."""
        blocks = []
        
        # 1. TD-DFT
        if hasattr(self, "tddft_enable") and self.tddft_enable.isChecked():
            block = (
                f"%tddft\n"
                f"  NRoots {self.tddft_nroots.value()}\n"
                f"  Singlets {'true' if self.tddft_singlets.isChecked() else 'false'}\n"
                f"  Triplets {'true' if self.tddft_triplets.isChecked() else 'false'}\n"
                f"  TDA {'true' if self.tddft_tda.isChecked() else 'false'}\n"
                f"  IRoot {self.tddft_iroot.value()}\n"
                f"end"
            )
            blocks.append(block)
            
        # 2. Constraints & Scan
        if hasattr(self, "constraint_table"):
            geom_text = self.get_constraints_text()
            # Add MaxIter 256 if checked
            if self.iter256_chk.isChecked():
                geom_text = "  MaxIter 256\n" + geom_text
                
            if geom_text:
                blocks.append(f"%geom\n{geom_text}end")
                
        return "\n\n".join(blocks)
        
    def parse_route(self, route):
        if not route: return
        self.ui_ready = False 
        
        # Reset defaults before parsing so we don't accumulate old checks
        self.opt_tight.setChecked(False)
        self.opt_verytight.setChecked(False)
        self.opt_loose.setChecked(False)
        self.opt_cart.setChecked(False)
        self.opt_calcfc.setChecked(False)
        
        self.freq_num.setChecked(False)
        self.freq_raman.setChecked(False)
        
        self.job_type.setCurrentText("Single Point Energy (SP)")
        
        self.scf_sloppy.setChecked(False)
        self.scf_loose.setChecked(False)
        self.scf_normal.setChecked(False)
        self.scf_strong.setChecked(False)
        self.scf_tight.setChecked(False)
        self.scf_verytight.setChecked(False)
        self.scf_extreme.setChecked(False)
        
        self.dispersion.setCurrentText("None")
        self.solv_model.setCurrentText("None")
        self.rijcosx.setChecked(False)
        self.pop_nbo.setChecked(False)
        self.tddft_enable.setChecked(False)
        self.constraint_table.setRowCount(0)
        
        # Normalize route
        cleaned_route = route.strip()
        if cleaned_route.startswith("!"):
            cleaned_route = cleaned_route[1:].strip()
            
        tokens = cleaned_route.split()
        if not tokens: 
            self.ui_ready = True
            return

        method_list_upper = [m.upper() for m in ALL_ORCA_METHODS]
        basis_list_upper = [b.upper() for b in ALL_ORCA_BASIS_SETS]
        
        found_method = False
        found_basis = False
        
        for t in tokens:
            tu = t.upper()
            
            # 1. Method & Basis (Priority)
            if not found_method and tu in method_list_upper:
                idx = method_list_upper.index(tu)
                self.method_name.setCurrentText(ALL_ORCA_METHODS[idx])
                found_method = True
                continue
            elif not found_basis and tu in basis_list_upper:
                idx = basis_list_upper.index(tu)
                self.basis_set.setCurrentText(ALL_ORCA_BASIS_SETS[idx])
                found_basis = True
                continue
            
            # 2. Job Types
            if tu in ["OPT", "TIGHTOPT", "VERYTIGHTOPT", "LOOSEOPT"]:
                 if self.job_type.currentText() == "Frequency Only (Freq)":
                      self.job_type.setCurrentText("Optimization + Freq (Opt Freq)")
                 else:
                      self.job_type.setCurrentText("Optimization Only (Opt)")
            elif tu == "FREQ": 
                if self.job_type.currentText() == "Optimization Only (Opt)":
                    self.job_type.setCurrentText("Optimization + Freq (Opt Freq)")
                else:
                    self.job_type.setCurrentText("Frequency Only (Freq)")
            elif tu == "OPTTS": self.job_type.setCurrentText("Transition State Opt (OptTS)")
            elif tu == "SCAN": self.job_type.setCurrentText("Scan (Relaxed Surface)")
            elif tu == "NMR": self.job_type.setCurrentText("NMR")
            elif tu in ["GRADIENT", "HESSIAN"]:
                # Direct match for Gradient/Hessian
                for i in range(self.job_type.count()):
                    if tu in self.job_type.itemText(i).upper():
                        self.job_type.setCurrentIndex(i)
                        break
            
            # 3. Opt Options
            if tu == "TIGHTOPT": self.opt_tight.setChecked(True)
            elif tu == "VERYTIGHTOPT": self.opt_verytight.setChecked(True)
            elif tu == "LOOSEOPT": self.opt_loose.setChecked(True)
            elif tu == "COPT": self.opt_cart.setChecked(True)
            elif tu == "CALCFC": self.opt_calcfc.setChecked(True)
            
            # 4. Freq Options
            if tu == "NUMFREQ": self.freq_num.setChecked(True)
            if tu == "RAMAN": self.freq_raman.setChecked(True)
            
            # 5. Solvation
            if "(" in tu and any(x in tu for x in ["CPCM", "SMD", "IEFPCM"]):
                s_model = tu.split("(")[0]
                s_name = t.split("(")[1].split(")")[0]
                
                if s_model == "CPCM": self.solv_model.setCurrentText("CPCM")
                elif s_model == "SMD": self.solv_model.setCurrentText("SMD")
                elif s_model == "IEFPCM": self.solv_model.setCurrentText("IEFPCM")
                
                for i in range(self.solvent.count()):
                    if self.solvent.itemText(i).upper() == s_name.upper():
                        self.solvent.setCurrentIndex(i)
                        break
            elif tu == "SMD": self.solv_model.setCurrentText("SMD")
            elif tu == "CPC(WATER)": self.solv_model.setCurrentText("CPC(Water) (Short)")
            
            # 6. Dispersion
            if tu in ["D3BJ", "D3ZERO", "D4", "D2", "NL"]:
                self.dispersion.setCurrentText(tu)
            
            # 7. RI / RIJCOSX
            if tu in ["RIJCOSX", "RI"]:
                self.rijcosx.setChecked(True)
            
            # 8. Aux Basis
            if tu == "DEF2/J": self.aux_basis.setCurrentText("Def2/J")
            elif tu == "DEF2/JK": self.aux_basis.setCurrentText("Def2/JK")
            elif tu == "AUTOMX": self.aux_basis.setCurrentText("AutoAux")
            
            # 9. SCF / Grid
            if tu == "SLOPPYSCF": self.scf_sloppy.setChecked(True)
            elif tu == "LOOSESCF": self.scf_loose.setChecked(True)
            elif tu == "NORMALSCF": self.scf_normal.setChecked(True)
            elif tu == "STRONGSCF": self.scf_strong.setChecked(True)
            elif tu == "TIGHTSCF": self.scf_tight.setChecked(True)
            elif tu == "VERYTIGHTSCF": self.scf_verytight.setChecked(True)
            elif tu == "EXTREMESCF": self.scf_extreme.setChecked(True)
            
            # 10. NBO
            if tu == "NBO": self.pop_nbo.setChecked(True)

        # --- AFTER THE LOOP ends ---
        # 11. Detect MaxIter 256 in the whole input string
        if "MaxIter 256" in route:
            self.iter256_chk.setChecked(True)

        # 2. Parse Blocks (%geom, %tddft)
        import re
        
        # Split by % to get blocks (e.g. ['! ...', '%geom ...', '%scf ...'])
        block_sections = re.split(r'(?=%[a-zA-Z])', route)
        for section in block_sections:
            section = section.strip()
            if not section.startswith("%"): 
                # Check for MaxIter 256 in the ! line or comments just in case
                if re.search(r"MaxIter\s+256", section, re.I):
                    self.iter256_chk.setChecked(True)
                continue
            
            # Extract block name and content
            m_block = re.match(r"%(\w+)\s+(.*)", section, re.S | re.I)
            if not m_block: continue
            
            bname = m_block.group(1).lower()
            bcontent = m_block.group(2).strip()
            
            # Strip the final 'end' of the block if it exists
            if bcontent.lower().endswith("end"):
                # Be careful not to strip 'end' of a sub-block if that's all there is
                # But since we split by %, this section should be exactly one block.
                # Find the LAST 'end' and strip it.
                last_end_idx = bcontent.lower().rfind("end")
                if last_end_idx != -1:
                    bcontent = bcontent[:last_end_idx].strip()
            
            if bname == "tddft":
                self.tddft_enable.setChecked(True)
                nr = re.search(r"NRoots\s+(\d+)", bcontent, re.I)
                if nr: self.tddft_nroots.setValue(int(nr.group(1)))
                ir = re.search(r"IRoot\s+(\d+)", bcontent, re.I)
                if ir: self.tddft_iroot.setValue(int(ir.group(1)))
                self.tddft_singlets.setChecked("singlets true" in bcontent.lower())
                self.tddft_triplets.setChecked("triplets true" in bcontent.lower())
                self.tddft_tda.setChecked("tda true" in bcontent.lower())
                
            elif bname == "geom":
                if re.search(r"MaxIter\s+256", bcontent, re.I):
                    self.iter256_chk.setChecked(True)
                
                # Constraints sub-block
                const_match = re.search(r"Constraints\s+(.*?)\s+end", bcontent, re.I | re.S)
                if const_match:
                    for line in const_match.group(1).splitlines():
                        line = line.strip()
                        if not line: continue
                        # { B 0 1 1.5 C } or { C 0 C }
                        m = re.search(r"\{\s*(\w)\s+(.*?)\s+C\s*\}", line, re.I)
                        if m:
                            c_type_char = m.group(1).upper()
                            parts = m.group(2).split()
                            if parts:
                                c_type = {"B": "Distance", "A": "Angle", "D": "Dihedral", "C": "Position"}.get(c_type_char, "Distance")
                                if c_type == "Position":
                                    idx_str = " ".join(parts)
                                    val = "0.0"
                                else:
                                    val = parts[-1]
                                    idx_str = " ".join(parts[:-1])
                                self._add_parsed_constraint(c_type, idx_str, val, False)
                
                # Scan sub-block
                scan_match = re.search(r"Scan\s+(.*?)\s+end", bcontent, re.I | re.S)
                if scan_match:
                    for line in scan_match.group(1).splitlines():
                        line = line.strip()
                        if not line: continue
                        # B 0 1 = 1.0, 2.0, 10
                        m = re.search(r"^([BADC])\s+(.*?)\s*=\s*([^,]+),\s*([^,]+),\s*(\d+)", line, re.I)
                        if m:
                            c_type_char = m.group(1).upper()
                            idx_str = m.group(2).strip()
                            start = m.group(3).strip()
                            end = m.group(4).strip()
                            steps = m.group(5).strip()
                            c_type = {"B": "Distance", "A": "Angle", "D": "Dihedral", "C": "Position"}.get(c_type_char, "Distance")
                            self._add_parsed_constraint(c_type, idx_str, start, True, end, steps)

        self.ui_ready = True
        self.update_ui_state()
        self.update_preview()

    def _add_parsed_constraint(self, c_type, indices_str, value, is_scan, end="0.0", steps="10"):
        row = self.constraint_table.rowCount()
        self.constraint_table.insertRow(row)
        
        def create_centered_item(text):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            return item

        self.constraint_table.setItem(row, 0, create_centered_item(c_type))
        self.constraint_table.setItem(row, 1, create_centered_item(indices_str))
        self.constraint_table.setItem(row, 2, create_centered_item(value))
        
        chk_scan = QCheckBox()
        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.addWidget(chk_scan)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk_layout.setContentsMargins(0,0,0,0)
        self.constraint_table.setCellWidget(row, 3, chk_widget)
        
        self.constraint_table.setItem(row, 4, create_centered_item(value if is_scan else value))
        self.constraint_table.setItem(row, 5, create_centered_item(end))
        self.constraint_table.setItem(row, 6, create_centered_item(steps))

        def sync_scan_state():
            is_on = chk_scan.isChecked()
            for col in [4, 5, 6]:
                it = self.constraint_table.item(row, col)
                if it:
                    if is_on:
                        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEnabled)
                        it.setForeground(Qt.GlobalColor.black)
                    else:
                        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                        it.setForeground(Qt.GlobalColor.gray)
            self.update_preview()

        chk_scan.stateChanged.connect(sync_scan_state)
        chk_scan.setChecked(is_scan)
        sync_scan_state()

    def closeEvent(self, event):
        self.disable_picking()
        super().closeEvent(event)

    def accept(self):
        self.disable_picking()
        super().accept()

    def reject(self):
        self.disable_picking()
        super().reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            focused = self.focusWidget()
            if isinstance(focused, (QLineEdit, QComboBox, QSpinBox, QTextEdit)):
                focused.clearFocus()
                return
        super().keyPressEvent(event)