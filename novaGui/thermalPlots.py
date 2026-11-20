
# -- NOVA GUI Thermal Views -- #

'''

The cooling views: the regenerative jacket, the film and the radiative extension.

Each draws from what the run kept on the Nozzle, never from a saved figure, so it follows the
active palette mode (themeColors). A drawer draws into a pane, as novaGui.plotting describes:

    drawWallMap            the jacket on the nozzle wall: hot wall and coolant temperature along it
    drawJacketTemperatures hot wall against its limit and the gas driving it, and the coolant warming
    drawCoolantFlow        coolant pressure, velocity and Mach number along the channel
    drawCoolantProperties  coolant density, viscosity and specific heat along the channel
    drawHeatFlux           heat flux with its radiative share, both film coefficients, Reynolds and
                           Nusselt numbers
    drawFilm               the film along the wall, its effectiveness and the temperatures it sets
    drawExtension          the extension's wall temperature against its limit, and its heat balance
    drawCircuit            the coolant's paths on the half section
    drawPasses             each pass's coolant and hot wall
    drawCircuitIterations  the hot wall and coolant at every pass of a multi-pass circuit's outer
                           iteration, earlier passes fading

The jacket views read `Nozzle.channelThermalResults`, the station arrays of the jacket solve, in
station order from the injector face aft. The film views read the regen section's film arrays and
the extension view the radiative extension's solution.

The film model is written along the wall: it gives an effectiveness and a driving temperature at
each station and nothing across the film. The film map therefore draws the film as a band of fixed
thickness, colored by the temperature the film holds the wall to, against the core gas colored by
the recovery temperature it would otherwise see, and says on the figure that the thickness is not
to scale.

Author: Sean Bowman

'''

import numpy as np

from . import themeColors
from .plotting import _palette

#--------------------------------------------------------------------------------------------------------------------------#
# -- Shared -- #
#--------------------------------------------------------------------------------------------------------------------------#

def _array(nozzle, name: str) -> np.ndarray:

    '''A Nozzle attribute as a float array, empty when it is missing or not numeric.'''

    value = getattr(nozzle, name, None)
    try:
        return np.asarray(value, dtype = float) if value is not None else np.array([])
    except (TypeError, ValueError):
        return np.array([])

def thermalResults(nozzle) -> dict:

    '''The jacket solve's station arrays, or None when no jacket was solved.'''

    results = getattr(nozzle, 'channelThermalResults', None)
    if not isinstance(results, dict) or np.size(results.get('xHotWall3D', [])) < 2:
        return None

    return results

def _metalWall(results: dict) -> np.ndarray:

    '''

    The wall the temperature limit applies to: the metal, which under a barrier coating is the
    face behind the coating rather than the gas-side surface. Without a coating the two are the
    same array.

    '''

    return np.asarray(results.get('metalWallTemperature', results['wallTemperature']), dtype = float)

def filmSolved(nozzle) -> bool:

    effectiveness = _array(nozzle, 'regenSectionFilmEffectiveness')

    return effectiveness.size >= 2 and effectiveness.size == _array(nozzle, 'xRegenNozzle').size

def extensionSolved(nozzle) -> bool:

    return getattr(nozzle, 'radiativeExtensionSolution', None) is not None \
        and _array(nozzle, 'extensionWallTemperature').size >= 2

def _panels(pane, rows: int, cols: int = 1, heightRatios = None, sharex: bool = True) -> list:

    '''

    A grid of themed axes filling the pane, row by row. With `sharex`, every axes in a column shares
    the axial axis and only the bottom row is labelled.

    '''

    figure = pane.figure
    figure.clear()
    figure.set_layout_engine('constrained')
    pane._projection = None
    grid = figure.add_gridspec(rows, cols, height_ratios = heightRatios)
    axes = []
    for row in range(rows):
        for col in range(cols):
            share = axes[col] if sharex and row > 0 else None
            ax = figure.add_subplot(grid[row, col], sharex = share)
            themeColors.styleAxes(ax)
            if sharex and row < rows - 1:
                ax.tick_params(labelbottom = False)
            axes.append(ax)
    pane.axes = axes[-1]

    return axes

def _throat(nozzle, axes) -> None:

    '''Mark the throat on each axial axes, where the jacket's hardest station is.'''

    wallX, wallR = _array(nozzle, 'xNozzleWall'), _array(nozzle, 'rNozzleWall')
    if wallX.size < 2 or wallR.size != wallX.size:
        return
    throatX = float(wallX[int(np.argmin(wallR))])
    for ax in axes:
        ax.axvline(throatX, color = themeColors.textDim, linewidth = 0.8, linestyle = ':', zorder = 0)

def _legend(ax, **options) -> None:

    ax.legend(facecolor = themeColors.surface2, edgecolor = themeColors.border, labelcolor = themeColors.text, fontsize = 8,
              framealpha = 0.95, **options)

def _twin(ax, color: str):

    '''A second y axis on the right, in a series color.'''

    twin = ax.twinx()
    twin.tick_params(colors = color)
    twin.grid(False)
    for spine in twin.spines.values():
        spine.set_color(themeColors.border)

    return twin

def _colorbar(pane, mappable, axes, label: str, orientation: str = 'horizontal'):

    bar = pane.figure.colorbar(mappable, ax = axes, orientation = orientation, fraction = 0.05, pad = 0.08)
    bar.set_label(label, color = themeColors.text)
    bar.outline.set_edgecolor(themeColors.border)
    bar.ax.tick_params(colors = themeColors.textMuted)

    return bar

def _band(ax, x, r, values, cmap, norm, width: float, zorder: int = 3):

    '''A line along (x, r) colored station by station, drawn `width` points wide.'''

    from matplotlib.collections import LineCollection

    points = np.column_stack([x, r]).reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis = 1)
    middle = 0.5 * (np.asarray(values[:-1]) + np.asarray(values[1:]))
    # Round caps overlap each segment onto the next, so no seam shows between stations
    collection = LineCollection(segments, cmap = cmap, norm = norm, linewidths = width, capstyle = 'round',
                                joinstyle = 'round', zorder = zorder)
    collection.set_array(middle)
    ax.add_collection(collection)

    return collection

def _flowDirection(ax, x, pressure, color: str) -> None:

    '''Name the coolant's inlet and outlet ends, which the pressure falling along the flow gives away.'''

    inlet = int(np.argmax(pressure))
    outlet = int(np.argmin(pressure))
    if inlet == outlet:
        return
    for index, word in ((inlet, 'coolant in'), (outlet, 'out')):
        ax.annotate(word, xy = (x[index], 1.0), xycoords = ('data', 'axes fraction'), xytext = (0, -12),
                    textcoords = 'offset points', ha = 'left' if index < len(x) // 2 else 'right', va = 'top',
                    color = color, fontsize = 8)

#--------------------------------------------------------------------------------------------------------------------------#
# -- The jacket -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawWallMap(pane, nozzle) -> None:

    '''

    The jacket on the nozzle wall: the hot wall colored by its temperature, and outside it the
    coolant channel colored by the coolant's, from the injector face to the end of the jacket, with
    the wall temperature limit marked on its scale.

    '''

    from matplotlib.colors import Normalize

    results = thermalResults(nozzle)
    if results is None:
        pane.message('No cooling jacket was built for this run.')
        return

    x, r = np.asarray(results['xHotWall3D']), np.asarray(results['rHotWall3D'])
    wall, coolant = _metalWall(results), np.asarray(results['temperature'])
    limit = getattr(nozzle, 'maxWallTemperature', None)
    # The channel sits millimetres outside the wall, closer than two bands wide enough to read can
    # be drawn, so its band is set out by a fixed fraction of the chamber radius and labelled as such
    offset = 0.12 * float(np.max(r))

    # The map takes the full width; its two scales sit side by side beneath it
    figure = pane.figure
    figure.clear()
    figure.set_layout_engine('constrained')
    pane._projection = None
    grid = figure.add_gridspec(2, 2, height_ratios = (1.0, 0.045))
    ax = figure.add_subplot(grid[0, :])
    wallScale, coolantScale = figure.add_subplot(grid[1, 0]), figure.add_subplot(grid[1, 1])
    themeColors.styleAxes(ax)
    pane.axes = ax
    ax.grid(False)

    # The whole contour for context, the jacketed part of it banded
    wallX, wallR = _array(nozzle, 'xNozzleWall'), _array(nozzle, 'rNozzleWall')
    if wallX.size == wallR.size and wallX.size:
        ax.plot(wallX, wallR, color = themeColors.textDim, linewidth = 1.0)
        ax.fill_between(wallX, 0.0, wallR, color = themeColors.surface2, alpha = 0.35, linewidth = 0)

    top = max(float(np.max(wall)), float(limit) if limit else 0.0)
    wallNorm = Normalize(vmin = float(np.min(wall)), vmax = top)
    coolantNorm = Normalize(vmin = float(np.min(coolant)), vmax = float(np.max(coolant)))
    wallBand = _band(ax, x, r, wall, _palette().colormap('temperature', themeColors.mode), wallNorm, 7.0, zorder = 4)
    coolantBand = _band(ax, x, r + offset, coolant, _palette().colormap('mach', themeColors.mode), coolantNorm, 5.0)

    ax.text(float(np.mean(x)), 0.45 * float(np.min(r)), 'exhaust', color = themeColors.textMuted, fontsize = 9,
            ha = 'center', style = 'italic')
    _flowDirection(ax, x, np.asarray(results['pressure']), themeColors.textMuted)
    ax.text(0.995, 0.03, 'coolant band drawn outside the wall, not to scale', transform = ax.transAxes, ha = 'right',
            va = 'bottom', color = themeColors.textMuted, fontsize = 7, style = 'italic')

    span = float(np.max(x) - np.min(x))
    ax.set_xlim(float(np.min(x)) - 0.04 * span, float(np.max(x)) + 0.04 * span)
    ax.set_ylim(0.0, 1.3 * float(np.max(r + offset)))
    ax.set_aspect('equal', adjustable = 'box')
    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')
    total = float(np.sum(results['heatTransfer'])) * float(getattr(nozzle, 'nChannel', 1) or 1)
    ax.set_title(f'The jacket on the wall: {int(getattr(nozzle, "nChannel", 0) or 0)} channels, '
                 f'{total / 1e6:.2f} MW into the coolant', color = themeColors.text)

    for scale, mappable, label in ((wallScale, wallBand, 'Hot wall temperature [K]'),
                                   (coolantScale, coolantBand, 'Coolant temperature [K]')):
        bar = figure.colorbar(mappable, cax = scale, orientation = 'horizontal')
        bar.set_label(label, color = themeColors.text)
        bar.outline.set_edgecolor(themeColors.border)
        bar.ax.tick_params(colors = themeColors.textMuted)
        if scale is wallScale and limit:
            bar.ax.axvline(float(limit), color = themeColors.red, linewidth = 2.0)
    pane.redraw()

def drawJacketTemperatures(pane, nozzle) -> None:

    '''

    The hot wall against its limit, with the gas temperature driving it on its own scale, and the
    coolant warming along the channel.

    '''

    results = thermalResults(nozzle)
    if results is None:
        pane.message('No cooling jacket was built for this run.')
        return

    x = np.asarray(results['xHotWall3D'])
    wallAxes, coolantAxes = _panels(pane, 2, heightRatios = (1.4, 1.0))

    metal, surface = _metalWall(results), np.asarray(results['wallTemperature'], dtype = float)
    wallAxes.plot(x, metal, color = themeColors.accent, linewidth = 1.8, label = 'Hot wall')
    if not np.array_equal(metal, surface):
        wallAxes.plot(x, surface, color = themeColors.accent, linewidth = 1.2, linestyle = ':', label = 'Coating surface')
    limit = getattr(nozzle, 'maxWallTemperature', None)
    if limit:
        wallAxes.axhline(float(limit), color = themeColors.red, linewidth = 1.0, linestyle = '--',
                         label = f'Wall limit {float(limit):.0f} K')
    gasAxes = _twin(wallAxes, themeColors.blue)
    gasAxes.plot(x, results['drivingTemperature'], color = themeColors.blue, linewidth = 1.2, label = 'Gas driving the wall')
    gasAxes.set_ylabel('Gas driving temperature [K]', color = themeColors.blue)
    wallAxes.set_ylabel('Hot wall temperature [K]')
    wallAxes.set_title('Wall and coolant temperatures', color = themeColors.text)
    handles, labels = wallAxes.get_legend_handles_labels()
    gasHandles, gasLabels = gasAxes.get_legend_handles_labels()
    gasAxes.legend(handles + gasHandles, labels + gasLabels, facecolor = themeColors.surface2, edgecolor = themeColors.border,
                   labelcolor = themeColors.text, fontsize = 8, loc = 'lower center', framealpha = 0.95)

    coolant = np.asarray(results['temperature'])
    coolantAxes.plot(x, coolant, color = themeColors.cyan, linewidth = 1.8)
    coolantAxes.fill_between(x, float(np.min(coolant)), coolant, color = themeColors.cyan, alpha = 0.15, linewidth = 0)
    coolantAxes.set_ylabel('Coolant temperature [K]')
    coolantAxes.set_xlabel('Nozzle axis [m]')
    _flowDirection(coolantAxes, x, np.asarray(results['pressure']), themeColors.textMuted)
    rise = float(np.max(coolant) - np.min(coolant))
    coolantAxes.set_title(f'Coolant warms {rise:.0f} K, from {float(np.min(coolant)):.0f} to '
                          f'{float(np.max(coolant)):.0f} K', color = themeColors.textMuted, fontsize = 9)
    _throat(nozzle, (wallAxes, coolantAxes))
    pane.redraw()

def drawCoolantFlow(pane, nozzle) -> None:

    '''Coolant pressure, velocity and Mach number along the channel.'''

    results = thermalResults(nozzle)
    if results is None:
        pane.message('No cooling jacket was built for this run.')
        return

    x = np.asarray(results['xHotWall3D'])
    pressure = np.asarray(results['pressure'])
    axes = _panels(pane, 3)
    series = ((pressure / 1e6, 'Pressure [MPa]', themeColors.accent), (results['velocity'], 'Velocity [m/s]', themeColors.blue),
              (results['machNumber'], 'Mach number [-]', themeColors.cyan))
    for ax, (values, label, color) in zip(axes, series):
        ax.plot(x, values, color = color, linewidth = 1.7)
        ax.set_ylabel(label)
    drop = float(np.max(pressure) - np.min(pressure))
    axes[0].set_title(f'Coolant flow: {drop / 1e3:.0f} kPa pressure drop, exit at {float(np.min(pressure)) / 1e6:.2f} MPa',
                      color = themeColors.text)
    _flowDirection(axes[0], x, pressure, themeColors.textMuted)
    axes[-1].set_xlabel('Nozzle axis [m]')
    _throat(nozzle, axes)
    pane.redraw()

def drawCoolantProperties(pane, nozzle) -> None:

    '''The coolant's density, viscosity and specific heat along the channel, from its equation of state.'''

    results = thermalResults(nozzle)
    if results is None:
        pane.message('No cooling jacket was built for this run.')
        return

    x = np.asarray(results['xHotWall3D'])
    axes = _panels(pane, 3)
    series = ((results['density'], 'Density [kg/m³]', themeColors.accent),
              (np.asarray(results['viscosity']) * 1e6, 'Viscosity [µPa·s]', themeColors.purple),
              (np.asarray(results['specificHeat']) * 1e-3, 'Specific heat [kJ/kg·K]', themeColors.green))
    for ax, (values, label, color) in zip(axes, series):
        ax.plot(x, values, color = color, linewidth = 1.7)
        ax.set_ylabel(label)
    coolant = getattr(nozzle, 'coolant', None) or 'coolant'
    axes[0].set_title(f'Thermophysical properties of the {coolant} along the channel', color = themeColors.text)
    _flowDirection(axes[0], x, np.asarray(results['pressure']), themeColors.textMuted)
    axes[-1].set_xlabel('Nozzle axis [m]')
    _throat(nozzle, axes)
    pane.redraw()

def drawHeatFlux(pane, nozzle) -> None:

    '''

    The heat flux through the hot wall with its radiative share, the gas-side and coolant-side film
    coefficients, and the coolant's Reynolds and Nusselt numbers.

    '''

    results = thermalResults(nozzle)
    if results is None:
        pane.message('No cooling jacket was built for this run.')
        return

    x = np.asarray(results['xHotWall3D'])
    fluxAxes, coefficientAxes, groupAxes = _panels(pane, 3)

    flux = np.asarray(results['heatFlux']) / 1e6
    fluxAxes.fill_between(x, 0.0, flux, color = themeColors.accent, alpha = 0.25, linewidth = 0)
    fluxAxes.plot(x, flux, color = themeColors.accent, linewidth = 1.7, label = 'Total')
    heat = np.asarray(results['heatTransfer'])
    radiative = np.asarray(results.get('radiativeHeatTransfer', np.zeros_like(heat)))
    if np.any(radiative):
        share = np.divide(radiative, heat, out = np.zeros_like(heat), where = heat != 0.0)
        fluxAxes.plot(x, flux * share, color = themeColors.purple, linewidth = 1.2, label = 'Radiative share')
        _legend(fluxAxes, loc = 'upper left')
    fluxAxes.set_ylabel('Heat flux [MW/m²]')
    fluxAxes.set_title(f'Heat flux peaks at {float(np.max(flux)):.1f} MW/m²', color = themeColors.text)

    coefficientAxes.plot(x, np.asarray(results['exhaustConvectiveHeatTransferCoef']) / 1e3, color = themeColors.red,
                         linewidth = 1.6, label = 'Gas side')
    coefficientAxes.plot(x, np.asarray(results['coolantConvectiveHeatTransferCoef']) / 1e3, color = themeColors.cyan,
                         linewidth = 1.6, label = 'Coolant side')
    coefficientAxes.set_ylabel('Film coefficient [kW/m²·K]')
    _legend(coefficientAxes, loc = 'upper left')

    groupAxes.plot(x, np.asarray(results['reynoldsNumber']) / 1e6, color = themeColors.blue, linewidth = 1.6)
    groupAxes.set_ylabel('Reynolds number [10⁶]', color = themeColors.blue)
    nusseltAxes = _twin(groupAxes, themeColors.green)
    nusseltAxes.plot(x, results['nusseltNumber'], color = themeColors.green, linewidth = 1.4)
    nusseltAxes.set_ylabel('Nusselt number [-]', color = themeColors.green)
    groupAxes.set_xlabel('Nozzle axis [m]')
    _throat(nozzle, (fluxAxes, coefficientAxes, groupAxes))
    pane.redraw()

#--------------------------------------------------------------------------------------------------------------------------#
# -- The film -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawFilm(pane, nozzle) -> None:

    '''

    The film along the wall: a map of the film against the core gas, the effectiveness falling away
    from the slot, and the temperature the film holds the wall to against what the gas would drive it
    to without one. The entrainment model's own arrays are added when it ran.

    '''

    from matplotlib.colors import Normalize

    if not filmSolved(nozzle):
        pane.message('No film was solved for this run.')
        return

    x, r = _array(nozzle, 'xRegenNozzle'), _array(nozzle, 'rRegenNozzle')
    effectiveness = _array(nozzle, 'regenSectionFilmEffectiveness')
    driving = _array(nozzle, 'regenSectionFilmDrivingTemperature')
    recovery = _array(nozzle, 'regenSectionNearWallRecoveryTemperature')
    entrained = _array(nozzle, 'regenSectionFilmEntrainmentFlowRatio')
    mixture = _array(nozzle, 'regenSectionFilmWallMixtureRatio')
    hasEntrainment = entrained.size == x.size and mixture.size == x.size
    slot = int(np.argmax(effectiveness > 0.0))
    survival = float(getattr(nozzle, 'filmSurvivalLength', 0.0) or 0.0)

    figure = pane.figure
    figure.clear()
    figure.set_layout_engine('constrained')
    pane._projection = None
    columns = 3 if hasEntrainment else 2
    grid = figure.add_gridspec(2, columns, height_ratios = (1.25, 1.0))
    mapAxes = figure.add_subplot(grid[0, :])
    lower = [figure.add_subplot(grid[1, 0])]
    lower += [figure.add_subplot(grid[1, index], sharex = lower[0]) for index in range(1, columns)]
    for ax in [mapAxes] + lower:
        themeColors.styleAxes(ax)
    pane.axes = lower[-1]

    # -- The map: the core at its recovery temperature, the film as a band on the wall -- #
    cmap = _palette().colormap('temperature', themeColors.mode)
    norm = Normalize(vmin = float(np.min(driving)), vmax = float(np.max(recovery)))
    thickness = 0.07 * float(np.max(r))
    span = np.linspace(0.0, 1.0, 24)
    coreR = np.outer(r - thickness, span)
    coreX = np.repeat(x[:, None], span.size, axis = 1)
    mapAxes.pcolormesh(coreX, coreR, np.repeat(recovery[:, None], span.size, axis = 1), cmap = cmap, norm = norm,
                       shading = 'gouraud')
    bandR = (r - thickness)[:, None] + np.outer(np.ones_like(r), span) * thickness
    film = mapAxes.pcolormesh(np.repeat(x[:, None], span.size, axis = 1), bandR,
                              np.repeat(driving[:, None], span.size, axis = 1), cmap = cmap, norm = norm,
                              shading = 'gouraud')
    mapAxes.plot(x, r, color = themeColors.accent, linewidth = 2.0)
    mapAxes.annotate('slot', xy = (x[slot], r[slot]), xytext = (x[slot], 1.18 * float(np.max(r))),
                     color = themeColors.text, fontsize = 8, ha = 'center',
                     arrowprops = dict(arrowstyle = '->', color = themeColors.textMuted, linewidth = 0.8))
    if survival > 0.0:
        end = float(x[slot]) + survival
        mapAxes.axvline(end, color = themeColors.textMuted, linewidth = 0.8, linestyle = '--')
        mapAxes.text(end, 1.08 * float(np.max(r)), ' effectiveness 0.3', color = themeColors.textMuted, fontsize = 8)
    mapAxes.text(0.995, 0.03, 'film band drawn at a fixed thickness: the film model resolves the film along '
                 'the wall, not across it', transform = mapAxes.transAxes, ha = 'right', va = 'bottom',
                 color = themeColors.textMuted, fontsize = 7, style = 'italic')
    mapAxes.set_xlim(float(np.min(x)), float(np.max(x)))
    mapAxes.set_ylim(0.0, 1.3 * float(np.max(r)))
    mapAxes.set_aspect('equal', adjustable = 'box')
    mapAxes.grid(False)
    mapAxes.set_ylabel('Radius [m]')
    model = {'hatchPapell': 'Hatch and Papell', 'sp8124Entrainment': 'SP-8124 entrainment'}.get(
        getattr(nozzle, 'filmCoolingModel', ''), str(getattr(nozzle, 'filmCoolingModel', '')))
    coolant = getattr(nozzle, 'filmCoolant', None) or 'coolant'
    flow = float(getattr(nozzle, 'filmMassFlow', 0.0) or 0.0)
    mapAxes.set_title(f'{coolant} film, {flow:.3f} kg/s through a {1e3 * float(nozzle.filmSlotHeight or 0.0):.1f} mm '
                      f'slot ({model}): useful for {1e3 * survival:.0f} mm', color = themeColors.text)
    _colorbar(pane, film, mapAxes, 'Gas temperature at the wall [K]', 'vertical')

    # -- Effectiveness -- #
    effectivenessAxes = lower[0]
    effectivenessAxes.fill_between(x, 0.0, effectiveness, color = themeColors.cyan, alpha = 0.25, linewidth = 0)
    effectivenessAxes.plot(x, effectiveness, color = themeColors.cyan, linewidth = 1.7)
    effectivenessAxes.axhline(0.3, color = themeColors.textMuted, linewidth = 0.8, linestyle = '--')
    effectivenessAxes.set_ylim(0.0, 1.05)
    effectivenessAxes.set_ylabel('Film effectiveness [-]')
    effectivenessAxes.set_xlabel('Nozzle axis [m]')

    # -- What the wall is driven by, with and without the film -- #
    temperatureAxes = lower[1]
    temperatureAxes.plot(x, recovery, color = themeColors.red, linewidth = 1.4, label = 'Without the film')
    temperatureAxes.plot(x, driving, color = themeColors.cyan, linewidth = 1.7, label = 'Under the film')
    results = thermalResults(nozzle)
    if results is not None:
        temperatureAxes.plot(results['xHotWall3D'], results['wallTemperature'], color = themeColors.accent, linewidth = 1.4,
                             label = 'Hot wall')
    temperatureAxes.set_ylabel('Temperature [K]')
    temperatureAxes.set_xlabel('Nozzle axis [m]')
    _legend(temperatureAxes, loc = 'lower right')

    if hasEntrainment:
        entrainmentAxes = lower[2]
        entrainmentAxes.plot(x, entrained, color = themeColors.purple, linewidth = 1.6)
        entrainmentAxes.set_ylabel('Entrained over film flow [-]', color = themeColors.purple)
        mixtureAxes = _twin(entrainmentAxes, themeColors.green)
        mixtureAxes.plot(x, mixture, color = themeColors.green, linewidth = 1.4)
        mixtureAxes.set_ylabel('Wall mixture ratio [-]', color = themeColors.green)
        entrainmentAxes.set_xlabel('Nozzle axis [m]')
    _throat(nozzle, [mapAxes] + lower)
    pane.redraw()

#--------------------------------------------------------------------------------------------------------------------------#
# -- The radiative extension -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawExtension(pane, nozzle) -> None:

    '''

    The radiation-cooled extension: the whole wall colored by its temperature, the jacket's and the
    extension's on one scale with the extension material's limit marked; the extension's wall
    against its radiative equilibrium and its limit; and the heat balance that sets it.

    '''

    from matplotlib.colors import Normalize

    if not extensionSolved(nozzle):
        pane.message('No radiative extension was solved for this run.')
        return

    solution = nozzle.radiativeExtensionSolution
    x, r = np.asarray(solution.axialPosition, dtype = float), np.asarray(solution.radius, dtype = float)
    wall = np.asarray(solution.extensionWallTemperature, dtype = float)
    limit = solution.extensionTemperatureLimit

    figure = pane.figure
    figure.clear()
    figure.set_layout_engine('constrained')
    pane._projection = None
    grid = figure.add_gridspec(2, 2, height_ratios = (1.1, 1.0))
    mapAxes = figure.add_subplot(grid[0, :])
    temperatureAxes = figure.add_subplot(grid[1, 0])
    fluxAxes = figure.add_subplot(grid[1, 1], sharex = temperatureAxes)
    for ax in (mapAxes, temperatureAxes, fluxAxes):
        themeColors.styleAxes(ax)
    pane.axes = fluxAxes

    # -- The whole wall on one temperature scale -- #
    results = thermalResults(nozzle)
    # The jacket's metal, as the shell's is: under a barrier coating the gas-side surface runs far
    # hotter and would set the scale for a temperature no limit applies to
    values = [wall] + ([_metalWall(results)] if results is not None else [])
    top = max(float(np.max(piece)) for piece in values)
    if limit:
        top = max(top, float(limit))
    norm = Normalize(vmin = min(float(np.min(piece)) for piece in values), vmax = top)
    cmap = _palette().colormap('temperature', themeColors.mode)
    wallX, wallR = _array(nozzle, 'xNozzleWall'), _array(nozzle, 'rNozzleWall')
    if wallX.size == wallR.size and wallX.size:
        mapAxes.plot(wallX, wallR, color = themeColors.textDim, linewidth = 1.0)
        mapAxes.fill_between(wallX, 0.0, wallR, color = themeColors.surface2, alpha = 0.35, linewidth = 0)
    band = _band(mapAxes, x, r, wall, cmap, norm, 7.0, zorder = 4)
    if results is not None:
        _band(mapAxes, results['xHotWall3D'], results['rHotWall3D'], _metalWall(results), cmap, norm, 7.0,
              zorder = 4)
    mapAxes.set_xlim(float(np.min(wallX)) if wallX.size else float(np.min(x)), float(np.max(x)))
    mapAxes.set_ylim(0.0, 1.2 * float(np.max(r)))
    mapAxes.set_aspect('equal', adjustable = 'box')
    mapAxes.grid(False)
    mapAxes.set_ylabel('Radius [m]')
    material = getattr(nozzle, 'extensionMaterial', None) or 'shell'
    atmosphere = str(getattr(nozzle, 'extensionAtmosphere', '') or '').replace('oxidisingCoated', 'oxidising, coated')
    peak = float(solution.extensionPeakWallTemperature)
    heading = f'{material} extension in an {atmosphere} atmosphere: peak wall {peak:.0f} K'
    if limit:
        margin = float(solution.extensionTemperatureMargin)
        heading += f', {abs(margin):.0f} K {"under" if margin >= 0 else "over"} its {float(limit):.0f} K limit'
    mapAxes.set_title(heading, color = themeColors.text)
    bar = _colorbar(pane, band, mapAxes, 'Wall temperature [K]: jacket and extension', 'vertical')
    if limit:
        bar.ax.axhline(float(limit), color = themeColors.red, linewidth = 2.0)

    # -- The extension's wall against its equilibrium and its limit -- #
    temperatureAxes.plot(x, wall, color = themeColors.accent, linewidth = 1.8, label = 'Wall')
    temperatureAxes.plot(x, solution.extensionEquilibriumTemperature, color = themeColors.blue, linewidth = 1.2,
                         linestyle = '--', label = 'Radiative equilibrium')
    if limit:
        temperatureAxes.axhline(float(limit), color = themeColors.red, linewidth = 1.0, linestyle = '--',
                                label = f'{material} limit')
    temperatureAxes.set_ylabel('Temperature [K]')
    temperatureAxes.set_xlabel('Nozzle axis [m]')
    _legend(temperatureAxes, loc = 'upper right')

    # -- The heat balance: what the gas puts in, what the shell radiates and conducts away -- #
    for name, label, color, sign in (('extensionConvectiveFlux', 'Convection in', themeColors.red, 1.0),
                                     ('extensionGasRadiativeFlux', 'Gas radiation in', themeColors.purple, 1.0),
                                     ('extensionEmittedFlux', 'Emitted out', themeColors.cyan, -1.0),
                                     ('extensionConductionFlux', 'Conducted along', themeColors.purple, 1.0)):
        values = np.asarray(getattr(solution, name), dtype = float)
        if values.size == x.size and np.any(values):
            fluxAxes.plot(x, sign * values / 1e3, color = color, linewidth = 1.4, label = label)
    fluxAxes.axhline(0.0, color = themeColors.textDim, linewidth = 0.8)
    fluxAxes.set_ylabel('Heat flux [kW/m²]')
    fluxAxes.set_xlabel('Nozzle axis [m]')
    residual = float(solution.extensionEnergyBalanceResidual)
    fluxAxes.set_title(f'Energy balance closes to {residual:.1e}', color = themeColors.textMuted, fontsize = 9)
    _legend(fluxAxes, loc = 'upper right')
    pane.redraw()

#--------------------------------------------------------------------------------------------------------------------------#
# -- The coolant circuit -- #
#--------------------------------------------------------------------------------------------------------------------------#

circuitNames = {'singlePass': 'A, single pass', 'oneAndHalfPass': 'B, one and a half pass', 'twoPass': 'C, two pass'}

def _arrows(ax, x, r, color: str, forward: bool, count: int = 4) -> None:

    '''Arrowheads along a line, pointing the way the coolant runs.'''

    if len(x) < 3:
        return
    for k in np.linspace(0, len(x) - 2, count + 2)[1:-1].astype(int):
        start, end = (k, k + 1) if forward else (k + 1, k)
        ax.annotate('', xy = (x[end], r[end]), xytext = (x[start], r[start]),
                    arrowprops = dict(arrowstyle = '-|>', color = color, lw = 1.4))

def drawCircuit(pane, nozzle) -> None:

    '''

    The nozzle's half section with the coolant's paths drawn on it: each family of the chamber
    jacket with the way it runs, its manifolds, turnaround and split, the extension's own circuit
    and its outlet, the film slots and the radiation-cooled shell.

    '''

    results = thermalResults(nozzle)
    if results is None:
        pane.message('No cooling jacket was built for this run.')
        return
    (ax,) = _panels(pane, 1)
    xWall, rWall = np.asarray(nozzle.xNozzleWall), np.asarray(nozzle.rNozzleWall)
    ax.plot(xWall, rWall, color = themeColors.textDim, linewidth = 1.2, label = 'Hot wall')
    step = 0.03 * float(np.max(rWall))

    x, r = np.asarray(results['xHotWall3D']), np.asarray(results['rHotWall3D'])
    circuit = getattr(nozzle, 'coolantCircuitSolution', None)
    if circuit is None:
        coflow = getattr(nozzle, 'jacketFlowDirection', 'counterflow') == 'coflow'
        ax.plot(x, r + step, color = themeColors.accent, linewidth = 2.2, label = 'Chamber jacket')
        _arrows(ax, x, r + step, themeColors.accent, forward = coflow)
        inlet, outlet = (0, -1) if coflow else (-1, 0)
        ax.plot(x[inlet], r[inlet] + step, marker = 'v', color = themeColors.accent, markersize = 9,
                linestyle = 'none', label = 'Inlet manifold')
        ax.plot(x[outlet], r[outlet] + step, marker = '^', color = themeColors.accent, markersize = 9,
                linestyle = 'none', label = 'Outlet manifold')
    else:
        down = circuit.down.stations
        ax.plot(x, r + step, color = themeColors.accent, linewidth = 2.2,
                label = f'Up family, {circuit.up.channelCount} channels')
        _arrows(ax, x, r + step, themeColors.accent, forward = False)
        ax.plot(x[down], r[down] + 2 * step, color = themeColors.blue, linewidth = 2.2,
                label = f'Down family, {circuit.down.channelCount} channels')
        _arrows(ax, x[down], r[down] + 2 * step, themeColors.blue, forward = True)
        ax.plot(x[down[0]], r[down[0]] + 2 * step, marker = 'v', color = themeColors.blue, markersize = 9,
                linestyle = 'none', label = 'Inlet manifold')
        ax.plot(x[-1], r[-1] + 1.5 * step, marker = 'o', markersize = 12, markerfacecolor = 'none',
                markeredgecolor = themeColors.purple, markeredgewidth = 2.0, linestyle = 'none',
                label = 'Turnaround ring')
        ax.plot(x[0], r[0] + step, marker = '^', color = themeColors.accent, markersize = 9, linestyle = 'none',
                label = 'Outlet manifold')

    blend = getattr(nozzle, 'channelSplitBlend', None)
    xInterfaced = getattr(nozzle, 'xRegenNozzleInterfaced', None)
    if blend is not None and xInterfaced is not None:
        inside = np.flatnonzero((np.asarray(blend) > 0.0) & (np.asarray(blend) < 1.0))
        if inside.size:
            ax.axvspan(float(np.asarray(xInterfaced)[inside[0]]), float(np.asarray(xInterfaced)[inside[-1]]),
                       color = themeColors.purple, alpha = 0.18, label = 'Channel split')

    extension = getattr(nozzle, 'extensionCircuitSolution', None)
    xExtension = getattr(nozzle, 'xExtension', None)
    if extension is not None and xExtension is not None:
        xe = np.asarray(xExtension)[extension.stations]
        re = np.asarray(nozzle.rExtension)[extension.stations]
        ax.plot(xe, re + step, color = themeColors.purple, linewidth = 2.2,
                label = f'Extension circuit, outlet {extension.outlet}')
        _arrows(ax, xe, re + step, themeColors.purple, forward = extension.direction == 'coflow')
    shell = getattr(nozzle, 'extensionWallTemperature', None)
    if shell is not None and xExtension is not None:
        start = len(xExtension) - len(shell)
        ax.plot(np.asarray(xExtension)[start:], np.asarray(nozzle.rExtension)[start:] + step, color = themeColors.textMuted,
                linewidth = 1.6, linestyle = '--', label = 'Radiation-cooled shell')

    # Slots a few stations apart would print their names over each other, so each sits a line
    # lower than the one before
    film = getattr(nozzle, 'extensionFilmSolution', None)
    if film is not None:
        names = {'turbineExhaust': 'turbine exhaust', 'extensionCircuitOutlet': 'circuit outlet',
                 'chamber': 'chamber film'}
        for number, layer in enumerate(film.layers):
            xf = float(film.x[layer.injectionIndex])
            rf = float(np.interp(xf, xWall, rWall))
            source = layer.name.split(' slot')[0]
            ax.plot(xf, rf - step, marker = '>', color = themeColors.cyan, markersize = 9, linestyle = 'none')
            ax.annotate(names.get(source, source), (xf, rf - step), xytext = (4, -12 - 11 * number),
                        textcoords = 'offset points', color = themeColors.cyan, fontsize = 7)

    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')
    ax.set_aspect('equal', adjustable = 'datalim')
    title = 'Coolant circuit: ' + circuitNames.get(getattr(nozzle, 'coolantCircuit', None), 'A, single pass')
    if extension is not None:
        title += ', with an extension circuit (D)'
    ax.set_title(title, color = themeColors.text)
    _legend(ax, loc = 'upper left')
    pane.redraw()

def drawPasses(pane, nozzle) -> None:

    '''Each pass's coolant and hot wall: the chamber jacket's two families and the extension circuit.'''

    circuit = getattr(nozzle, 'coolantCircuitSolution', None)
    extension = getattr(nozzle, 'extensionCircuitSolution', None)
    if circuit is None and extension is None:
        pane.message('This run has a single pass and no extension circuit.')
        return
    coolantAxes, wallAxes = _panels(pane, 2)
    if circuit is not None:
        for passSolution, color in ((circuit.down, themeColors.blue), (circuit.up, themeColors.accent)):
            x = np.asarray(passSolution.results['xHotWall3D'])
            coolantAxes.plot(x, passSolution.results['temperature'], color = color, linewidth = 1.8,
                             label = f'{passSolution.name} pass')
            wallAxes.plot(x, _metalWall(passSolution.results), color = color, linewidth = 1.6,
                          label = f'{passSolution.name} family')
    if extension is not None and extension.circuit is None:
        x = np.asarray(nozzle.xExtension)[extension.stations]
        coolantAxes.plot(x, extension.sizing.channelThermalResults['temperature'], color = themeColors.purple,
                         linewidth = 1.8, label = 'extension circuit')
        wallAxes.plot(x, extension.metalWallTemperature, color = themeColors.purple, linewidth = 1.6,
                      label = 'extension circuit')
    elif extension is not None:
        # Two passes on the extension: the down pass dashed, the up pass solid
        for passSolution, style in ((extension.circuit.down, '--'), (extension.circuit.up, '-')):
            x = np.asarray(passSolution.results['xHotWall3D'])
            coolantAxes.plot(x, passSolution.results['temperature'], color = themeColors.purple, linewidth = 1.8,
                             linestyle = style, label = f'extension {passSolution.name} pass')
            wallAxes.plot(x, _metalWall(passSolution.results), color = themeColors.purple, linewidth = 1.6,
                          linestyle = style, label = f'extension {passSolution.name} family')
    limit = getattr(nozzle, 'maxWallTemperature', None)
    if limit:
        wallAxes.axhline(float(limit), color = themeColors.red, linewidth = 1.0, linestyle = '--')
    coolantAxes.set_ylabel('Coolant temperature [K]')
    wallAxes.set_ylabel('Hot wall temperature [K]')
    wallAxes.set_xlabel('Nozzle axis [m]')
    coolantAxes.set_title('Coolant and hot wall of each pass', color = themeColors.text)
    _legend(coolantAxes)
    _legend(wallAxes)
    _throat(nozzle, (coolantAxes, wallAxes))
    pane.redraw()

#--------------------------------------------------------------------------------------------------------------------------#
# -- The circuit's outer iteration -- #
#--------------------------------------------------------------------------------------------------------------------------#

# The circuits whose outer iteration is drawn, by key, with what a figure calls each, in drawing order
iterationLoops = (('jacket', 'jacket'), ('extension', 'extension circuit'))

def legStyle(loopKey: str, leg: str) -> tuple:

    '''

    A leg's color name in the palette and whether it is dashed, as the passes view draws it: the
    jacket's down leg blue and its up leg copper, the extension circuit's legs purple, down dashed.

    '''

    if loopKey == 'extension':
        return 'purple', leg == 'down'

    return ('blue' if leg == 'down' else 'accent'), False

def iterationAlpha(position: int, count: int) -> float:

    '''The opacity of a pass's lines: the latest solid, the earlier ones fading with age.'''

    if position >= count - 1:
        return 1.0

    return 0.25 + 0.4 * position / max(1, count - 1)

def iterationDescription(nozzle) -> dict:

    '''

    Every pass of each multi-pass circuit the run solved, as the iteration figures draw them, or
    None when no circuit iterated.

    A running run's description is built in the same form from the circuit's profile events
    (novaGui.session), so a run still going and a finished run draw through the same renderers:

        {'loops': [{'key', 'label', 'iterations': [{'index', 'change' [K] or None,
                    'legs': [{'leg', 'x' [m], 'wall' [K], 'coolant' [K]}, ...]}, ...]}, ...],
         'limit': wall temperature limit [K] or None, 'throatX': [m] or None}

    '''

    extension = getattr(nozzle, 'extensionCircuitSolution', None)
    solutions = {'jacket': getattr(nozzle, 'coolantCircuitSolution', None),
                 'extension': getattr(extension, 'circuit', None) if extension is not None else None}
    loops = []
    for key, label in iterationLoops:
        # A circuit solved before its passes were kept has none, and draws nothing here
        iterations = getattr(solutions[key], 'iterationProfiles', None) if solutions[key] is not None else None
        if iterations:
            loops.append({'key': key, 'label': label, 'iterations': list(iterations)})
    if not loops:
        return None

    limit = getattr(nozzle, 'maxWallTemperature', None)
    wallX, wallR = _array(nozzle, 'xNozzleWall'), _array(nozzle, 'rNozzleWall')
    throatX = float(wallX[int(np.argmin(wallR))]) if wallX.size >= 2 and wallR.size == wallX.size else None

    return {'loops': loops, 'limit': float(limit) if limit else None, 'throatX': throatX}

def iterationThroat(description: dict):

    '''The throat's axial position where it lies on a circuit drawn, else None: an extension circuit lies past it.'''

    throatX = description.get('throatX')
    if throatX is None:
        return None
    x = np.concatenate([np.asarray(leg['x'], dtype = float) for loop in description['loops']
                        for entry in loop['iterations'] for leg in entry['legs']])
    x = x[np.isfinite(x)]

    return float(throatX) if x.size and float(np.min(x)) <= float(throatX) <= float(np.max(x)) else None

def iterationSummary(description: dict) -> str:

    '''

    Each circuit's passes and its last change, for a title: 'jacket, 7 passes, last change 0.027 K'.

    '''

    parts = []
    for loop in description['loops']:
        iterations = loop['iterations']
        count = len(iterations)
        change = iterations[-1].get('change') if count else None
        text = f'{loop["label"]}, {count} pass{"es" if count != 1 else ""}'
        parts.append(text + (f', last change {change:.3g} K' if change is not None else ''))

    return '; '.join(parts)

def drawCircuitIterations(pane, nozzle) -> None:

    '''

    The hot wall and the coolant along the wall at every pass of each multi-pass circuit's outer
    iteration, the latest solid and the earlier ones fading, so where the circuit was still moving
    reads off the axis.

    '''

    description = iterationDescription(nozzle)
    if description is None:
        pane.message('This run has no multi-pass circuit, so no circuit iterated.')
        return

    wallAxes, coolantAxes = _panels(pane, 2, heightRatios = (1.2, 1.0))
    for loop in description['loops']:
        count = len(loop['iterations'])
        for position, entry in enumerate(loop['iterations']):
            latest = position == count - 1
            for leg in entry['legs']:
                colorName, dashed = legStyle(loop['key'], leg['leg'])
                style = dict(color = getattr(themeColors, colorName), alpha = iterationAlpha(position, count),
                             linewidth = 1.8 if latest else 1.2, linestyle = '--' if dashed else '-')
                label = f'{loop["label"]} {leg["leg"]}, pass {entry["index"]}' if latest else None
                x = np.asarray(leg['x'], dtype = float)
                wallAxes.plot(x, np.asarray(leg['wall'], dtype = float), label = label, **style)
                coolantAxes.plot(x, np.asarray(leg['coolant'], dtype = float), **style)
    if description['limit']:
        wallAxes.axhline(description['limit'], color = themeColors.red, linewidth = 1.0, linestyle = '--',
                         label = f'Wall limit {description["limit"]:.0f} K')
    wallAxes.set_ylabel('Hot wall temperature [K]')
    coolantAxes.set_ylabel('Coolant temperature [K]')
    coolantAxes.set_xlabel('Nozzle axis [m]')
    wallAxes.set_title(f'Each pass of the circuit, earlier passes fading\n{iterationSummary(description)}',
                       color = themeColors.text, fontsize = 10)
    _legend(wallAxes)
    throatX = iterationThroat(description)
    if throatX is not None:
        for ax in (wallAxes, coolantAxes):
            ax.axvline(throatX, color = themeColors.textDim, linewidth = 0.8, linestyle = ':', zorder = 0)
    pane.redraw()
