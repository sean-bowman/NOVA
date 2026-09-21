
# -- NOVA: Deliberate Failures -- #

'''

Every failure NOVA raises on purpose is one of these, so a caller can catch the family it cares
about instead of guessing at exception types.

'RegenGeometryError' is the common base. Its subclasses narrow it to why the geometry failed:
a solver did not converge, a constraint could not be met, an input was invalid before any
calculation ran. Catching the base class still catches every one of them.

'createErrorContext' builds the dictionary a raise site attaches to the exception, so the state
at the point of failure survives into the traceback rather than being lost to the stack unwinding
past it.

Author: Sean Bowman

'''

from typing import Dict, Any, Optional

class RegenGeometryError(Exception):

    '''

    Base exception class for regenerative cooling geometry generation errors.

    This is the parent class for all regenerative cooling-related exceptions.
    All custom exceptions inherit from this class to allow for broad exception
    handling when needed.

    Attributes:
        message (str): Human-readable error message
        context (dict): Additional context about the error (station index, variable values, etc.)

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):

        '''

        Initialize the RegenGeometryError exception.

        Args:
            message: Human-readable description of the error
            context: Dictionary containing relevant state information when error occurred

        '''

        self.message = message
        self.context = context if context is not None else {}

        # Build detailed error message
        fullMessage = f'\n{"=" * 80}\n'
        fullMessage += f'REGENERATIVE GEOMETRY ERROR\n'
        fullMessage += f'{"=" * 80}\n'
        fullMessage += f'{message}\n'

        if self.context:
            fullMessage += f'\nError Context:\n'
            fullMessage += f'{"-" * 80}\n'
            for key, value in self.context.items():
                fullMessage += f'  {key}: {value}\n'

        fullMessage += f'{"=" * 80}\n'

        super().__init__(fullMessage)

    def getContext(self) -> Dict[str, Any]:

        '''

        Retrieve the error context dictionary.

        Returns:
            Dictionary containing error context information

        '''

        return self.context

class ConvergenceFailureError(RegenGeometryError):

    '''

    Exception raised when iterative solver fails to converge within iteration limit.

    This error occurs when numerical solvers (temperature convergence, channel radius
    optimization, etc.) cannot find a solution within the maximum allowed iterations.

    Common causes:
        - Incompatible design constraints (conflicting requirements)
        - Poor initial guess leading to oscillation
        - Numerical stiffness in governing equations
        - Step size too large or too small

    Attributes:
        iterations (int): Number of iterations attempted before failure
        tolerance (float): Convergence tolerance that was not met
        residual (float): Final residual/error value

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 iterations: Optional[int] = None, tolerance: Optional[float] = None,
                 residual: Optional[float] = None):

        '''

        Initialize the ConvergenceFailureError exception.

        Args:
            message: Description of the convergence failure
            context: Error context dictionary
            iterations: Number of iterations attempted
            tolerance: Required convergence tolerance
            residual: Final error/residual value

        '''

        if context is None:
            context = {}

        if iterations is not None:
            context['iterations'] = iterations
        if tolerance is not None:
            context['tolerance'] = tolerance
        if residual is not None:
            context['residual'] = residual

        super().__init__(message, context)

class GeometricConstraintError(RegenGeometryError):

    '''

    Exception raised when geometric constraints are violated or impossible to satisfy.

    This error occurs when the requested geometry cannot be physically realized due to
    geometric constraints such as:
        - Channel radius too small (< minimum fabrication limit)
        - Cross-sectional area approaching zero
        - Hydraulic diameter too small for correlation validity
        - Number of channels cannot fit around nozzle circumference
        - Channel path cannot be wrapped without self-intersection

    Attributes:
        constraintType (str): Type of geometric constraint violated
        value (float): Actual value that violated the constraint
        limit (float): Constraint limit that was exceeded

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 constraintType: Optional[str] = None, value: Optional[float] = None,
                 limit: Optional[float] = None):

        '''

        Initialize the GeometricConstraintError exception.

        Args:
            message: Description of the geometric constraint violation
            context: Error context dictionary
            constraintType: Type of constraint (e.g., 'channelRadius', 'CSA', 'hydraulicDiameter')
            value: Actual value that violated constraint
            limit: Constraint boundary value

        '''

        if context is None:
            context = {}

        if constraintType is not None:
            context['constraintType'] = constraintType
        if value is not None:
            context['value'] = value
        if limit is not None:
            context['limit'] = limit

        super().__init__(message, context)

class ThermalConstraintError(RegenGeometryError):

    '''

    Exception raised when thermal constraints cannot be satisfied.

    This error occurs when thermal requirements or limits are violated:
        - Wall temperature exceeds material limit
        - Coolant temperature exceeds decomposition temperature
        - Heat flux exceeds critical heat flux
        - Coolant state calculation failure (RefProp error)
        - Temperature convergence produces physically invalid results

    Attributes:
        thermalProperty (str): Which thermal property violated constraint
        value (float): Actual value of the property
        limit (float): Limit that was exceeded

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 thermalProperty: Optional[str] = None, value: Optional[float] = None,
                 limit: Optional[float] = None):

        '''

        Initialize the ThermalConstraintError exception.

        Args:
            message: Description of the thermal constraint violation
            context: Error context dictionary
            thermalProperty: Property that violated constraint (e.g., 'wallTemperature', 'heatFlux')
            value: Actual value
            limit: Limit value

        '''

        if context is None:
            context = {}

        if thermalProperty is not None:
            context['thermalProperty'] = thermalProperty
        if value is not None:
            context['value'] = value
        if limit is not None:
            context['limit'] = limit

        super().__init__(message, context)

class PressureDropError(RegenGeometryError):

    '''

    Exception raised when pressure drop exceeds allowable limits.

    This error occurs when the coolant pressure drop through the regenerative cooling
    channels exceeds the available pressure margin, or when coolant pressure becomes
    negative or approaches vapor pressure (risk of cavitation/boiling).

    Common causes:
        - Too many channels (high velocity)
        - Channels too small (high friction)
        - Excessive channel length
        - High momentum loss from bends
        - Insufficient inlet pressure

    Attributes:
        pressureDrop (float): Total pressure drop calculated [Pa]
        maxPressureDrop (float): Maximum allowable pressure drop [Pa]
        exitPressure (float): Calculated exit pressure [Pa]
        minExitPressure (float): Minimum required exit pressure [Pa]

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 pressureDrop: Optional[float] = None, maxPressureDrop: Optional[float] = None,
                 exitPressure: Optional[float] = None, minExitPressure: Optional[float] = None):

        '''

        Initialize the PressureDropError exception.

        Args:
            message: Description of the pressure drop error
            context: Error context dictionary
            pressureDrop: Calculated total pressure drop [Pa]
            maxPressureDrop: Maximum allowable pressure drop [Pa]
            exitPressure: Calculated exit pressure [Pa]
            minExitPressure: Minimum required exit pressure [Pa]

        '''

        if context is None:
            context = {}

        if pressureDrop is not None:
            context['pressureDrop'] = pressureDrop
        if maxPressureDrop is not None:
            context['maxPressureDrop'] = maxPressureDrop
        if exitPressure is not None:
            context['exitPressure'] = exitPressure
        if minExitPressure is not None:
            context['minExitPressure'] = minExitPressure

        super().__init__(message, context)

class InvalidInputError(RegenGeometryError):

    '''

    Exception raised when input parameters are invalid or out of acceptable range.

    This error is raised during input validation before expensive calculations begin.
    Catching invalid inputs early prevents wasted computation and provides clear
    feedback about what needs to be corrected.

    Common invalid inputs:
        - Negative values for physical quantities (mass flow, pressure, temperature)
        - Zero or negative channel count
        - Helix angle outside valid range (0°, 90°)
        - Empty or malformed geometry arrays
        - Incompatible parameter combinations

    Attributes:
        parameterName (str): Name of the invalid parameter
        value: Actual value provided
        validRange (str): Description of valid range

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 parameterName: Optional[str] = None, value: Any = None,
                 validRange: Optional[str] = None):

        '''

        Initialize the InvalidInputError exception.

        Args:
            message: Description of the invalid input
            context: Error context dictionary
            parameterName: Name of the parameter that is invalid
            value: The invalid value provided
            validRange: Description of the valid range for this parameter

        '''

        if context is None:
            context = {}

        if parameterName is not None:
            context['parameterName'] = parameterName
        if value is not None:
            context['value'] = value
        if validRange is not None:
            context['validRange'] = validRange

        super().__init__(message, context)

class NumericalInstabilityError(RegenGeometryError):

    '''

    Exception raised when numerical instabilities are detected (NaN, Inf, etc.).

    This error occurs when calculations produce non-finite values (NaN, Inf, -Inf)
    which indicate numerical breakdown. This is typically caused by:
        - Division by zero or near-zero values
        - Domain errors in mathematical functions (sqrt of negative, log of zero)
        - Overflow/underflow in floating point arithmetic
        - Accumulation of rounding errors
        - RefProp calculation failures

    Attributes:
        variableName (str): Name of variable containing non-finite value
        value: The problematic value (NaN, Inf, etc.)
        operation (str): Operation that produced the non-finite value

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 variableName: Optional[str] = None, value: Any = None,
                 operation: Optional[str] = None):

        '''

        Initialize the NumericalInstabilityError exception.

        Args:
            message: Description of the numerical instability
            context: Error context dictionary
            variableName: Name of variable with non-finite value
            value: The non-finite value
            operation: Mathematical operation that caused the issue

        '''

        if context is None:
            context = {}

        if variableName is not None:
            context['variableName'] = variableName
        if value is not None:
            context['value'] = value
        if operation is not None:
            context['operation'] = operation

        super().__init__(message, context)

class VoluteGenerationError(RegenGeometryError):

    '''

    Exception raised when volute (inlet/return manifold) generation fails.

    This error occurs when the Volute class cannot generate valid manifold geometry
    for interfacing the cooling channels with external feedlines. Common causes:
        - Invalid scroll geometry parameters
        - Wall thickness too small for structural requirements
        - Insufficient space for volute routing
        - Temperature/pressure outside material property data range
        - Stress exceeds material allowable stress

    Attributes:
        voluteType (str): Type of volute ('inlet' or 'return')
        failureMode (str): Specific failure mode

    '''

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None,
                 voluteType: Optional[str] = None, failureMode: Optional[str] = None):

        '''

        Initialize the VoluteGenerationError exception.

        Args:
            message: Description of the volute generation failure
            context: Error context dictionary
            voluteType: 'inlet' or 'return'
            failureMode: Specific mode of failure

        '''

        if context is None:
            context = {}

        if voluteType is not None:
            context['voluteType'] = voluteType
        if failureMode is not None:
            context['failureMode'] = failureMode

        super().__init__(message, context)

# Helper function to create error context snapshots
def createErrorContext(stationIndex: Optional[int] = None,
                       iterationCount: Optional[int] = None,
                       **kwargs) -> Dict[str, Any]:

    '''

    Create a standardized error context dictionary.

    This helper function creates a dictionary containing relevant state information
    at the point where an error occurred. This context is attached to exceptions
    to aid in debugging.

    Args:
        stationIndex: Axial station index where error occurred
        iterationCount: Iteration number when error occurred
        **kwargs: Additional key-value pairs to include in context

    Returns:
        Dictionary containing error context information

    Example:
        >>> context = createErrorContext(
        ...     stationIndex=42,
        ...     iterationCount=50,
        ...     channelRadius=0.001,
        ...     wallTemperature=850.0
        ... )

    '''

    context = {}

    if stationIndex is not None:
        context['stationIndex'] = stationIndex

    if iterationCount is not None:
        context['iterationCount'] = iterationCount

    # Add any additional context
    context.update(kwargs)

    return context
