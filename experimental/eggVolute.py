# -- NOVA (experimental): Egg Cross Section Volute -- #

'''

A volute whose cross section is an egg, pointed end outboard, removed from the package.

The section is two circular arcs joined by a Bezier tip whose control magnitudes are set from
the shoulder tangents, so the profile is smooth where the arcs meet the tip and the sharpness of
the point is a free parameter. `eggPointiness` of 1 draws a regular egg and higher values sharpen
it. The scroll, the wall offset and the sweep are the package's own: only the section and the
solve that sizes it live here.

The shape exists because a duct that has to clear a wall on one side and carry area on the other
wants to be asymmetric, and an egg with its point outboard puts its area where the packaging
allows it.

----------------------------------------------------------------------
                        Status
----------------------------------------------------------------------

This builds and sweeps. It is here because the section solve is unsound in three of its branches
and nothing selects it.

  - **Three convergence loops test the wrong sense.** The branches that are handed an area and
    have to find the egg height run `while abs(area - target) < tolerance`, so they exit on the
    first pass whenever the error is larger than the tolerance, which is always. The height keeps
    its initial guess, `expandedArea/10`, an area used as a length. The branches handed a
    hydraulic diameter test `> tolerance` and do converge. Driving the section by area therefore
    returns a first cross section of the wrong size without saying so.
  - **The search is a fixed-step walk.** Each iteration moves the height by two or three
    micrometres with no bisection, so a converging branch takes thousands of passes to cross a
    centimetre of height.
  - **`crossSectionResolution` is ignored.** The point count follows from the arc and tip
    construction: 24 points requested returns 152.
  - **`scaledBy = 'momentum'` raises.** The momentum branch never assigns `crossSectionalArea`,
    so the first read of it raises `AttributeError`. The linear branch is the only one written.
  - **Neither scroll topology reaches it.** The section is swept over a full turn with a monotone
    taper, which is what the package built before it carried a `ring` and a `cutwater` law, so
    `scrollType` is not read here.
  - **No printability support and no tilt.** `circlePrintability` has no egg path, and
    `printabilityAngle` is not read, so an egg section is drawn upright whatever the
    configuration asks for.
  - **It clashed with the nozzle wall where the circle did.** On `assets/NOVANozzle.json` through
    `solveRegenVolutes`, the inlet egg volute reached 1.02 mm inside the gas-side wall, against
    1.51 mm for the circle. That is the scroll placement rather than the section, and it is
    recorded in `docs/reports/voluteAudit_2026-09-29.md`.

Nothing here is validated. The section is geometry, and the claim made for it is that it closes
and that its area matches what the solve asked for in the branches that converge.

----------------------------------------------------------------------
                        Wiring it back in
----------------------------------------------------------------------

`EggVolute` subclasses the package `Volute`, so the section is runnable from here without
touching the package:

    from eggVolute import EggVolute
    volute = EggVolute(voluteScrollRadius = 0.105, interfaceHydraulicDiameter = 0.008,
                       expandedHydraulicDiameter = 0.0254, eggPointiness = 1.0)
    volute.generateVolute()

A caller reinstating it in the package needs to:

  - fix the three inverted loops before anything reads the result,
  - move `bezier`, `drawEgg` and `generateEggVolute` back into `Volute.py`, restore
    `eggPointiness` on the constructor and the `case 'egg'` arm in `generateVolute`,
  - restore `'egg'` to the `inletVoluteCrossSection` and `outletVoluteCrossSection` choices in
    `novaGui/configSchema.py` and drop the rejection in `config.py`,
  - record a regression case with an egg cross section, since the nine that pin the volutes all
    run circles.

Author: Sean Bowman

'''

import os
import sys

import numpy as np
from scipy.interpolate import interp1d
from math import dist
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from NOVA.Volute import Volute, dynamicEggShell, sweptSectionAreas
from NOVA.exports import py2cad

def bezier(p1: float, p4: float, theta_1: float, theta_2: float, magnitude, res, TwoD=1):

    '''
   
     Creates a bezier curve utilizing p1 and p4 as the end points, theta_1 and theta_2 as end angles, and magnitude to control the magnitude of the curve
    
    '''

    # Scale the magnitude to the size of the bezier to make it less dependent on the input points
    length = np.sqrt(((p4[1]-p1[1])**2) + ((p4[0]-p1[0])**2))
    magnitude[0] = magnitude[0]*length
    magnitude[1] = magnitude[1]*length

    # Create control points p2, p3 from given angles and magnitudes
    py2 = magnitude[0]*np.sin(np.radians(theta_1)) # (magnitude[0]-p1[0] - p1[0])*np.tan(np.radians(theta_1)) + p1[1]
    px2 = np.sqrt((magnitude[0]**2)-(py2**2))
    p2 = [px2+p1[0], py2+p1[1]] # magnitude, angle
    py3 = magnitude[1]*np.sin(np.radians(theta_2)) # (p4[0]-magnitude[1] - p4[0])*np.tan(np.radians(theta_2)) + p4[1]
    px3 = np.sqrt((magnitude[1]**2) - (py3**2))
    p3 = [p4[0]-px3, p4[1]-py3] # magnitude, angle

    # Bezier parametric equation
    def eqn(p1, p2, p3, p4, t):
        return (1 - (t**3))*p1 + (3*t*(1-t)**2)*p2 + 3*(t**2)*(1-t)*p3 + (t**3)*p4

    # parametric bezier
    t = np.linspace(0, 1, res)
    x = [eqn(0, p2[0]-p1[0], p3[0]-p1[0], p4[0]-p1[0], i)+p1[0] for i in t]
    y = [eqn(0, p2[1]-p1[1], p3[1]-p1[1], p4[1]-p1[1], i)+p1[1] for i in t]

    # Plot Bezier curve for debugging
    # plt.plot(x, y, c='k')
    # plt.plot(p2[0], p2[1], '*')
    # plt.plot(p3[0], p3[1], '*')
    # plt.plot(p1[0], p1[1], '*')
    # plt.plot(p4[0], p4[1], '*')
    #plt.show()

    return [x, y]

class EggVolute(Volute):

    '''

    The package volute with an egg cross section available.

    Parameters:
    -----------
    eggPointiness : float
        Sharpness of the outboard point. 1 draws a regular egg, above that sharpens it.
    **kwargs
        Anything `Volute` takes. `crossSectionType` defaults to `egg`.

    '''

    def __init__(self, eggPointiness: float = 1.0, **kwargs):
        kwargs.setdefault('crossSectionType', 'egg')
        super().__init__(**kwargs)
        self.eggPointiness = eggPointiness

    def generateVolute(self):

        '''Build an egg scroll, or defer to the package for any other cross section.'''

        if str(self.crossSectionType).lower() != 'egg':
            return super().generateVolute()

        outputDirectory = self.outputDirectory or os.getcwd()
        os.makedirs(outputDirectory, exist_ok = True)

        self.generateEggVolute()
        self.drawnArea = sweptSectionAreas(self.xVolute, self.yVolute, self.zVolute)
        self.flowArea = self.drawnArea

        if self.export == 'on':
            py2cad(os.path.join(outputDirectory, self.filename + '.stl'),
                   self.xVolute[1:], self.yVolute[1:], self.zVolute[1:])
            if self.wallThickness is not None:
                py2cad(os.path.join(outputDirectory, self.filename + '_eggShell.stl'),
                       self.xShell[1:], self.yShell[1:], self.zShell[1:])

    def generateEggVolute(self):

        '''
        
        Can i offer you an egg in this trying time?

        The area distribution can be bounded either by hydraulic diameter or CSA on
        both the interface and expanded ends.

        The anchor point can be north, south, inside, outside, combinations thereof, or center.
        Specify the anchor point with one or two letters, e.g. 'n' , 'o' , or 'no'.
        Unspecified, the default is center.
        An invalid anchor point will anchor south.

        Default egg pointiness is 1.
        
        '''

        def drawEgg(h,pointiness=1):

            # im stealing this egg -B

            top_circle_scaling_factor = pointiness  # Pointiness of the top of the egg

            # -- Declare properties of egg -- #

            phi = (1/2)*(1 + np.sqrt(5))
            theta_test = np.linspace(0,2*np.pi,100)

            c = h*phi/(1 + np.sqrt(7 - 4*phi))
            r1 = c                                          # Circle 1's radius
            r2 = c*(2 - phi)                                # Circle 2's radius
            r3 = c*(2*phi - 3)/top_circle_scaling_factor    # Circle 3's radius
            a = 2*c*(2 - phi)
            L = c*np.cos(np.radians(108-90))

            circle_1_center_x = r2 + r3*top_circle_scaling_factor
            circle_1_center_y = (0.5*r3/np.tan(np.deg2rad(108-90)))*top_circle_scaling_factor
            circle_x_1_left = r1*np.cos(theta_test) - circle_1_center_x
            circle_y_1_left = r1*np.sin(theta_test) + circle_1_center_y

            circle_x_1_right = r1*np.cos(theta_test) + circle_1_center_x
            circle_y_1_right = r1*np.sin(theta_test) + circle_1_center_y

            circle_2_center_y = circle_1_center_y
            circle_x_2 = r2*np.cos(theta_test)
            circle_y_2 = r2*np.sin(theta_test) + circle_2_center_y
            circle_2 = interp1d(circle_x_2,circle_y_2)
            y = circle_2(0)

            circle_3_center_y = min(circle_y_2) + h - r3/top_circle_scaling_factor
            circle_x_3 = r3*np.cos(theta_test)
            circle_y_3 = r3*np.sin(theta_test) + circle_3_center_y

            # -- Only plot the egg part -- #

            yellow_dashed = dist([circle_1_center_x, circle_1_center_y], [(3*r2)/2, L-circle_1_center_y])
            theta_1_int = (np.pi/2 - np.arccos((r2/2)/yellow_dashed)) + np.radians(5*top_circle_scaling_factor)
            # theta_1_int = np.pi/2 - np.arctan2((circle_3_center_y - circle_2_center_y),(r2 + r3*top_circle_scaling_factor))

            theta_1_right = np.linspace(np.pi,np.pi/2 + theta_1_int)
            theta_1_left = np.linspace(np.pi/2 - theta_1_int,0)
            theta_2 = np.linspace(2*np.pi,np.pi)
            theta_3 = np.linspace(np.pi/2 + theta_1_int, np.pi/2 - theta_1_int)

            egg_arc_1_x = r1*np.cos(theta_1_right) + circle_1_center_x   # This is circle 1 right
            egg_arc_1_y = r1*np.sin(theta_1_right) + circle_1_center_y

            # egg_arc_2_x = r3*np.cos(theta_3)                           # This is circle 3
            # egg_arc_2_y = r3*np.sin(theta_3) + circle_3_center_y

            egg_arc_3_x = r1*np.cos(theta_1_left) - circle_1_center_x    # This is circle 1 left
            egg_arc_3_y = r1*np.sin(theta_1_left) + circle_1_center_y

            # Make egg tip (previously circle 3)
            # Bezier spline controls
                # 0.7 and 0.1 used because at pointiness=1 the egg is egg shaped
            mag_sides = 0.7/top_circle_scaling_factor
            mag_tip = 0.1/top_circle_scaling_factor
            res = int(self.crossSectionResolution/4) ############################################################################### WEE WOO WEE WOO

            # Find angle of egg before spline
            dx = abs(egg_arc_1_x[-2]-egg_arc_1_x[-1])
            dy = abs(egg_arc_1_y[-2]-egg_arc_1_y[-1])
            angle = np.degrees(np.arctan2(dy, dx))

            # Initialize arrays
            egg_arc_2_x = np.zeros(res)
            egg_arc_2_y = np.zeros(res)

            # Make left half of egg tip spline
            p1 = [egg_arc_1_x[-1], egg_arc_1_y[-1]]
            p2 = [0, abs((min(circle_y_2)))+h]
            egg_tip_spline = bezier(p1, p2, angle, 0, [mag_sides, mag_tip], int(res/2))
            egg_arc_2_x[:int(res/2)], egg_arc_2_y[:int(res/2)] = egg_tip_spline[0], egg_tip_spline[1]

            # Make right half of egg tip spline
            p1 = [0, abs((min(circle_y_2)))+h]
            p2 = [egg_arc_3_x[0], egg_arc_3_y[0]]
            egg_tip_spline = bezier(p1, p2, 0, -angle, [mag_tip, mag_sides], int(res/2))
            egg_arc_2_x[int((res/2)):], egg_arc_2_y[int((res/2)):] = egg_tip_spline[0], egg_tip_spline[1]

            egg_arc_4_x = r2*np.cos(theta_2)                             # This is circle 2
            egg_arc_4_y = r2*np.sin(theta_2) + circle_2_center_y

            egg_x = np.concatenate([egg_arc_1_x[:-1],egg_arc_2_x,egg_arc_3_x[1:-1],egg_arc_4_x])
            egg_y = np.concatenate([egg_arc_1_y[:-1],egg_arc_2_y,egg_arc_3_y[1:-1],egg_arc_4_y])

            for i in np.arange(len(egg_x)-2,-1,-1):
                if [egg_x[i],egg_y[i]] == [egg_x[i+1],egg_y[i+1]]:
                    egg_x = np.delete(egg_x,i)
                    egg_y = np.delete(egg_y,i)
            # egg_x, egg_y, _ = arcSpline(egg_x, egg_y, np.zeros((len(egg_x))),newNumPoints=self.crossSectionResolution)

            # plt.figure()
            # plt.plot(circle_x_1_left,circle_y_1_left,'purple')
            # plt.plot(circle_x_1_right,circle_y_1_right,'blue')
            # plt.plot(circle_x_2,circle_y_2,'red')
            # plt.plot(circle_x_3,circle_y_3,'green')

            # plt.plot   ( egg_arc_1_x[:-1], egg_arc_1_y[:-1],          'orange',label='arc 1')
            # plt.plot   ( egg_arc_2_x,      egg_arc_2_y,               'green',label='arc 2')
            # plt.plot   ( egg_arc_3_x,      egg_arc_3_y,               'blue',label='arc 3')
            # plt.scatter([egg_arc_3_x[-1]],[egg_arc_3_y[-1]],200,color='b',marker='*')
            # plt.plot   ( egg_arc_4_x,      egg_arc_4_y,               'red',label='arc 4')
            # plt.scatter([egg_arc_4_x[0]], [egg_arc_4_y[0]],100, color='r',marker='*')

            # plt.legend()
            # plt.gca().set_aspect('equal')
            # plt.show(block=True)

            # plt.figure()
            # plt.style.use('dark_background')
            # plt.plot(egg_x,egg_y,'w')
            # plt.gca().set_aspect('equal')
            # plt.show(block=True)

            return egg_x, egg_y

        eggTolerance = 1e-6
        # make resolution eggable
        self.crossSectionResolution = int(np.ceil(self.crossSectionResolution/8)*8)

        ## Define area distribution
        if self.progressbar == 'on':
            print('Converging egg volute area distribution. This should only take a few seconds.')

        if self.numOrifices is None:
            # if not specified, get interface area from interface hydraulic diameter
            if self.interfaceHydraulicDiameter is not None:

                if self.interfaceArea is not None:
                    raise Exception('Please specify only interface area OR hydraulic diameter')

                # guess and check egg until interface area is determined
                interfaceEggH = self.interfaceHydraulicDiameter
                yInterfaceEgg, zInterfaceEgg = drawEgg(h=interfaceEggH,pointiness=self.eggPointiness)
                interfaceEggCSA  = np.trapz(zInterfaceEgg,yInterfaceEgg)
                interfaceEggPeri = 0
                for i in range(len(yInterfaceEgg)-1):
                    interfaceEggPeri += np.sqrt((yInterfaceEgg[i+1] - yInterfaceEgg[i])**2 + (zInterfaceEgg[i+1] - zInterfaceEgg[i])**2)
                checkInterfaceEggHD = 4*interfaceEggCSA/interfaceEggPeri
                while abs(checkInterfaceEggHD - self.interfaceHydraulicDiameter) > eggTolerance:
                    if checkInterfaceEggHD - self.interfaceHydraulicDiameter > 0:
                        interfaceEggH -= eggTolerance*2
                        yInterfaceEgg, zInterfaceEgg = drawEgg(h=interfaceEggH,pointiness=self.eggPointiness)
                        interfaceEggCSA  = np.trapz(zInterfaceEgg,yInterfaceEgg)
                        interfaceEggPeri = 0
                        for i in range(len(yInterfaceEgg)-1):
                            interfaceEggPeri += np.sqrt((yInterfaceEgg[i+1] - yInterfaceEgg[i])**2 + (zInterfaceEgg[i+1] - zInterfaceEgg[i])**2)
                        checkInterfaceEggHD = 4*interfaceEggCSA/interfaceEggPeri
                    elif checkInterfaceEggHD - self.interfaceHydraulicDiameter < 0:
                        interfaceEggH += eggTolerance*2
                        yInterfaceEgg, zInterfaceEgg = drawEgg(h=interfaceEggH,pointiness=self.eggPointiness)
                        interfaceEggCSA  = np.trapz(zInterfaceEgg,yInterfaceEgg)
                        interfaceEggPeri = 0
                        for i in range(len(yInterfaceEgg)-1):
                            interfaceEggPeri += np.sqrt((yInterfaceEgg[i+1] - yInterfaceEgg[i])**2 + (zInterfaceEgg[i+1] - zInterfaceEgg[i])**2)
                        checkInterfaceEggHD = 4*interfaceEggCSA/interfaceEggPeri
                self.interfaceArea = interfaceEggCSA
            # if not specified, get expanded area from expanded hydraulic diameter
            if self.expandedHydraulicDiameter is not None:

                if self.expandedArea is not None:
                    raise Exception('Please specify only expanded area OR hydraulic diameter')

                # guess and check egg until expanded area is determined
                expandedEggH = self.expandedHydraulicDiameter
                yExpandedEgg, zExpandedEgg = drawEgg(h=expandedEggH,pointiness=self.eggPointiness)
                expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                expandedEggPeri = 0
                for i in range(len(yExpandedEgg)-1):
                    expandedEggPeri += np.sqrt((yExpandedEgg[i+1] - yExpandedEgg[i])**2 + (zExpandedEgg[i+1] - zExpandedEgg[i])**2)
                checkexpandedEggHD = 4*expandedEggCSA/expandedEggPeri
                while abs(checkexpandedEggHD - self.expandedHydraulicDiameter) > eggTolerance:
                    if checkexpandedEggHD - self.expandedHydraulicDiameter > 0:
                        expandedEggH -= eggTolerance*3
                        yExpandedEgg, zExpandedEgg = drawEgg(h=expandedEggH,pointiness=self.eggPointiness)
                        expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                        expandedEggPeri = 0
                        for i in range(len(yExpandedEgg)-1):
                            expandedEggPeri += np.sqrt((yExpandedEgg[i+1] - yExpandedEgg[i])**2 + (zExpandedEgg[i+1] - zExpandedEgg[i])**2)
                        checkexpandedEggHD = 4*expandedEggCSA/expandedEggPeri
                    elif checkexpandedEggHD - self.expandedHydraulicDiameter < 0:
                        expandedEggH += eggTolerance*3
                        yExpandedEgg, zExpandedEgg = drawEgg(h=expandedEggH,pointiness=self.eggPointiness)
                        expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                        expandedEggPeri = 0
                        for i in range(len(yExpandedEgg)-1):
                            expandedEggPeri += np.sqrt((yExpandedEgg[i+1] - yExpandedEgg[i])**2 + (zExpandedEgg[i+1] - zExpandedEgg[i])**2)
                        checkexpandedEggHD = 4*expandedEggCSA/expandedEggPeri
                self.expandedArea = expandedEggCSA
            else: # need to establish expanded hydraulic diameter to make first cross section
                eggHeightGuess = self.expandedArea/10
                yExpandedEgg, zExpandedEgg = drawEgg(h=eggHeightGuess,pointiness=self.eggPointiness)
                expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                while abs(expandedEggCSA - self.expandedArea) < eggTolerance:
                    if expandedEggCSA > self.expandedArea:
                        eggHeightGuess -= eggTolerance*3
                        yExpandedEgg, zExpandedEgg = drawEgg(h=eggHeightGuess,pointiness=self.eggPointiness)
                        expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                    elif expandedEggCSA < self.expandedArea:
                        eggHeightGuess += eggTolerance*3
                        yExpandedEgg, zExpandedEgg = drawEgg(h=eggHeightGuess,pointiness=self.eggPointiness)
                        expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                expandedEggPeri = 0
                for i in range(len(yExpandedEgg)-1):
                    expandedEggPeri += np.sqrt((yExpandedEgg[i+1] - yExpandedEgg[i])**2 + (zExpandedEgg[i+1] - zExpandedEgg[i])**2)
                self.expandedHydraulicDiameter = 4*expandedEggCSA/expandedEggPeri
        else:
            # expanded end specified
            if self.interfaceArea is None and self.interfaceHydraulicDiameter is None:

                # if not specified, get expanded area from expanded hydraulic diameter
                if self.expandedHydraulicDiameter is not None:

                    if self.expandedArea is not None:
                        raise Exception('Please specify only expanded area OR hydraulic diameter')

                    # guess and check egg until expanded area is determined
                    expandedEggH = self.expandedHydraulicDiameter
                    yExpandedEgg, zExpandedEgg = drawEgg(h=expandedEggH,pointiness=self.eggPointiness)
                    expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                    expandedEggPeri = 0
                    for i in range(len(yExpandedEgg)-1):
                        expandedEggPeri += np.sqrt((yExpandedEgg[i+1] - yExpandedEgg[i])**2 + (zExpandedEgg[i+1] - zExpandedEgg[i])**2)
                    checkexpandedEggHD = 4*expandedEggCSA/expandedEggPeri
                    while abs(checkexpandedEggHD - self.expandedHydraulicDiameter) > eggTolerance:
                        if checkexpandedEggHD - self.expandedHydraulicDiameter > 0:
                            expandedEggH -= eggTolerance*3
                            yExpandedEgg, zExpandedEgg = drawEgg(h=expandedEggH,pointiness=self.eggPointiness)
                            expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                            expandedEggPeri = 0
                            for i in range(len(yExpandedEgg)-1):
                                expandedEggPeri += np.sqrt((yExpandedEgg[i+1] - yExpandedEgg[i])**2 + (zExpandedEgg[i+1] - zExpandedEgg[i])**2)
                            checkexpandedEggHD = 4*expandedEggCSA/expandedEggPeri
                        elif checkexpandedEggHD - self.expandedHydraulicDiameter < 0:
                            expandedEggH += eggTolerance*3
                            yExpandedEgg, zExpandedEgg = drawEgg(h=expandedEggH,pointiness=self.eggPointiness)
                            expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                            expandedEggPeri = 0
                            for i in range(len(yExpandedEgg)-1):
                                expandedEggPeri += np.sqrt((yExpandedEgg[i+1] - yExpandedEgg[i])**2 + (zExpandedEgg[i+1] - zExpandedEgg[i])**2)
                            checkexpandedEggHD = 4*expandedEggCSA/expandedEggPeri
                    self.expandedArea = expandedEggCSA
                else: # need to establish expanded hydraulic diameter to make first cross section
                    eggHeightGuess = self.expandedArea/10
                    yExpandedEgg, zExpandedEgg = drawEgg(h=eggHeightGuess,pointiness=self.eggPointiness)
                    expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                    while abs(expandedEggCSA - self.expandedArea) < eggTolerance:
                        if expandedEggCSA > self.expandedArea:
                            eggHeightGuess -= eggTolerance*3
                            yExpandedEgg, zExpandedEgg = drawEgg(h=eggHeightGuess,pointiness=self.eggPointiness)
                            expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                        elif expandedEggCSA < self.expandedArea:
                            eggHeightGuess += eggTolerance*3
                            yExpandedEgg, zExpandedEgg = drawEgg(h=eggHeightGuess,pointiness=self.eggPointiness)
                            expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                    expandedEggPeri = 0
                    for i in range(len(yExpandedEgg)-1):
                        expandedEggPeri += np.sqrt((yExpandedEgg[i+1] - yExpandedEgg[i])**2 + (zExpandedEgg[i+1] - zExpandedEgg[i])**2)
                    self.expandedHydraulicDiameter = 4*expandedEggCSA/expandedEggPeri

                self.interfaceArea = self.expandedArea/self.numOrifices
            # interface end specified
            elif self.expandedArea is None and self.expandedHydraulicDiameter is None:

                # if not specified, get interface area from interface hydraulic diameter
                if self.interfaceHydraulicDiameter is not None:

                    if self.interfaceArea is not None:
                        raise Exception('Please specify only interface area OR hydraulic diameter')

                    # guess and check egg until interface area is determined
                    interfaceEggH = self.interfaceHydraulicDiameter
                    yInterfaceEgg, zInterfaceEgg = drawEgg(h=interfaceEggH,pointiness=self.eggPointiness)
                    interfaceEggCSA  = np.trapz(zInterfaceEgg,yInterfaceEgg)
                    interfaceEggPeri = 0
                    for i in range(len(yInterfaceEgg)-1):
                        interfaceEggPeri += np.sqrt((yInterfaceEgg[i+1] - yInterfaceEgg[i])**2 + (zInterfaceEgg[i+1] - zInterfaceEgg[i])**2)
                    checkInterfaceEggHD = 4*interfaceEggCSA/interfaceEggPeri
                    while abs(checkInterfaceEggHD - self.interfaceHydraulicDiameter) > eggTolerance:
                        if checkInterfaceEggHD - self.interfaceHydraulicDiameter > 0:
                            interfaceEggH -= eggTolerance*3
                            yInterfaceEgg, zInterfaceEgg = drawEgg(h=interfaceEggH,pointiness=self.eggPointiness)
                            interfaceEggCSA  = np.trapz(zInterfaceEgg,yInterfaceEgg)
                            interfaceEggPeri = 0
                            for i in range(len(yInterfaceEgg)-1):
                                interfaceEggPeri += np.sqrt((yInterfaceEgg[i+1] - yInterfaceEgg[i])**2 + (zInterfaceEgg[i+1] - zInterfaceEgg[i])**2)
                            checkInterfaceEggHD = 4*interfaceEggCSA/interfaceEggPeri
                        elif checkInterfaceEggHD - self.interfaceHydraulicDiameter < 0:
                            interfaceEggH += eggTolerance*3
                            yInterfaceEgg, zInterfaceEgg = drawEgg(h=interfaceEggH,pointiness=self.eggPointiness)
                            interfaceEggCSA  = np.trapz(zInterfaceEgg,yInterfaceEgg)
                            interfaceEggPeri = 0
                            for i in range(len(yInterfaceEgg)-1):
                                interfaceEggPeri += np.sqrt((yInterfaceEgg[i+1] - yInterfaceEgg[i])**2 + (zInterfaceEgg[i+1] - zInterfaceEgg[i])**2)
                            checkInterfaceEggHD = 4*interfaceEggCSA/interfaceEggPeri
                    self.interfaceArea = interfaceEggCSA

                self.expandedArea = self.interfaceArea*self.numOrifices

                if self.expandedHydraulicDiameter is None: # need to establish expanded hydraulic diameter to make first cross section
                    eggHeightGuess = self.expandedArea/10
                    yExpandedEgg, zExpandedEgg = drawEgg(h=eggHeightGuess,pointiness=self.eggPointiness)
                    expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                    while abs(expandedEggCSA - self.expandedArea) < eggTolerance:
                        if expandedEggCSA > self.expandedArea:
                            eggHeightGuess -= eggTolerance*3
                            yExpandedEgg, zExpandedEgg = drawEgg(h=eggHeightGuess,pointiness=self.eggPointiness)
                            expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                        elif expandedEggCSA < self.expandedArea:
                            eggHeightGuess += eggTolerance*3
                            yExpandedEgg, zExpandedEgg = drawEgg(h=eggHeightGuess,pointiness=self.eggPointiness)
                            expandedEggCSA  = np.trapz(zExpandedEgg,yExpandedEgg)
                    expandedEggPeri = 0
                    for i in range(len(yExpandedEgg)-1):
                        expandedEggPeri += np.sqrt((yExpandedEgg[i+1] - yExpandedEgg[i])**2 + (zExpandedEgg[i+1] - zExpandedEgg[i])**2)
                    self.expandedHydraulicDiameter = 4*expandedEggCSA/expandedEggPeri

        localCrossSectionResolution = len(yExpandedEgg)

        # distribute
        if self.scaledBy.lower() == 'linear':
            self.crossSectionalArea = np.linspace(self.interfaceArea,self.expandedArea,self.numCrossSections)
        elif self.scaledBy.lower() == 'momentum':
            debug = 1 # not implemented

        ## generate inner wall CSs with seat at (0,0):
        if self.progressbar == 'on':
            print('Generating cross sections.')
        # preallocate
        xCS, yCS, zCS = [np.zeros((self.numCrossSections,localCrossSectionResolution)) for _ in range(3)] # 196 is the resolution of egg idk
        eggHeight = self.expandedHydraulicDiameter
        eggHeights, eggWidths, zEggCenters = [np.zeros((self.numCrossSections)) for _ in range(3)]
        hydraulicDiameter = np.zeros((self.numCrossSections))
        # loop
        for i in tqdm(range(self.numCrossSections-1,-1,-1)):
            targetArea = self.crossSectionalArea[i]
            yCSi, zCSi = drawEgg(h=eggHeight,pointiness=self.eggPointiness)
            checkArea = np.trapz(zCSi,yCSi)
            while abs(checkArea - targetArea) > eggTolerance:
                if checkArea > targetArea:
                    eggHeight -= eggTolerance*2
                    yCSi, zCSi = drawEgg(h=eggHeight,pointiness=self.eggPointiness)
                    checkArea = np.trapz(zCSi,yCSi)
                else:
                    eggHeight += eggTolerance*2
                    yCSi, zCSi = drawEgg(h=eggHeight,pointiness=self.eggPointiness)
                    checkArea = np.trapz(zCSi,yCSi)
            zCSi -= min(zCSi) # make sure it sits on its ass
            yCS[i,:] = yCSi
            zCS[i,:] = zCSi
            eggPeri = 0
            for j in range(len(yExpandedEgg)-1):
                eggPeri += np.sqrt((yCSi[j+1] - yCSi[j])**2 + (zCSi[j+1] - zCSi[j])**2)
            hydraulicDiameter[i] = 4*targetArea/eggPeri

            # move to anchor point
            eggHeights[i]  = max(zCSi)
            eggWidths[i]   = max(yCSi)
            zEggCenters[i] = zCSi[np.where(yCSi == max(yCSi))][0]
            dy = 0
            dz = 0
            match self.anchorBy.lower():
                case 'c':
                    dz -= zEggCenters[i]
                case 'n':
                    dz -= eggHeights[i]
                case 's':
                    dz -= 0
                case 'o':
                    dy -= eggWidths[i]
                    dz -= zEggCenters[i]
                case 'i':
                    dy += eggWidths[i]
                    dz -= zEggCenters[i]
                case 'no':
                    dy -= eggWidths[i]
                    dz -= eggHeights[i]
                case 'so':
                    dy -= eggWidths[i]
                    dz -= 0
                case 'ni':
                    dy += eggWidths[i]
                    dz -= eggHeights[i]
                case 'si':
                    dy += eggWidths[i]
                    dz -= 0
            yCS[i,:] += dy
            zCS[i,:] += dz

        self.hydraulicDiameter = hydraulicDiameter

        # generate shell
        if self.wallThickness is not None or self.wallHoopStress is not None:

            if self.progressbar == 'on':
                print('Generating shell.')

            yShellCS, zShellCS, _, _, wallThickness= dynamicEggShell(yCS,zCS,
                                                                    self.wallThickness,
                                                                    self.wallHoopStress, self.pressureDifferential, self.hydraulicDiameter)
            self.wallThickness = wallThickness
            xShellCS = np.zeros_like(xCS)
            # catch inverted wall
            if abs(np.trapz(yShellCS[0,:],zShellCS[0,:])) < abs(np.trapz(yCS[0,:],zCS[0,:])):
                self.wallThickness *= -1
                yShellCS, zShellCS, _, _, wallThickness= dynamicEggShell(yCS,zCS,
                                                        self.wallThickness)
            self.wallThickness = abs(wallThickness)

        # move cross sections to correct radius
        if self.progressbar == 'on':
            print('Locating radially.')
        if self.alignWallBy == 'inner':
            yCS += self.voluteScrollRadius
            if self.wallThickness is not None:
                yShellCS += self.voluteScrollRadius
        elif self.alignWallBy == 'outer':

            if self.wallThickness is None:
                print('No outer wall to align by.')
                yCS += self.voluteScrollRadius
                if self.wallThickness is not None:
                    yShellCS += self.voluteScrollRadius
            elif self.wallThickness is not None:
                y1p = np.zeros((self.numCrossSections))
                z1p = np.zeros((self.numCrossSections))
                match self.anchorBy.lower():
                    case 'n':
                        z1p += self.wallThickness
                    case 's':
                        z1p -= self.wallThickness
                    case 'o':
                        y1p += self.wallThickness
                    case 'i':
                        y1p -= self.wallThickness
                    case 'no':
                        y1p += self.wallThickness
                        z1p += self.wallThickness
                    case 'so':
                        y1p += self.wallThickness
                        z1p -= self.wallThickness
                    case 'ni':
                        y1p -= self.wallThickness
                        z1p += self.wallThickness
                    case 'si':
                        y1p -= self.wallThickness
                        z1p -= self.wallThickness

                for i in range(self.numCrossSections):
                    yCS[i,:] += self.voluteScrollRadius - y1p[i]
                    zCS[i,:] += -z1p[i]
                    yShellCS[i,:] += self.voluteScrollRadius - y1p[i]
                    zShellCS[i,:] += -z1p[i]
        else:
            raise Exception('Invalid wall alignment argument. Please specify inner or outer.')

        # roll cross sections about scroll axis to create mesh
        if self.progressbar == 'on':
            print('Generating 3D geometry.')
        if self.scrollDirection.lower() == 'cw':
            rollAngle = np.linspace(0, 2*np.pi, self.numCrossSections)
        elif self.scrollDirection.lower() == 'ccw':
            rollAngle = np.linspace(2*np.pi, 0, self.numCrossSections)
        else:
            raise Exception('Invalid scroll direction argument. Please specify cw or ccw.')
        xVolute, yVolute, zVolute = [np.zeros((self.numCrossSections,localCrossSectionResolution)) for _ in range(3)]
        for i in range(self.numCrossSections):

            V = [xCS[i,:], yCS[i,:], zCS[i,:]]
            E = [0,        0,        rollAngle[i]]

            # Direction Cosines (rotation matrix) construction:

            Rx = np.array([                                     \
                [1,             0,              0           ],  \
                [0,             np.cos(E[0]),  -np.sin(E[0])],  \
                [0,             np.sin(E[0]),   np.cos(E[0])]]) # X-Axis rotation

            Ry = np.array([                                     \
                [np.cos(E[1]),  0,              np.sin(E[1])],  \
                [0,             1,              0           ],  \
                [-np.sin(E[1]), 0,              np.cos(E[1])]]) # Y-axis rotation

            Rz = np.array([                                     \
                [np.cos(E[2]), -np.sin(E[2]),   0           ],  \
                [np.sin(E[2]),  np.cos(E[2]),   0           ],  \
                [0,             0,              1           ]]) # Z-axis rotation

            R = Rx@Ry@Rz                                        # Rotation matrix

            # Un-centered rotated matrix:
            xVolute[i,:] = (R@V).T[:,0]                  # Extract X from V
            yVolute[i,:] = (R@V).T[:,1]                  # Extract Y from V
            zVolute[i,:] = (R@V).T[:,2]                  # Extract Z from V

        # roll outer wall cross sections about scroll axis to create mesh
        if self.wallThickness is not None:
            xShell, yShell, zShell = [np.zeros((self.numCrossSections,localCrossSectionResolution)) for _ in range(3)]
            for i in range(self.numCrossSections):

                V = [xShellCS[i,:], yShellCS[i,:], zShellCS[i,:]]
                E = [0,             0,             rollAngle[i]]

                # Direction Cosines (rotation matrix) construction:

                Rx = np.array([                                     \
                    [1,             0,              0           ],  \
                    [0,             np.cos(E[0]),  -np.sin(E[0])],  \
                    [0,             np.sin(E[0]),   np.cos(E[0])]]) # X-Axis rotation

                Ry = np.array([                                     \
                    [np.cos(E[1]),  0,              np.sin(E[1])],  \
                    [0,             1,              0           ],  \
                    [-np.sin(E[1]), 0,              np.cos(E[1])]]) # Y-axis rotation

                Rz = np.array([                                     \
                    [np.cos(E[2]), -np.sin(E[2]),   0           ],  \
                    [np.sin(E[2]),  np.cos(E[2]),   0           ],  \
                    [0,             0,              1           ]]) # Z-axis rotation

                R = Rx@Ry@Rz                                        # Rotation matrix

                # Un-centered rotated matrix:
                xShell[i,:] = (R@V).T[:,0]                  # Extract X from V
                yShell[i,:] = (R@V).T[:,1]                  # Extract Y from V
                zShell[i,:] = (R@V).T[:,2]                  # Extract Z from V

        # axial location
        if self.progressbar == 'on':
            print('Locating axially.')
        zVolute += self.axialOffset
        if self.wallThickness is not None:
            zShell += self.axialOffset

        # assign
        if self.progressbar == 'on':
            print('Finishing volute.')
        self.xVolute = xVolute
        self.yVolute = yVolute
        self.zVolute = zVolute
        if self.wallThickness is not None:
            self.xShell = xShell
            self.yShell = yShell
            self.zShell = zShell
