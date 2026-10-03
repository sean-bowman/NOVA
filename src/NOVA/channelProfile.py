# -- NOVA: Cooling Channel Profile -- #

'''

Fixing a cooling channel's size by hand, as a profile along the jacket.

The sizing solve converges the channel's radial half-extent at every station against a wall
temperature limit, and pays about seven passes of the thermal model per station to do it. A
jacket whose size is already decided does not need that search. It needs the size read off a
profile and marched once, which is what this module supplies: the coordinate a profile is
written in, the reader that turns a configuration entry into control points, and the
interpolation that puts a half-extent on every station.

The thermal model still runs one pass per station under a manual profile, so the wall
temperature, the pressure drop and the coolant exit state all come out. They are reported rather
than converged to, and nothing holds the wall at its limit: that is the trade a fixed geometry
makes.

A profile is a list of control points, each a key and a half-extent [m]. Between points it is
linear in the key, and outside the range the points cover it is flat at the nearest one. A
single point is a constant channel. Two keys are read:

    areaRatio        Local area ratio, negative upstream of the throat. The injector face of a
                     3.2 contraction ratio chamber is -3.2, the throat is -1 on the converging
                     side and +1 on the diverging side, and an exit at area ratio 3 is +3. This
                     is the key a profile is written in by hand, because it is anchored to the
                     throat rather than to the length of one particular jacket. No station sits
                     between -1 and +1, so a profile that means to pin the throat states both.

    jacketFraction   Meridional distance along the jacket, 0 at the injector face end and 1 at
                     the regen truncation. This is the key a recorded profile is written in,
                     because it is injective where the area ratio is not: a constant radius
                     barrel holds one area ratio over its whole length, so a profile keyed on
                     area ratio cannot vary along a barrel and one keyed on fraction can.
                     Stations are respaced by arc length before the jacket is laid out, so a
                     profile recorded at one station count replays at another.

A recorded profile is written out as a document carrying its own key and channel family, and a
configuration may name that file instead of listing points. The file's key and family win over
the configuration's, so replaying a recording reproduces it rather than reinterpreting it.

----------------------------------------------------------------------
                            Validation status
----------------------------------------------------------------------

**Nothing here is a physical model.** A key is a coordinate built from the wall the jacket sits
on and a profile is a linear interpolation, so both are exact and both are held in closed form by
tests/testChannelProfile.py: the signed area ratio against its definition on a cone and a
barrel, the fraction against the arc length it is built from, the interpolation against its end
clamps and its single-point case, and a round trip of a recorded document.

What a manual profile does not carry is any claim that the jacket it describes cools the wall.
The wall temperature it produces comes from the thermal model and carries that model's
disclosures in full; a profile only decides the geometry the model is asked about.

All units are mass base SI:
    - Length [m]

Author: Sean Bowman

'''

from dataclasses import dataclass

import io
import json
import os

import numpy as np

from .errors import InvalidInputError

# How the channel size is decided. 'thermal' converges it against the wall temperature limit;
# 'manual' reads it off a profile and marches once.
CHANNELSIZINGMODES = ('thermal', 'manual')

# The coordinates a profile may be keyed on.
PROFILEKEYS = ('areaRatio', 'jacketFraction')

@dataclass(frozen = True)
class ChannelProfile:

    '''

    A channel size distribution, as control points in one of the profile keys.

    Attributes:
    -----------
    points : np.ndarray
        Control points, shape (N, 2): the key in the first column and the radial half-extent
        [m] in the second. Keys are strictly increasing.
    keyName : str
        One of PROFILEKEYS, naming the coordinate the first column is in.
    channelType : str
        Channel family the profile was recorded for, or None where the configuration listed
        points directly and said nothing about a family.
    source : str
        Path the profile was read from, or None where it came from the configuration.

    '''

    points:      np.ndarray
    keyName:     str
    channelType: str = None
    source:      str = None

def signedAreaRatio(radius) -> np.ndarray:

    '''

    Local area ratio at each station, signed negative upstream of the throat.

    The throat is the first smallest radius on the wall given. Everything before it carries the
    minus sign, so the key rises from the injector face to the jacket's aft end and is readable
    as an area ratio at both. A wall that holds its smallest radius over several stations reads
    +1 from the first of them on, which keeps the key non-decreasing.

    Parameters:
    -----------
    radius : array-like
        Wall radius at each station, in nozzle order [m].

    Returns:
    --------
    np.ndarray
        Signed area ratio at each station [-].

    Raises:
    -------
    InvalidInputError
        If the wall is not a one-dimensional array of at least two positive radii.

    '''

    radius = np.asarray(radius, dtype = float)

    if radius.ndim != 1 or radius.size < 2 or not np.all(np.isfinite(radius)) or np.any(radius <= 0.0):
        raise InvalidInputError(
            message = 'The signed area ratio is built from the wall the jacket sits on, which '
                      'has to be a run of at least two positive radii.',
            parameterName = 'radius',
            value = np.shape(radius),
            validRange = 'One-dimensional array of at least 2 finite positive values [m]')

    throatIndex = int(np.argmin(radius))
    ratio       = (radius/radius[throatIndex])**2

    # The throat station itself is the start of the diverging side, so it reads +1.
    ratio[:throatIndex] *= -1.0

    return ratio

def jacketFraction(axialPosition, radius) -> np.ndarray:

    '''

    Meridional distance along the jacket at each station, normalized to the whole.

    Parameters:
    -----------
    axialPosition, radius : array-like
        Wall coordinates at each station, in nozzle order [m].

    Returns:
    --------
    np.ndarray
        Distance from the first station as a fraction of the total, 0 to 1 [-].

    Raises:
    -------
    InvalidInputError
        If the two arrays disagree in length, or the wall has no length.

    '''

    axialPosition = np.asarray(axialPosition, dtype = float)
    radius        = np.asarray(radius, dtype = float)

    if axialPosition.shape != radius.shape or axialPosition.ndim != 1 or axialPosition.size < 2:
        raise InvalidInputError(
            message = 'The jacket fraction is built from the wall the jacket sits on, which has '
                      'to be two matching runs of at least two coordinates.',
            parameterName = 'axialPosition',
            value = (np.shape(axialPosition), np.shape(radius)),
            validRange = 'Two one-dimensional arrays of the same length, at least 2 long [m]')

    meridional = np.insert(np.cumsum(np.hypot(np.diff(axialPosition), np.diff(radius))), 0, 0.0)

    if meridional[-1] <= 0.0:
        raise InvalidInputError(
            message = 'The wall the jacket sits on has no meridional length, so there is no '
                      'fraction along it to key a profile on.',
            parameterName = 'axialPosition',
            value = float(meridional[-1]),
            validRange = 'Total meridional length greater than zero [m]')

    return meridional/meridional[-1]

def stationKeys(keyName: str, axialPosition, radius) -> np.ndarray:

    '''

    The profile key at every station, for the key the configuration named.

    Parameters:
    -----------
    keyName : str
        One of PROFILEKEYS.
    axialPosition, radius : array-like
        Wall coordinates at each station, in nozzle order [m].

    Returns:
    --------
    np.ndarray
        Key value at each station.

    Raises:
    -------
    InvalidInputError
        If the key is not one this module builds.

    '''

    if keyName == 'areaRatio':
        return signedAreaRatio(radius)

    if keyName == 'jacketFraction':
        return jacketFraction(axialPosition, radius)

    raise InvalidInputError(
        message = f"A channel profile is keyed on {' or '.join(PROFILEKEYS)}.",
        parameterName = 'manualChannelProfileKey',
        value = keyName,
        validRange = 'One of ' + ', '.join(repr(key) for key in PROFILEKEYS))

def readProfile(profile, keyName: str = 'areaRatio', channelType: str = None) -> ChannelProfile:

    '''

    A channel profile from whatever the configuration carried.

    Four forms are read. A number is a constant half-extent. A list of pairs is the control
    points, in the key the configuration named. A string that starts with a bracket is that same
    list written as text, which is the form a text entry field can carry. Any other string is a
    path to a recorded profile document, whose own key and channel family win over the ones
    passed here, because a recording replays as itself.

    Parameters:
    -----------
    profile : float | Sequence | str
        The configuration entry.
    keyName : str
        Key the points are in, where the profile does not name its own.
    channelType : str
        Channel family the jacket is being built in, checked against a recorded profile's own.

    Returns:
    --------
    ChannelProfile

    Raises:
    -------
    InvalidInputError
        If the entry is not one of the four forms, if a point is not a finite key and a
        positive half-extent, if the keys are not strictly increasing, or if a recorded profile
        was taken for a different channel family.

    '''

    source        = None
    documentKey   = None
    documentType  = None

    if isinstance(profile, str) and profile.strip().startswith(('[', '(')):
        # The control points written as text, which is what a text entry field hands over.
        try:
            points = json.loads(profile.strip().replace('(', '[').replace(')', ']'))
        except ValueError as failure:
            raise InvalidInputError(
                message = f'The channel profile {profile!r} does not read as a list of '
                          f'[key, half-extent] pairs: {failure}.',
                parameterName = 'manualChannelProfile',
                value = profile,
                validRange = 'A list of [key, half-extent] pairs [m]') from failure
    elif isinstance(profile, str) and _asNumber(profile) is not None:
        # A constant channel written as text, from the same entry field.
        points = _asNumber(profile)
    elif isinstance(profile, str):
        source = profile
        document = _readProfileDocument(profile)
        points       = document.get('points')
        documentKey  = document.get('key')
        documentType = document.get('channelType')
    else:
        points = profile

    if documentKey is not None:
        if documentKey not in PROFILEKEYS:
            raise InvalidInputError(
                message = f'The profile recorded in {source} is keyed on {documentKey!r}, which '
                          f'is not a key this package builds.',
                parameterName = 'key',
                value = documentKey,
                validRange = 'One of ' + ', '.join(repr(key) for key in PROFILEKEYS))
        keyName = documentKey

    if documentType is not None and channelType is not None and documentType != channelType:
        raise InvalidInputError(
            message = f'The profile recorded in {source} sizes a {documentType} channel and the '
                      f'jacket is being built with {channelType} channels. The half-extent means '
                      f'a different section in each, so the recording does not carry over.',
            parameterName = 'channelType',
            value = channelType,
            validRange = f'{documentType!r}, to match the recorded profile')

    if keyName not in PROFILEKEYS:
        raise InvalidInputError(
            message = f"A channel profile is keyed on {' or '.join(PROFILEKEYS)}.",
            parameterName = 'manualChannelProfileKey',
            value = keyName,
            validRange = 'One of ' + ', '.join(repr(key) for key in PROFILEKEYS))

    return ChannelProfile(points = _readPoints(points, source), keyName = keyName,
                          channelType = documentType or channelType, source = source)

def _asNumber(text: str):

    '''The number a string holds, or None where it holds something else.'''

    try:
        return float(text)
    except ValueError:
        return None

def _readProfileDocument(path: str) -> dict:

    '''

    A recorded profile document from the path a configuration named.

    The path is used as given when it is absolute, and otherwise resolved against the working
    directory, which is where a run writes its output folder.

    '''

    resolved = path if os.path.isabs(path) else os.path.abspath(path)

    if not os.path.isfile(resolved):
        raise InvalidInputError(
            message = f'No channel profile at {resolved}. A run writes one into its output '
                      f'folder as <name>ChannelProfile.json when export is on.',
            parameterName = 'manualChannelProfile',
            value = path,
            validRange = 'Path to a profile document, absolute or relative to the working directory')

    with io.open(resolved, encoding = 'utf-8') as handle:
        document = json.load(handle)

    if not isinstance(document, dict) or 'points' not in document:
        raise InvalidInputError(
            message = f'The file at {resolved} is not a channel profile document. One carries '
                      f'its control points under "points", and the key they are in under "key".',
            parameterName = 'manualChannelProfile',
            value = path,
            validRange = 'A JSON object with a "points" entry')

    return document

def _readPoints(points, source: str = None) -> np.ndarray:

    '''

    Control points as an (N, 2) array, from a number or a list of pairs.

    '''

    where = f' recorded in {source}' if source else ''

    if isinstance(points, (int, float, np.integer, np.floating)) and not isinstance(points, bool):
        # A constant channel is the one-point case, and the key it sits at does not matter.
        points = [[0.0, float(points)]]

    try:
        table = np.asarray(points, dtype = float)
    except (TypeError, ValueError):
        table = np.zeros(0)

    if table.ndim == 1 and table.size == 2:
        table = table.reshape(1, 2)

    if table.ndim != 2 or table.shape[0] < 1 or table.shape[1] != 2:
        raise InvalidInputError(
            message = f'A channel profile{where} is a half-extent [m], or a list of [key, '
                      f'half-extent] pairs.',
            parameterName = 'manualChannelProfile',
            value = np.shape(table),
            validRange = 'A number, or an (N, 2) list of [key, half-extent] pairs [m]')

    if not np.all(np.isfinite(table)):
        raise InvalidInputError(
            message = f'Every key and half-extent in a channel profile{where} has to be a finite '
                      f'number.',
            parameterName = 'manualChannelProfile',
            value = table.tolist(),
            validRange = 'All entries finite')

    if np.any(table[:, 1] <= 0.0):
        raise InvalidInputError(
            message = f'A channel profile{where} gives the section\'s radial half-extent, which '
                      f'is a positive length in meters.',
            parameterName = 'manualChannelProfile',
            value = table[:, 1].tolist(),
            validRange = 'Every half-extent greater than zero [m]')

    if table.shape[0] > 1 and np.any(np.diff(table[:, 0]) <= 0.0):
        raise InvalidInputError(
            message = f'The control points of a channel profile{where} have to run in strictly '
                      f'increasing order of their key, so that the interpolation between them is '
                      f'single valued.',
            parameterName = 'manualChannelProfile',
            value = table[:, 0].tolist(),
            validRange = 'Strictly increasing keys')

    return table

def evaluateProfile(profile: ChannelProfile, keys) -> np.ndarray:

    '''

    The half-extent the profile asks for at every station.

    Linear in the key between control points, and flat at the nearest point outside the range
    they cover, so a profile written about the throat holds its end values out to the ends of
    the jacket rather than extrapolating to somewhere unintended.

    Parameters:
    -----------
    profile : ChannelProfile
    keys : array-like
        Profile key at each station, from stationKeys.

    Returns:
    --------
    np.ndarray
        Radial half-extent at each station [m].

    '''

    return np.interp(np.asarray(keys, dtype = float), profile.points[:, 0], profile.points[:, 1])

def profileDocument(channelType: str, keyName: str, keys, halfExtents, notes: dict = None) -> dict:

    '''

    A recorded profile, as the document a later run replays.

    Parameters:
    -----------
    channelType : str
        Channel family the half-extents size.
    keyName : str
        One of PROFILEKEYS, naming the coordinate the keys are in.
    keys, halfExtents : array-like
        One value each per station, in nozzle order.
    notes : dict
        Anything else worth carrying beside the profile, such as the channel count and the wall
        temperature limit it was sized against. Recorded for the reader; nothing reads it back.

    Returns:
    --------
    dict

    Raises:
    -------
    InvalidInputError
        If the keys and half-extents do not pass the reader's own checks.

    '''

    keys        = np.asarray(keys, dtype = float)
    halfExtents = np.asarray(halfExtents, dtype = float)

    if keys.shape != halfExtents.shape:
        raise InvalidInputError(
            message = 'A recorded profile carries one key and one half-extent per station.',
            parameterName = 'halfExtents',
            value = (np.shape(keys), np.shape(halfExtents)),
            validRange = 'Two arrays of the same length')

    # Checked by the same reader that will replay it, so a profile that cannot be read back is
    # caught where it is written rather than in the run that tries to use it.
    points = _readPoints(np.column_stack([keys, halfExtents]), source = 'the jacket just built')

    document = {
        'channelType': channelType,
        'key':         keyName,
        'points':      [[float(key), float(value)] for key, value in points],
    }

    if notes:
        document['notes'] = notes

    return document

def profileConfigurationBlock(document: dict) -> str:

    '''

    The recorded profile as the configuration entries that replay it.

    Written on one line per entry so it can be pasted into a .json configuration as it stands.
    Every number is written at full precision, so a pasted profile builds the same jacket the
    recording came from.

    Parameters:
    -----------
    document : dict
        A profileDocument.

    Returns:
    --------
    str

    '''

    points = json.dumps(document['points'], separators = (', ', ': '))

    return (f'"channelSizingMode": "manual",\n'
            f'"manualChannelProfileKey": "{document["key"]}",\n'
            f'"manualChannelProfile": {points}')
