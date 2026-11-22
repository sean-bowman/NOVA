NOVA: rocket nozzle design
==========================

NOVA designs a rocket nozzle from a set of inputs: its contour by the method of characteristics,
its regenerative cooling, and its plume. This folder holds the NOVA desktop application for
Windows. It needs no Python or other install.

Starting NOVA
-------------
Keep this folder together: NOVA.exe needs the _internal folder beside it. Double-click NOVA.exe.
To start it from the taskbar or Start, right-click NOVA.exe and pin it.

The first time, Windows may show "Windows protected your PC", because this release is not
code-signed. Click "More info", then "Run anyway".

NOVA opens on the example nozzle the project ships. Change the inputs in the Design form on the
left and press Generate; the results appear on the right.

Where NOVA keeps things
-----------------------
Finished runs:     %LOCALAPPDATA%\NOVA\runs
Exports:           Documents\NOVA, unless the Export dialog names another folder
Theme setting:     %APPDATA%\NOVA
Startup log:       %TEMP%\NOVA\novaGui.log (if NOVA does not open, the reason is here)
CEA work files:    %USERPROFILE%\RocketCEA

Fluid properties
----------------
NOVA computes coolant properties with CoolProp, which is included. If REFPROP is installed on this
machine (in %USERPROFILE%\REFPROP or C:\Program Files (x86)\REFPROP), NOVA uses it instead.
REFPROP is licensed separately and is not included.

Reporting a problem
-------------------
The About button, top right, names the version running; the startup log starts with the same line.
Put that line in the report, with the startup log if NOVA did not open:
https://github.com/sean-bowman/NOVA/issues

Source, documentation and validation records: https://github.com/sean-bowman/NOVA
