from __future__ import print_function, division, absolute_import, unicode_literals


# UFO3 kerning class prefixes
UFO3_PREFIX_1 = "public.kern1."
UFO3_PREFIX_2 = "public.kern2."
UFO3_PREFIX_LENGTH = len(UFO3_PREFIX_1)
# Metrics Machine prefixes
MMK_PREFIX_L = "@MMK_L_"
MMK_PREFIX_R = "@MMK_R_"
# common kerning class suffixes
SUFFIX_L = ("_1ST", "_L", "_LEFT")
SUFFIX_R = ("_2ND", "_R", "_RIGHT")
# common kerning class prefixes
ANY_KERN_PREFIX = (("@_",) + (MMK_PREFIX_L, MMK_PREFIX_R) +
                   (UFO3_PREFIX_1, UFO3_PREFIX_2))


# class KernFeatureWriter(AbstractFeatureWriter):
class KernFeatureWriter(object):
    """Generates a kerning feature based on groups definitions and kerning
    rules contained in font.
    """

    def __init__(self, font):
        # build dict of kerning groups from font.groups
        self.kerningGroups = {}
        for key, members in sorted(font.groups.items()):
            if not key.startswith(ANY_KERN_PREFIX):
                continue
            key = self._makeFeaClassName(key)
            self.kerningGroups[key] = members

        # build dicts of kerning pairs from font.kerning
        self.glyphPairKerning = {}
        self.leftClassKerning = {}
        self.rightClassKerning = {}
        self.classPairKerning = {}
        for (left, right), val in sorted(font.kerning.items()):
            leftIsClass = left.startswith(ANY_KERN_PREFIX)
            rightIsClass = right.startswith(ANY_KERN_PREFIX)

            if leftIsClass:
                left = self._makeFeaClassName(left)

            if rightIsClass:
                right = self._makeFeaClassName(right)

            if leftIsClass:
                if rightIsClass:
                    self.classPairKerning[left, right] = val
                else:
                    self.leftClassKerning[left, right] = val
            elif rightIsClass:
                self.rightClassKerning[left, right] = val
            else:
                self.glyphPairKerning[left, right] = val

    def _addGlyphClasses(self, lines):
        """Add glyph classes for the input font's groups."""

        for key, members in sorted(self.kerningGroups.items()):
            lines.append("    %s = [%s];" % (key, " ".join(members)))

    def _addKerning(self, lines, kerning, enum=False):
        """Add kerning rules for a mapping of pairs to values."""

        enum = "enum " if enum else ""
        for (left, right), val in sorted(kerning.items()):
            lines.append("    %spos %s %s %d;" % (enum, left, right, val))

    def write(self, linesep="\n"):
        """Write kern feature."""

        if not any([self.glyphPairKerning, self.leftClassKerning,
                    self.rightClassKerning, self.classPairKerning]):
            # no kerning pairs, return empty
            return ""

        lines = []
        lines.append("feature kern {")
        self._addGlyphClasses(lines)
        lines.append("")
        self._addKerning(lines, self.glyphPairKerning)
        if self.leftClassKerning:
            lines.append("")
            self._addKerning(lines, self.leftClassKerning, enum=True)
        if self.rightClassKerning:
            lines.append("")
            self._addKerning(lines, self.rightClassKerning, enum=True)
        if self.classPairKerning:
            lines.append("")
            self._addKerning(lines, self.classPairKerning)
        lines.append("} kern;")

        return linesep.join(lines)

    @staticmethod
    def _makeFeaClassName(name):
        """ Strip 'public.kern1.', 'public.kern2.' prefixes and add '@' if
        not already there.
        """
        if name.startswith((UFO3_PREFIX_1, UFO3_PREFIX_2)):
            name = name[UFO3_PREFIX_LENGTH:]
        if not name.startswith("@"):
            name = "@" + name
        return name
