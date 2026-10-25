
# -- NOVA GUI Thermal Views -- #

'''

The View tab's cooling views: the regenerative jacket, the film and the radiative extension.

Each draws from what the run kept on the Nozzle, never from a saved figure, so it follows the
window's theme:

    drawWallMap            the jacket on the nozzle wall: hot wall and coolant temperature along it
    drawJacketTemperatures hot wall against its limit and the gas driving it, and the coolant warming
    drawCoolantFlow        coolant pressure, velocity and Mach number along the channel
    drawCoolantProperties  coolant density, viscosity and specific heat along the channel
    drawHeatFlux           heat flux with its radiative share, both film coefficients, Reynolds and
                           Nusselt numbers
    drawFilm               the film along the wall, its effectiveness and the temperatures it sets
    drawExtension          the extension's wall temperature against its limit, and its heat balance

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

from . import theme
from .plotting import MplPane, _palette

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

def filmSolved(nozzle) -> bool:

    effectiveness = _array(nozzle, 'regenSectionFilmEffectiveness')

    return effectiveness.size >= 2 and effectiveness.size == _array(nozzle, 'xRegenNozzle').size

def extensionSolved(nozzle) -> bool:

    return getattr(nozzle, 'radiativeExtensionSolution', None) is not None \
        and _array(nozzle, 'extensionWallTemperature').size >= 2

def _panels(pane: MplPane, rows: int, cols: int = 1, heightRatios = None, sharex: bool = True) -> list:

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
            theme.styleAxes(ax)
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
        ax.axvline(throatX, color = theme.textDim, linewidth = 0.8, linestyle = ':', zorder = 0)

def _legend(ax, **options) -> None:

    ax.legend(facecolor = theme.surface2, edgecolor = theme.border, labelcolor = theme.text, fontsize = 8,
              framealpha = 0.95, **options)

def _twin(ax, color: str):

    '''A second y axis on the right, in a series color.'''

    twin = ax.twinx()
    twin.tick_params(colors = color)
    twin.grid(False)
    for spine in twin.spines.values():
        spine.set_color(theme.border)

    return twin

def _colorbar(pane: MplPane, mappable, axes, label: str, orientation: str = 'horizontal'):

    bar = pane.figure.colorbar(mappable, ax = axes, orientation = orientation, fraction = 0.05, pad = 0.08)
    bar.set_label(label, color = theme.text)
    bar.outline.set_edgecolor(theme.border)
    bar.ax.tick_params(colors = theme.textMuted)

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

def drawWallMap(pane: MplPane, nozzle) -> None:

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
    wall, coolant = np.asarray(results['wallTemperature']), np.asarray(results['temperature'])
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
    theme.styleAxes(ax)
    pane.axes = ax
    ax.grid(False)

    # The whole contour for context, the jacketed part of it banded
    wallX, wallR = _array(nozzle, 'xNozzleWall'), _array(nozzle, 'rNozzleWall')
    if wallX.size == wallR.size and wallX.size:
        ax.plot(wallX, wallR, color = theme.textDim, linewidth = 1.0)
        ax.fill_between(wallX, 0.0, wallR, color = theme.surface2, alpha = 0.35, linewidth = 0)

    top = max(float(np.max(wall)), float(limit) if limit else 0.0)
    wallNorm = Normalize(vmin = float(np.min(wall)), vmax = top)
    coolantNorm = Normalize(vmin = float(np.min(coolant)), vmax = float(np.max(coolant)))
    wallBand = _band(ax, x, r, wall, _palette().colormap('temperature', theme.mode), wallNorm, 7.0, zorder = 4)
    coolantBand = _band(ax, x, r + offset, coolant, _palette().colormap('mach', theme.mode), coolantNorm, 5.0)

    ax.text(float(np.mean(x)), 0.45 * float(np.min(r)), 'exhaust', color = theme.textMuted, fontsize = 9,
            ha = 'center', style = 'italic')
    _flowDirection(ax, x, np.asarray(results['pressure']), theme.textMuted)
    ax.text(0.995, 0.03, 'coolant band drawn outside the wall, not to scale', transform = ax.transAxes, ha = 'right',
            va = 'bottom', color = theme.textMuted, fontsize = 7, style = 'italic')

    span = float(np.max(x) - np.min(x))
    ax.set_xlim(float(np.min(x)) - 0.04 * span, float(np.max(x)) + 0.04 * span)
    ax.set_ylim(0.0, 1.3 * float(np.max(r + offset)))
    ax.set_aspect('equal', adjustable = 'box')
    ax.set_xlabel('Nozzle axis [m]')
    ax.set_ylabel('Radius [m]')
    total = float(np.sum(results['heatTransfer'])) * float(getattr(nozzle, 'nChannel', 1) or 1)
    ax.set_title(f'The jacket on the wall: {int(getattr(nozzle, "nChannel", 0) or 0)} channels, '
                 f'{total / 1e6:.2f} MW into the coolant', color = theme.text)

    for scale, mappable, label in ((wallScale, wallBand, 'Hot wall temperature [K]'),
                                   (coolantScale, coolantBand, 'Coolant temperature [K]')):
        bar = figure.colorbar(mappable, cax = scale, orientation = 'horizontal')
        bar.set_label(label, color = theme.text)
        bar.outline.set_edgecolor(theme.border)
        bar.ax.tick_params(colors = theme.textMuted)
        if scale is wallScale and limit:
            bar.ax.axvline(float(limit), color = theme.red, linewidth = 2.0)
    pane.redraw()

def drawJacketTemperatures(pane: MplPane, nozzle) -> None:

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

    wallAxes.plot(x, results['wallTemperature'], color = theme.accent, linewidth = 1.8, label = 'Hot wall')
    limit = getattr(nozzle, 'maxWallTemperature', None)
    if limit:
        wallAxes.axhline(float(limit), color = theme.red, linewidth = 1.0, linestyle = '--',
                         label = f'Wall limit {float(limit):.0f} K')
    gasAxes = _twin(wallAxes, theme.blue)
    gasAxes.plot(x, results['drivingTemperature'], color = theme.blue, linewidth = 1.2, label = 'Gas driving the wall')
    gasAxes.set_ylabel('Gas driving temperature [K]', color = theme.blue)
    wallAxes.set_ylabel('Hot wall temperature [K]')
    wallAxes.set_title('Wall and coolant temperatures', color = theme.text)
    handles, labels = wallAxes.get_legend_handles_labels()
    gasHandles, gasLabels = gasAxes.get_legend_handles_labels()
    gasAxes.legend(handles + gasHandles, labels + gasLabels, facecolor = theme.surface2, edgecolor = theme.border,
                   labelcolor = theme.text, fontsize = 8, loc = 'lower center', framealpha = 0.95)

    coolant = np.asarray(results['temperature'])
    coolantAxes.plot(x, coolant, color = theme.cyan, linewidth = 1.8)
    coolantAxes.fill_between(x, float(np.min(coolant)), coolant, color = theme.cyan, alpha = 0.15, linewidth = 0)
    coolantAxes.set_ylabel('Coolant temperature [K]')
    coolantAxes.set_xlabel('Nozzle axis [m]')
    _flowDirection(coolantAxes, x, np.asarray(results['pressure']), theme.textMuted)
    rise = float(np.max(coolant) - np.min(coolant))
    coolantAxes.set_title(f'Coolant warms {rise:.0f} K, from {float(np.min(coolant)):.0f} to '
                          f'{float(np.max(coolant)):.0f} K', color = theme.textMuted, fontsize = 9)
    _throat(nozzle, (wallAxes, coolantAxes))
    pane.redraw()

def drawCoolantFlow(pane: MplPane, nozzle) -> None:

    '''Coolant pressure, velocity and Mach number along the channel.'''

    results = thermalResults(nozzle)
    if results is None:
        pane.message('No cooling jacket was built for this run.')
        return

    x = np.asarray(results['xHotWall3D'])
    pressure = np.asarray(results['pressure'])
    axes = _panels(pane, 3)
    series = ((pressure / 1e6, 'Pressure [MPa]', theme.accent), (results['velocity'], 'Velocity [m/s]', theme.blue),
              (results['machNumber'], 'Mach number [-]', theme.cyan))
    for ax, (values, label, color) in zip(axes, series):
        ax.plot(x, values, color = color, linewidth = 1.7)
        ax.set_ylabel(label)
    drop = float(np.max(pressure) - np.min(pressure))
    axes[0].set_title(f'Coolant flow: {drop / 1e3:.0f} kPa pressure drop, exit at {float(np.min(pressure)) / 1e6:.2f} MPa',
                      color = theme.text)
    _flowDirection(axes[0], x, pressure, theme.textMuted)
    axes[-1].set_xlabel('Nozzle axis [m]')
    _throat(nozzle, axes)
    pane.redraw()

def drawCoolantProperties(pane: MplPane, nozzle) -> None:

    '''The coolant's density, viscosity and specific heat along the channel, from its equation of state.'''

    results = thermalResults(nozzle)
    if results is None:
        pane.message('No cooling jacket was built for this run.')
        return

    x = np.asarray(results['xHotWall3D'])
    axes = _panels(pane, 3)
    series = ((results['density'], 'Density [kg/m³]', theme.accent),
              (np.asarray(results['viscosity']) * 1e6, 'Viscosity [µPa·s]', theme.purple),
              (np.asarray(results['specificHeat']) * 1e-3, 'Specific heat [kJ/kg·K]', theme.green))
    for ax, (values, label, color) in zip(axes, series):
        ax.plot(x, values, color = color, linewidth = 1.7)
        ax.set_ylabel(label)
    coolant = getattr(nozzle, 'coolant', None) or 'coolant'
    axes[0].set_title(f'Thermophysical properties of the {coolant} along the channel', color = theme.text)
    _flowDirection(axes[0], x, np.asarray(results['pressure']), theme.textMuted)
    axes[-1].set_xlabel('Nozzle axis [m]')
    _throat(nozzle, axes)
    pane.redraw()

def drawHeatFlux(pane: MplPane, nozzle) -> None:

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
    fluxAxes.fill_between(x, 0.0, flux, color = theme.accent, alpha = 0.25, linewidth = 0)
    fluxAxes.plot(x, flux, color = theme.accent, linewidth = 1.7, label = 'Total')
    heat = np.asarray(results['heatTransfer'])
    radiative = np.asarray(results.get('radiativeHeatTransfer', np.zeros_like(heat)))
    if np.any(radiative):
        share = np.divide(radiative, heat, out = np.zeros_like(heat), where = heat != 0.0)
        fluxAxes.plot(x, flux * share, color = theme.yellow, linewidth = 1.2, label = 'Radiative share')
        _legend(fluxAxes, loc = 'upper left')
    fluxAxes.set_ylabel('Heat flux [MW/m²]')
    fluxAxes.set_title(f'Heat flux peaks at {float(np.max(flux)):.1f} MW/m²', color = theme.text)

    coefficientAxes.plot(x, np.asarray(results['exhaustConvectiveHeatTransferCoef']) / 1e3, color = theme.red,
                         linewidth = 1.6, label = 'Gas side')
    coefficientAxes.plot(x, np.asarray(results['coolantConvectiveHeatTransferCoef']) / 1e3, color = theme.cyan,
                         linewidth = 1.6, label = 'Coolant side')
    coefficientAxes.set_ylabel('Film coefficient [kW/m²·K]')
    _legend(coefficientAxes, loc = 'upper left')

    groupAxes.plot(x, np.asarray(results['reynoldsNumber']) / 1e6, color = theme.blue, linewidth = 1.6)
    groupAxes.set_ylabel('Reynolds number [10⁶]', color = theme.blue)
    nusseltAxes = _twin(groupAxes, theme.green)
    nusseltAxes.plot(x, results['nusseltNumber'], color = theme.green, linewidth = 1.4)
    nusseltAxes.set_ylabel('Nusselt number [-]', color = theme.green)
    groupAxes.set_xlabel('Nozzle axis [m]')
    _throat(nozzle, (fluxAxes, coefficientAxes, groupAxes))
    pane.redraw()

#--------------------------------------------------------------------------------------------------------------------------#
# -- The film -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawFilm(pane: MplPane, nozzle) -> None:

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
        theme.styleAxes(ax)
    pane.axes = lower[-1]

    # -- The map: the core at its recovery temperature, the film as a band on the wall -- #
    cmap = _palette().colormap('temperature', theme.mode)
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
    mapAxes.plot(x, r, color = theme.accent, linewidth = 2.0)
    mapAxes.annotate('slot', xy = (x[slot], r[slot]), xytext = (x[slot], 1.18 * float(np.max(r))),
                     color = theme.text, fontsize = 8, ha = 'center',
                     arrowprops = dict(arrowstyle = '->', color = theme.textMuted, linewidth = 0.8))
    if survival > 0.0:
        end = float(x[slot]) + survival
        mapAxes.axvline(end, color = theme.textMuted, linewidth = 0.8, linestyle = '--')
        mapAxes.text(end, 1.08 * float(np.max(r)), ' effectiveness 0.3', color = theme.textMuted, fontsize = 8)
    mapAxes.text(0.995, 0.03, 'film band drawn at a fixed thickness: the film model resolves the film along '
                 'the wall, not across it', transform = mapAxes.transAxes, ha = 'right', va = 'bottom',
                 color = theme.textMuted, fontsize = 7, style = 'italic')
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
                      f'slot ({model}): useful for {1e3 * survival:.0f} mm', color = theme.text)
    _colorbar(pane, film, mapAxes, 'Gas temperature at the wall [K]', 'vertical')

    # -- Effectiveness -- #
    effectivenessAxes = lower[0]
    effectivenessAxes.fill_between(x, 0.0, effectiveness, color = theme.cyan, alpha = 0.25, linewidth = 0)
    effectivenessAxes.plot(x, effectiveness, color = theme.cyan, linewidth = 1.7)
    effectivenessAxes.axhline(0.3, color = theme.textMuted, linewidth = 0.8, linestyle = '--')
    effectivenessAxes.set_ylim(0.0, 1.05)
    effectivenessAxes.set_ylabel('Film effectiveness [-]')
    effectivenessAxes.set_xlabel('Nozzle axis [m]')

    # -- What the wall is driven by, with and without the film -- #
    temperatureAxes = lower[1]
    temperatureAxes.plot(x, recovery, color = theme.red, linewidth = 1.4, label = 'Without the film')
    temperatureAxes.plot(x, driving, color = theme.cyan, linewidth = 1.7, label = 'Under the film')
    results = thermalResults(nozzle)
    if results is not None:
        temperatureAxes.plot(results['xHotWall3D'], results['wallTemperature'], color = theme.accent, linewidth = 1.4,
                             label = 'Hot wall')
    temperatureAxes.set_ylabel('Temperature [K]')
    temperatureAxes.set_xlabel('Nozzle axis [m]')
    _legend(temperatureAxes, loc = 'lower right')

    if hasEntrainment:
        entrainmentAxes = lower[2]
        entrainmentAxes.plot(x, entrained, color = theme.purple, linewidth = 1.6)
        entrainmentAxes.set_ylabel('Entrained over film flow [-]', color = theme.purple)
        mixtureAxes = _twin(entrainmentAxes, theme.green)
        mixtureAxes.plot(x, mixture, color = theme.green, linewidth = 1.4)
        mixtureAxes.set_ylabel('Wall mixture ratio [-]', color = theme.green)
        entrainmentAxes.set_xlabel('Nozzle axis [m]')
    _throat(nozzle, [mapAxes] + lower)
    pane.redraw()

#--------------------------------------------------------------------------------------------------------------------------#
# -- The radiative extension -- #
#--------------------------------------------------------------------------------------------------------------------------#

def drawExtension(pane: MplPane, nozzle) -> None:

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
        theme.styleAxes(ax)
    pane.axes = fluxAxes

    # -- The whole wall on one temperature scale -- #
    results = thermalResults(nozzle)
    values = [wall] + ([np.asarray(results['wallTemperature'])] if results is not None else [])
    top = max(float(np.max(piece)) for piece in values)
    if limit:
        top = max(top, float(limit))
    norm = Normalize(vmin = min(float(np.min(piece)) for piece in values), vmax = top)
    cmap = _palette().colormap('temperature', theme.mode)
    wallX, wallR = _array(nozzle, 'xNozzleWall'), _array(nozzle, 'rNozzleWall')
    if wallX.size == wallR.size and wallX.size:
        mapAxes.plot(wallX, wallR, color = theme.textDim, linewidth = 1.0)
        mapAxes.fill_between(wallX, 0.0, wallR, color = theme.surface2, alpha = 0.35, linewidth = 0)
    band = _band(mapAxes, x, r, wall, cmap, norm, 7.0, zorder = 4)
    if results is not None:
        _band(mapAxes, results['xHotWall3D'], results['rHotWall3D'], results['wallTemperature'], cmap, norm, 7.0,
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
    mapAxes.set_title(heading, color = theme.text)
    bar = _colorbar(pane, band, mapAxes, 'Wall temperature [K]: jacket and extension', 'vertical')
    if limit:
        bar.ax.axhline(float(limit), color = theme.red, linewidth = 2.0)

    # -- The extension's wall against its equilibrium and its limit -- #
    temperatureAxes.plot(x, wall, color = theme.accent, linewidth = 1.8, label = 'Wall')
    temperatureAxes.plot(x, solution.extensionEquilibriumTemperature, color = theme.blue, linewidth = 1.2,
                         linestyle = '--', label = 'Radiative equilibrium')
    if limit:
        temperatureAxes.axhline(float(limit), color = theme.red, linewidth = 1.0, linestyle = '--',
                                label = f'{material} limit')
    temperatureAxes.set_ylabel('Temperature [K]')
    temperatureAxes.set_xlabel('Nozzle axis [m]')
    _legend(temperatureAxes, loc = 'upper right')

    # -- The heat balance: what the gas puts in, what the shell radiates and conducts away -- #
    for name, label, color, sign in (('extensionConvectiveFlux', 'Convection in', theme.red, 1.0),
                                     ('extensionGasRadiativeFlux', 'Gas radiation in', theme.yellow, 1.0),
                                     ('extensionEmittedFlux', 'Emitted out', theme.cyan, -1.0),
                                     ('extensionConductionFlux', 'Conducted along', theme.purple, 1.0)):
        values = np.asarray(getattr(solution, name), dtype = float)
        if values.size == x.size and np.any(values):
            fluxAxes.plot(x, sign * values / 1e3, color = color, linewidth = 1.4, label = label)
    fluxAxes.axhline(0.0, color = theme.textDim, linewidth = 0.8)
    fluxAxes.set_ylabel('Heat flux [kW/m²]')
    fluxAxes.set_xlabel('Nozzle axis [m]')
    residual = float(solution.extensionEnergyBalanceResidual)
    fluxAxes.set_title(f'Energy balance closes to {residual:.1e}', color = theme.textMuted, fontsize = 9)
    _legend(fluxAxes, loc = 'upper right')
    pane.redraw()
