
class VerboseMessage(object):

    (ERR, WARN, INFO, DEBUG, DEBUG2) = range(5)
    CONST = ERR
    v_level = WARN

    def __init__(self):
        pass

    @staticmethod
    def msg(*arg):
        if len(arg) > 1:
            if VerboseMessage.v_level >= arg[0]:
                print(arg[1:])

    @staticmethod
    def set(level):
        VerboseMessage.v_level = level