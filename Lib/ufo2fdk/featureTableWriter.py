try:
    set
except NameError:
    from sets import Set as set


class FeatureTableWriter(object):

    """
    A very simple feature file syntax table writer.
    """

    def __init__(self, name, indentation="    "):
        self._name = name
        self._lineSep = "\n"
        self._indentation = indentation
        self._lines = ["table %s {" % name]

    def addLineWithKeyValue(self, key, value):
        """
        Adds a line with form::

            key value;
        """
        line = "%s %s;" % (key, str(value))
        self.addLine(line)

    def addLine(self, line):
        """
        Adds a raw line.
        """
        line = self._indentation + line
        self._lines.append(line)

    def write(self):
        """
        Returns the text of the table.
        """
        lines = self._lines + ["} %s;" % self._name]
        return self._lineSep.join(lines)


# --------------
# Text Utilities
# --------------

# The comments were taken from the feature file syntax spec.

def winCharEncode(char):
    exceptions = set("\\\"\t\n\r")
    # Strings are converted to Unicode for the Windows platform
    # by adding a high byte of 0. 2-byte Unicode values for the
    # Windows platform may be specified using a special character
    # sequence of a backslash character (\) followed by exactly
    # four hexadecimal numbers (of either case) which may not all
    # be zero, e.g. \4e2d.
    # The ASCII backslash character must be represented as the
    # sequence \005c or \005C and the ASCII double quote character
    # must be represented as the sequence \0022.
    value = ord(char)
    if value > 128 or char in exceptions:
        v = hex(value)[2:].upper()
        v = "0" * (4 - len(v)) + v
        return "\\" + v
    return char

def macCharEncode(char):
    exceptions = set("\\\"\t\n\r")
    # character codes in the range 128-255 may be specified
    # using a special character sequence of a backslash
    # character (\) followed by exactly two hexadecimal numbers
    # (of either case) which may not both be zero, e.g. \83.
    # The ASCII blackslash character must be represented as the
    # sequence \5c or \5C and the ASCII double quote character
    # must be represented as the sequence \22.
    try:
        value = ord(char.encode("macroman"))
        if (128 < value and value < 256) or char in exceptions:
            v = hex(value)[2:].upper()
            v = "0" * (2 - len(v)) + v
            return "\\" + v
    except UnicodeEncodeError:
        pass
    value = ord(char)
    if value >= 256:
        v = hex(value)[2:].upper()
        v = "0" * (4 - len(v)) + v
        return "\\" + v
    return char

def winStr(text):
    """
    Convert string to FDK encoding for Windows.
    """
    return str("".join([winCharEncode(c) for c in unicode(text)]))

def macStr(text):
    """
    Convert string to FDK encoding for Mac.
    """
    return str("".join([macCharEncode(c) for c in unicode(text)]))
