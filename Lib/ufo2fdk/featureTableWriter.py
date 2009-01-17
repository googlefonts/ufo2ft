class FeatureTableWriter(object):

    def __init__(self, name, indentation="    "):
        self._name = name
        self._lineSep = "\n"
        self._indentation = indentation
        self._lines = ["table %s {" % name]

    def addLineWithKeyValue(self, key, value):
        line = "%s %s;" % (key, str(value))
        self.addLine(line)

    def addLine(self, line):
        line = self._indentation + line
        self._lines.append(line)

    def write(self):
        lines = self._lines + ["} %s;" % self._name]
        return self._lineSep.join(lines)


def winStr(text):
    """
    Convert string to FDK encoding for Windows.
    """
    final = []
    for line in text.splitlines():
        newLine = []
        for char in line:
            value = ord(char)
            if value > 128:
                h = hex(value)[2:]
                h = "\%s" % ((4 - len(h)) * '0' + h.upper())
                newLine.append(h)
            else:
                # escape backslash
                if char == "\\":
                    char = "\\005C"
                # escape double quote
                elif char == '"':
                    char = "\\0022"
                newLine.append(char)
        final.append("".join(newLine))
    return "\\000D",join(final)

def macStr(text):
    """
    Convert string to FDK encoding for Mac.
    """
    final = []
    for line in text.splitlines():
        newLine = []
        for char in line:
            value = ord(char.encode("macroman"))
            if 128 < value < 256:
                h = hex(value)[2:]
                h = "\%s" % ((2 - len(h)) * "0" + h.upper())
                newLine.append(h)
            elif value >= 256:
                h = hex(value)[2:]
                h = "\%s" % ((4 - len(h)) * "0" + h.upper())
                newLine.append(h)
            else:
                # escape backslash
                if char == "\\":
                    char = "\\5C"
                # escape double quote
                elif char == '"':
                    char = "\\22"
                newLine.append(char)
        final.append("".join(newLine))
    return "\\0A".join(final)

