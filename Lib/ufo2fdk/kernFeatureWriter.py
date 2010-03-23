try:
    set
except NameError:
    from sets import Set as set

try:
    sorted
except NameError:
    def sorted(l):
        l = list(l)
        l.sort()
        return l

inlineGroupInstance = (list, tuple, set)


class KernFeatureWriter(object):

    """
    This object will create a kerning feature in FDK
    syntax using the kerning in the given font. The
    only external method is :meth:`ufo2fdk.tools.kernFeatureWriter.write`.

    This object does what it can to create the best possible
    kerning feature, but because it doesn't know anything
    about how the raw kerning data was created, it has
    to make some educated guesses about a few things. This
    happens with regards to finding kerning groups that
    are not referenced by any kerning pairs. This is only an
    issue when attempting to decompose certain types of
    exception pairs. The default implementation of this object
    finds unreferenced groups in the ``getUnreferencedGroups``.
    These groups will be studied when attempting to decompose
    these special exceptions. This is as accurate as it can be,
    but it is not foolproof. Passing a groupNamePrefix that
    defines a prefix that all referenced kerning groups will
    start with. If this is known, it will help remove the
    ambiguities described above.
    """

    def __init__(self, font, groupNamePrefix=""):
        self.font = font
        self.groupNamePrefix = groupNamePrefix
        self.leftGroups, self.rightGroups = self.getReferencedGroups()
        self.leftUnreferencedGroups, self.rightUnreferencedGroups = self.getUnreferencedGroups()
        self.pairs = self.getPairs()
        self.flatLeftGroups, self.flatRightGroups, self.flatLeftUnreferencedGroups, self.flatRightUnreferencedGroups = self.getFlatGroups()

    def write(self, headerText=None):
        """
        Write the feature text. If *headerText* is provided
        it will inserted after the ``feature kern {`` line.
        """
        if not self.pairs:
            return ""
        glyphGlyph, glyphGroupDecomposed, groupGlyphDecomposed, glyphGroup, groupGlyph, groupGroup = self.getSeparatedPairs(self.pairs)
        # write the classes
        groups = dict(self.leftGroups)
        groups.update(self.rightGroups)
        for groupName, glyphList in groups.items():
            if not glyphList:
                del groups[groupName]
        classes = self.getClassDefinitionsForGroups(groups)
        # write the kerning rules
        rules = []
        order = [
            ("# glyph, glyph", glyphGlyph),
            ("# glyph, group exceptions", glyphGroupDecomposed),
            ("# group exceptions, glyph", groupGlyphDecomposed),
            ("# glyph, group", glyphGroup),
            ("# group, glyph", groupGlyph),
            ("# group, group", groupGroup),
        ]
        for note, pairs in order:
            if pairs:
                rules.append("")
                rules.append(note)
                rules += self.getFeatureRulesForPairs(pairs)
        # compile
        feature = ["feature kern {"]
        if headerText:
            for line in headerText.splitlines():
                line = line.strip()
                if not line.startswith("#"):
                    line = "# " + line
                line = "    " + line
                feature.append(line)
        for line in classes + rules:
            if line:
                line = "    " + line
            feature.append(line)
        feature.append("} kern;")
        # done
        return u"\n".join(feature)

    # -------------
    # Initial Setup
    # -------------

    def getReferencedGroups(self):
        """
        Get two dictionaries representing groups
        referenced on the left and right of pairs.
        You should not call this method directly.
        """
        leftReferencedGroups = set()
        rightReferencedGroups = set()
        groups = self.font.groups
        for left, right in self.font.kerning.keys():
            if left.startswith(self.groupNamePrefix) and left in groups:
                leftReferencedGroups.add(left)
            if right.startswith(self.groupNamePrefix) and right in groups:
                rightReferencedGroups.add(right)
        leftGroups = {}
        for groupName in leftReferencedGroups:
            glyphList = [glyphName for glyphName in groups[groupName] if glyphName in self.font]
            glyphList = set(glyphList)
            if not groupName.startswith("@"):
                groupName = "@" + groupName
            leftGroups[groupName] = glyphList
        rightGroups = {}
        for groupName in rightReferencedGroups:
            glyphList = [glyphName for glyphName in groups[groupName] if glyphName in self.font]
            glyphList = set(glyphList)
            if not groupName.startswith("@"):
                groupName = "@" + groupName
            rightGroups[groupName] = glyphList
        return leftGroups, rightGroups

    def getUnreferencedGroups(self):
        """
        Get a dictionary representing kerning groups
        that are not referenced in any kerning pairs.
        You should not call this method directly.
        """
        # gather all glyphs that are already referenced
        leftReferencedGlyphs = []
        for glyphList in self.leftGroups.values():
            leftReferencedGlyphs += glyphList
        leftReferencedGlyphs = set(leftReferencedGlyphs)
        rightReferencedGlyphs = []
        for glyphList in self.rightGroups.values():
            rightReferencedGlyphs += glyphList
        rightReferencedGlyphs = set(rightReferencedGlyphs)
        # find unreferenced groups
        unreferencedLeftGroups = {}
        unreferencedRightGroups = {}
        for groupName, glyphList in sorted(self.font.groups.items()):
            if not groupName.startswith("@") or not groupName.startswith(self.groupNamePrefix):
                continue
            if groupName in self.leftGroups:
                continue
            if groupName in self.rightGroups:
                continue
            glyphList = set(glyphList)
            if not leftReferencedGlyphs & glyphList:
                unreferencedLeftGroups[groupName] = glyphList
                leftReferencedGlyphs = leftReferencedGlyphs | glyphList
            if not rightReferencedGlyphs & glyphList:
                unreferencedRightGroups[groupName] = glyphList
                rightReferencedGlyphs = rightReferencedGlyphs | glyphList
        return unreferencedLeftGroups, unreferencedRightGroups

    def getPairs(self):
        """
        Get a dictionary containing all kerning pairs.
        This should filter out pairs containing empty groups
        and groups/glyphs that are not in the font.
        You should not call this method directly.
        """
        pairs = {}
        for (left, right), value in self.font.kerning.items():
            # skip missing glyphs
            if left not in self.font.groups and left not in self.font:
                continue
            if right not in self.font.groups and right not in self.font:
                continue
            # skip empty groups
            if left.startswith(self.groupNamePrefix) and left in self.font.groups and not self.font.groups[left]:
                continue
            if right.startswith(self.groupNamePrefix) and right in self.font.groups and not self.font.groups[right]:
                continue
            # store pair
            if left.startswith(self.groupNamePrefix) and left in self.font.groups:
                if not left.startswith("@"):
                    left = "@" + left
            if right.startswith(self.groupNamePrefix) and right in self.font.groups:
                if not right.startswith("@"):
                    right = "@" + right
            pairs[left, right] = value
        return pairs

    def getFlatGroups(self):
        """
        Get three dictionaries keyed by glyph names with
        group names as values for left, right and
        unreferenced groups. You should not call this
        method directly.
        """
        flatLeftGroups = {}
        flatRightGroups = {}
        for groupName, glyphList in self.leftGroups.items():
            for glyphName in glyphList:
                # user has glyph in more than one group.
                # this is not allowed.
                if glyphName in flatLeftGroups:
                    continue
                flatLeftGroups[glyphName] = groupName
        for groupName, glyphList in self.rightGroups.items():
            for glyphName in glyphList:
                # user has glyph in more than one group.
                # this is not allowed.
                if glyphName in flatRightGroups:
                    continue
                flatRightGroups[glyphName] = groupName
        flatLeftUnreferencedGroups = {}
        for groupName, glyphList in self.leftUnreferencedGroups.items():
            for glyphName in glyphList:
                flatLeftUnreferencedGroups[glyphName] = groupName
        flatRightUnreferencedGroups = {}
        for groupName, glyphList in self.rightUnreferencedGroups.items():
            for glyphName in glyphList:
                flatRightUnreferencedGroups[glyphName] = groupName
        return flatLeftGroups, flatRightGroups, flatLeftUnreferencedGroups, flatRightUnreferencedGroups

    # ------------
    # Pair Support
    # ------------

    def isHigherLevelPairPossible(self, (left, right)):
        """
        Determine if there is a higher level pair possible.
        This doesn't indicate that the pair exists, it simply
        indicates that something higher than (left, right)
        can exist.
        You should not call this method directly.
        """
        leftInUnreferenced = False
        rightInUnreferenced = False
        if left.startswith("@"):
            leftGroup = left
            leftGlyph = None
        else:
            leftGroup = self.flatLeftGroups.get(left)
            leftGlyph = left
            if leftGroup is None and left in self.flatLeftUnreferencedGroups:
                leftInUnreferenced= True
        if right.startswith("@"):
            rightGroup = right
            rightGlyph = None
        else:
            rightGroup = self.flatRightGroups.get(right)
            rightGlyph = right
            if rightGroup is None and right in self.flatRightUnreferencedGroups:
                rightInUnreferenced = True

        havePotentialHigherLevelPair = False
        if left.startswith("@") and right.startswith("@"):
            pass
        elif left.startswith("@"):
            if rightGroup is not None or rightInUnreferenced:
                if (left, right) in self.pairs:
                    havePotentialHigherLevelPair = True
        elif right.startswith("@"):
            if leftGroup is not None or leftInUnreferenced:
                if (left, right) in self.pairs:
                    havePotentialHigherLevelPair = True
        else:
            if leftGroup is not None and rightGroup is not None:
                if (leftGlyph, rightGlyph) in self.pairs:
                    havePotentialHigherLevelPair = True
                elif (leftGroup, rightGlyph) in self.pairs:
                    havePotentialHigherLevelPair = True
                elif (leftGlyph, rightGroup) in self.pairs:
                    havePotentialHigherLevelPair = True
            elif leftGroup is not None:
                if (leftGlyph, rightGlyph) in self.pairs:
                    havePotentialHigherLevelPair = True
            elif rightGroup is not None:
                if (leftGlyph, rightGlyph) in self.pairs:
                    havePotentialHigherLevelPair = True
        return havePotentialHigherLevelPair

    def getSeparatedPairs(self, pairs):
        """
        Organize *pair* into the following groups:

        * glyph, glyph
        * glyph, group (decomposed)
        * group, glyph (decomposed)
        * glyph, group
        * group, glyph
        * group, group

        You should not call this method directly.
        """
        ## seperate pairs
        glyphGlyph = {}
        glyphGroup = {}
        glyphGroupDecomposed = {}
        groupGlyph = {}
        groupGlyphDecomposed = {}
        groupGroup = {}
        for (left, right), value in pairs.items():
            if left.startswith("@") and right.startswith("@"):
                groupGroup[left, right] = value
            elif left.startswith("@"):
                groupGlyph[left, right] = value
            elif right.startswith("@"):
                glyphGroup[left, right] = value
            else:
                glyphGlyph[left, right] = value
        ## handle decomposition
        allGlyphGlyph = set(glyphGlyph.keys())
        # glyph to group
        for (left, right), value in glyphGroup.items():
            if self.isHigherLevelPairPossible((left, right)):
                finalRight = tuple([r for r in sorted(self.rightGroups[right]) if (left, r) not in allGlyphGlyph])
                for r in finalRight:
                    allGlyphGlyph.add((left, r))
                glyphGroupDecomposed[left, finalRight] = value
                del glyphGroup[left, right]
        # group to glyph
        for (left, right), value in groupGlyph.items():
            if self.isHigherLevelPairPossible((left, right)):
                finalLeft = tuple([l for l in sorted(self.leftGroups[left]) if (l, right) not in glyphGlyph and (l, right) not in allGlyphGlyph])
                for l in finalLeft:
                    allGlyphGlyph.add((l, right))
                groupGlyphDecomposed[finalLeft, right] = value
                del groupGlyph[left, right]
        ## return the result
        return glyphGlyph, glyphGroupDecomposed, groupGlyphDecomposed, glyphGroup, groupGlyph, groupGroup

    # -------------
    # Write Support
    # -------------

    def getClassDefinitionsForGroups(self, groups):
        """
        Write class definitions to a list of strings.
        You should not call this method directly.
        """
        classes = []
        for groupName in sorted(groups.keys()):
            group = groups[groupName]
            l = "%s = [%s];" % (groupName, " ".join(sorted(group)))
            classes.append(l)
        return classes

    def getFeatureRulesForPairs(self, pairs):
        """
        Write pair rules to a list of strings.
        You should not call this method directly.
        """
        rules = []
        for (left, right), value in sorted(pairs.items()):
            if not left or not right:
                continue
            if isinstance(left, inlineGroupInstance) or isinstance(right, inlineGroupInstance):
                line = "enum pos %s %s %d;"
            else:
                line = "pos %s %s %d;"
            if isinstance(left, inlineGroupInstance):
                left = "[%s]" % " ".join(sorted(left))
            if isinstance(right, inlineGroupInstance):
                right = "[%s]" % " ".join(sorted(right))
            rules.append(line % (left, right, value))
        return rules


# ----
# Test
# ----


def _test():
    """
    >>> from fontTools.agl import AGL2UV
    >>> from defcon import Font
    >>> font = Font()
    >>> for glyphName in AGL2UV:
    ...     font.newGlyph(glyphName)
    >>> kerning = {
    ...     # various pair types
    ...     ("Agrave", "Agrave") : -100,
    ...     ("@LEFT_A", "Agrave") : -75,
    ...     ("@LEFT_A", "Aacute") : -74,
    ...     ("eight", "@RIGHT_B") : -49,
    ...     ("@LEFT_A", "@RIGHT_A") : -25,
    ...     ("@LEFT_D", "X") : -25,
    ...     ("X", "@RIGHT_D") : -25,
    ...     # empty groups
    ...     ("@LEFT_C", "@RIGHT_C") : 25,
    ...     ("C", "@RIGHT_C") : 25,
    ...     ("@LEFT_C", "C") : 25,
    ...     # nonexistant glyphs
    ...     ("NotInFont", "NotInFont") : 25,
    ...     # nonexistant groups
    ...     ("@LEFT_NotInFont", "@RIGHT_NotInFont") : 25,
    ... }
    >>> groups = {
    ...     "@LEFT_A" : ["A", "Aacute", "Agrave"],
    ...     "@RIGHT_A" : ["A", "Aacute", "Agrave"],
    ...     "@LEFT_B" : ["B", "eight"],
    ...     "@RIGHT_B" : ["B", "eight"],
    ...     "@LEFT_C" : [],
    ...     "@RIGHT_C" : [],
    ...     "@LEFT_D" : ["D"],
    ...     "@RIGHT_D" : ["D"],
    ... }
    >>> font.groups.update(groups)
    >>> font.kerning.update(kerning)

    >>> writer = KernFeatureWriter(font)
    >>> text = writer.write()
    >>> t1 = [line.strip() for line in text.strip().splitlines()]
    >>> t2 = [line.strip() for line in _expectedFeatureText.strip().splitlines()]
    >>> t1 == t2
    True
    """

_expectedFeatureText = """
feature kern {
    @LEFT_A = [A Aacute Agrave];
    @LEFT_D = [D];
    @RIGHT_A = [A Aacute Agrave];
    @RIGHT_B = [B eight];
    @RIGHT_D = [D];

    # glyph, glyph
    pos Agrave Agrave -100;

    # glyph, group exceptions
    enum pos eight [B eight] -49;

    # group exceptions, glyph
    enum pos [A Aacute] Agrave -75;
    enum pos [A Aacute Agrave] Aacute -74;

    # glyph, group
    pos X @RIGHT_D -25;

    # group, glyph
    pos @LEFT_D X -25;

    # group, group
    pos @LEFT_A @RIGHT_A -25;
} kern;
"""

if __name__ == "__main__":
    import doctest
    doctest.testmod()
