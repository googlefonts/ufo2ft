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


def winStr(s):
    """
    Convert string to FDK encoding for windows
    """
    t = []
    for c in s:
        v = ord(c)
        if v > 128:
            h = hex(v)[2:]
            h = "\%s" % ((4 - len(h)) * '0' + h.upper())
            t.append(h)
        else:
            # escape backslash
            if c == "\\":
                c = "\\005C"
            # escape double quote
            if c == '"':
                c = "\\0022"
            t.append(c)
    return "".join(t)

def macStr(s):
    """
    Convert string to FDK encoding for mac.
    """
    t = []
    for c in s:
        v = ord(c.encode("macroman"))
        if 128 < v < 256:
            h = hex(v)[2:]
            h = "\%s" % ((2 - len(h)) * '0' + h.upper())
            t.append(h)
        elif v >= 256:
            h = hex(v)[2:]
            h = "\%s" % ((4 - len(h)) * '0' + h.upper())
            t.append(h)
        else:
            # escape backslash
            if c == "\\":
                c = "\\5C"
            # escape double quote
            if c == '"':
                c = "\\22"
            t.append(c)
    return "".join(t)

