
class VerboseMessage(object):
    """Centralized logging helper that gates console output by verbosity level."""

    (ERR, WARN, INFO, DEBUG, DEBUG2) = range(5)
    CONST = ERR
    v_level = WARN

    def __init__(self):
        """Create a verbosity helper instance.

        Input:
            None.
        Output:
            None. The class mainly uses static methods and shared level state.
        """
        pass

    @staticmethod
    def msg(*arg):
        """Print a message tuple when the current verbosity level allows it.

        Input:
            *arg: First value is the message level, remaining values are the message body.
        Output:
            None. Prints to stdout when the message level is enabled.
        """
        if len(arg) > 1:
            if VerboseMessage.v_level >= arg[0]:
                print(arg[1:])

    @staticmethod
    def set(level):
        """Update the global verbosity level used by msg.

        Input:
            level: Integer verbosity threshold.
        Output:
            None. Updates class-level state.
        """
        VerboseMessage.v_level = level