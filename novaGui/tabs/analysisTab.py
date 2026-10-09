
# -- Analyze Tab -- #

'''

Scalar results from the run: sizing, the chamber, delivered performance, station thermochemistry
from CEA, the regenerative cooling summary when a jacket was built, and the plume. The figures that
go with them are on the View tab.

Author: Sean Bowman
Date:   08/28/2026

'''

import math
from tkinter import ttk

from .. import theme
from ..widgets import card

def _num(value):

    '''

    Coerce NOVA's mix of scalars, 0-d arrays and empty lists to a float, or None.

    '''

    try:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return None if len(value) == 0 else float(value[-1])
        result = float(value)
        return None if math.isnan(result) else result
    except (TypeError, ValueError):
        return None

class AnalysisTab(ttk.Frame):

    '''

    Grouped result table.

    '''

    def __init__(self, master, app):

        super().__init__(master, style = 'TFrame', padding = theme.scaled(8))

        self._app = app

        header = ttk.Frame(self, style = 'TFrame', padding = (theme.scaled(4), 0, theme.scaled(4), theme.scaled(6)))
        header.pack(fill = 'x')
        ttk.Label(header, text = 'RESULTS', style = 'Eyebrow.TLabel').pack(side = 'left')
        self._summary = ttk.Label(header, text = '', style = 'Muted.TLabel')
        self._summary.pack(side = 'left', padx = theme.scaled(12))

        treeWrap = card(self, fill = 'both', expand = True)
        self._tree = ttk.Treeview(treeWrap, columns = ('value',), show = 'tree headings', height = 24)
        self._tree.heading('#0', text = 'Quantity')
        self._tree.heading('value', text = 'Value')
        self._tree.column('#0', width = theme.scaled(340), anchor = 'w')
        self._tree.column('value', width = theme.scaled(220), anchor = 'e')
        scroll = ttk.Scrollbar(treeWrap, orient = 'vertical', command = self._tree.yview, style = 'Card.Vertical.TScrollbar')
        self._tree.configure(yscrollcommand = scroll.set)
        scroll.pack(side = 'right', fill = 'y')
        self._tree.pack(side = 'left', fill = 'both', expand = True)

        self._placeholder()

    def _placeholder(self) -> None:

        self._tree.delete(*self._tree.get_children())
        node = self._tree.insert('', 'end', text = 'No run yet', open = True)
        self._tree.insert(node, 'end', text = 'Generate a nozzle from the Design tab', values = ('',))

    def refresh(self, runResult) -> None:

        nozzle = getattr(runResult, 'nozzle', None)
        if nozzle is None:
            self._placeholder()
            return

        self._tree.delete(*self._tree.get_children())
        cea = getattr(nozzle, 'ceaOutput', None)
        ceaResults = getattr(cea, 'ceaResults', {}) if cea is not None else {}
        performance = getattr(cea, 'nozzlePerformance', None) if cea is not None else None
        performance = performance or {}

        def section(title):
            return self._tree.insert('', 'end', text = title, open = True)

        def row(parent, label, value, fmt = '{:.4g}', unit = ''):
            number = _num(value) if not isinstance(value, str) else value
            if number is None or number == '':
                text = '--'
            elif isinstance(number, str):
                text = number
            else:
                text = fmt.format(number) + (f' {unit}' if unit else '')
            self._tree.insert(parent, 'end', text = label, values = (text,))

        def ceaGet(key):
            try:
                return ceaResults.get(key)
            except Exception:
                return None

        sizing = section('Sizing')
        row(sizing, 'Thrust', getattr(nozzle, 'thrust', None), '{:.0f}', 'N')
        row(sizing, 'Engine mass flow', getattr(nozzle, 'engineMassFlow', None), '{:.3f}', 'kg/s')
        row(sizing, 'Throat radius', self._throatRadius(nozzle), '{:.2f}', 'mm')
        row(sizing, 'Exit radius', self._exitRadius(nozzle), '{:.2f}', 'mm')
        row(sizing, 'Contour length', self._length(nozzle), '{:.1f}', 'mm')
        row(sizing, 'Expansion ratio (1D)', getattr(nozzle, 'expansionRatio', None))
        row(sizing, 'Geometric area ratio', getattr(nozzle, 'exitExpansionRatio', None))
        row(sizing, 'Contraction ratio', getattr(nozzle, 'inletContractionRatio', None))
        row(sizing, 'Exit pressure (1D)', getattr(nozzle, 'targetExitPressure', None), '{:.0f}', 'Pa')

        chamberGeometry = section('Combustion Chamber')
        row(chamberGeometry, 'Barrel length', self._mm(getattr(nozzle, 'chamberBarrelLength', None)), '{:.1f}', 'mm')
        row(chamberGeometry, 'Chamber volume', self._cm3(getattr(nozzle, 'chamberVolume', None)), '{:.1f}', 'cm3')
        row(chamberGeometry, 'Characteristic length L*', getattr(nozzle, 'chamberLstarActual', None), '{:.4f}', 'm')
        row(chamberGeometry, 'Contraction ratio', getattr(nozzle, 'chamberContractionRatio', None))
        row(chamberGeometry, 'Chamber diameter', self._mm(getattr(nozzle, 'chamberDiameter', None)), '{:.1f}', 'mm')

        perf = section('Performance')
        row(perf, 'Ideal Isp', performance.get('idealISP[s]'), '{:.1f}', 's')
        row(perf, 'Vacuum Isp', performance.get('vacuumISP[s]'), '{:.1f}', 's')
        row(perf, 'Sea level Isp', performance.get('seaLevelISP[s]'), '{:.1f}', 's')
        row(perf, 'Vacuum thrust coefficient', performance.get('vacuumThrustCoef'))
        row(perf, 'Characteristic velocity', ceaGet('characteristicVelocity'), '{:.1f}', 'm/s')
        row(perf, 'Exit Mach', getattr(nozzle, 'exitMachNumber', None) or ceaGet('exitMach'))
        row(perf, 'Ideal Mach', getattr(nozzle, 'idealMachNumber', None))
        row(perf, 'Operating mode', performance.get('mode') or '--')

        chamber = section('Chamber')
        row(chamber, 'Temperature', ceaGet('combustionChamberTemperature')
            or getattr(nozzle, 'chamberStagnationTemperature', None), '{:.1f}', 'K')
        row(chamber, 'Pressure', getattr(nozzle, 'chamberPressure', None), '{:.0f}', 'Pa')
        row(chamber, 'Gamma', getattr(nozzle, 'chamberGamma', None) or ceaGet('combustionChamberGamma'))
        row(chamber, 'Molecular weight', ceaGet('combustionChamberMolecularWeight'), '{:.3f}', 'g/mol')
        row(chamber, 'Gas constant', getattr(nozzle, 'chamberRGasConstant', None), '{:.1f}', 'J/kg-K')
        row(chamber, 'Prandtl number', ceaGet('combustionChamberPrandtlNumber'))

        throat = section('Throat')
        row(throat, 'Temperature', ceaGet('throatTemperature'), '{:.1f}', 'K')
        row(throat, 'Pressure', ceaGet('throatPressure'), '{:.0f}', 'Pa')
        row(throat, 'Gamma', ceaGet('throatGamma') or getattr(nozzle, 'throatGamma', None))

        exit_ = section('Exit')
        row(exit_, 'Temperature', ceaGet('exitTemperature'), '{:.1f}', 'K')
        row(exit_, 'Pressure', ceaGet('exitPressure'), '{:.0f}', 'Pa')
        row(exit_, 'Mach', ceaGet('exitMach'))
        row(exit_, 'Velocity', ceaGet('exitVelocity'), '{:.1f}', 'm/s')

        if str(getattr(nozzle, 'makeCoolingChannels', 'off')) not in ('off', 'False', ''):
            cooling = section('Cooling')
            row(cooling, 'Number of channels', getattr(nozzle, 'nChannel', None), '{:.0f}')
            row(cooling, 'Max hot wall temperature', getattr(nozzle, 'maxWallTemperature', None), '{:.1f}', 'K')
            row(cooling, 'Coolant exit temperature',
                getattr(nozzle, 'coolantExitTemperature', None), '{:.1f}', 'K')
            row(cooling, 'Coolant exit pressure',
                getattr(nozzle, 'coolantExitPressure', None), '{:.0f}', 'Pa')
            row(cooling, 'Coolant mass flow', getattr(nozzle, 'coolantMassFlow', None), '{:.3f}', 'kg/s')

        # The march's own numbers first, because they say whether its picture can be used, then
        # the correlated quantities the march cannot produce
        structure = getattr(nozzle, 'nozzlePlumeStructure', None)
        field = getattr(nozzle, 'nozzlePlumeField', None)
        if structure is not None or field is not None:
            plume = section('Plume')
            row(plume, 'Ambient pressure', getattr(nozzle, 'plumeAmbientPressure', None), '{:.0f}', 'Pa')
            if field is not None and field.solved:
                row(plume, 'Lip pressure ratio', field.lipPressureRatio, '{:.3f}')
                row(plume, 'Boundary Mach', field.boundaryMach, '{:.3f}')
                if field.lipRadius:
                    row(plume, 'Marched reach', (field.solvedTo - field.lipX) / field.lipRadius, '{:.2f}', 'lip radii')
                row(plume, 'Mass continuity error', field.massDriftWorst, '{:+.2f}', '%')
                row(plume, 'Within the trusted bound', 'yes' if field.trustworthy else 'no, shorten the reach')
            elif field is not None:
                row(plume, 'March', 'declined')
                row(plume, 'Reason', (field.notes[-1] if field.notes else '--')[:140])
            if structure is not None:
                row(plume, 'Shock cell length (correlated)', getattr(structure, 'shockCellLength', 0.0) * 1e3,
                    '{:.1f}', 'mm')
                if getattr(structure, 'machDiskPresent', False) and getattr(structure, 'lipRadius', 0.0):
                    row(plume, 'Mach disk (correlated)',
                        (structure.machDiskX - structure.lipX) / structure.lipRadius, '{:.1f}', 'lip radii downstream')
                else:
                    row(plume, 'Mach disk (correlated)', 'none')

        thrust = _num(getattr(nozzle, 'thrust', None))
        isp = performance.get('idealISP[s]')
        parts = []
        if thrust:
            parts.append(f'{thrust / 1e3:.0f} kN')
        if _num(isp):
            parts.append(f'Isp {_num(isp):.0f} s')
        fuel = getattr(nozzle, 'Fuel', '')
        ox = getattr(nozzle, 'Oxidizer', '')
        if fuel and ox:
            parts.append(f'{ox}/{fuel}')
        self._summary.configure(text = '   '.join(parts))

    @staticmethod
    def _mm(value):

        return None if value in (None, '') else float(value) * 1e3

    @staticmethod
    def _cm3(value):

        return None if value in (None, '') else float(value) * 1e6

    def _throatRadius(self, nozzle):

        area = _num(getattr(nozzle, 'throatArea', None))
        if area:
            return math.sqrt(area / math.pi) * 1e3
        radii = getattr(nozzle, 'rNozzleWall', [])
        try:
            return float(min(radii)) * 1e3
        except (TypeError, ValueError):
            return None

    def _exitRadius(self, nozzle):

        radii = getattr(nozzle, 'rNozzleWall', [])
        try:
            return float(radii[-1]) * 1e3
        except (TypeError, IndexError):
            return None

    def _length(self, nozzle):

        axis = getattr(nozzle, 'xNozzleWall', [])
        try:
            return (float(axis[-1]) - float(axis[0])) * 1e3
        except (TypeError, IndexError):
            return None
