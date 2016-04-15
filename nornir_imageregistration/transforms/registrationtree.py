'''
Created on Nov 14, 2012

@author: u0490822
'''

import operator


class RegistrationTreeNode(object):

    @property
    def IsRoot(self):
        return self.Parent is None

    @property
    def LeafOnly(self):
        '''Return true if this node must stay a leaf'''
        return self._leaf_only

    @property
    def NonLeafOnlyChildren(self):
        '''Child nodes which can have child nodes'''
        output = []
        for c in self.Children:
            if not c.LeafOnly:
                output.append(c)

        return output


    def __init__(self, sectionNumber, leaf_only=False):
        self.Parent = None
        self.SectionNumber = sectionNumber
        self.Children = []
        self._leaf_only = leaf_only

    def SetParent(self, sectionNumber):
        self.Parent = sectionNumber

    def AddChild(self, childSectionNumber):
        self.Children.append(childSectionNumber)
        self.Children.sort(key=operator.attrgetter('SectionNumber'))

    def __str__(self, *args, **kwargs):
        s = str(self.SectionNumber) + " <- "
        for c in self.Children:
            if c.LeafOnly:
                s += '[' + str(c.SectionNumber) + '] '
            else:
                s += str(c.SectionNumber) + ' '

        return s


class RegistrationTree(object):
    '''
    The registration tree tracks which sections are mapped to each other.  When calculating the section to volume transform we begin with the
    root nodes and register down the tree until registration is completed
    '''

    @property
    def SectionNumbers(self):
        '''List of all section numbers contained in tree'''
        return list(self.Nodes.keys())

    @property
    def IsEmpty(self):
        return len(self.Nodes) == 0

    def __init__(self):
        '''
        Constructor
        '''
        self.Nodes = {}  # Dictionary of all nodes
        self.RootNodes = {}  # Dictionary of nodes without parents

    def _GetOrCreateRootNode(self, ControlSection):
        ControlNode = None
        if ControlSection in self.Nodes:
            ControlNode = self.Nodes[ControlSection]
        else:
            ControlNode = RegistrationTreeNode(ControlSection)
            self.Nodes[ControlSection] = ControlNode
            self.RootNodes[ControlSection] = ControlNode

        return ControlNode

    def _GetOrCreateMappedNode(self, MappedSection, leaf_only=False):
        MappedNode = None
        if MappedSection in self.Nodes:
           MappedNode = self.Nodes[MappedSection]
        else:
           MappedNode = RegistrationTreeNode(MappedSection, leaf_only=leaf_only)
           self.Nodes[MappedSection] = MappedNode

        return MappedNode

    def AddPair(self, ControlSection, MappedSection):
        '''
        Maps a section to a control section
        :param int ControlSection: Section to be used as a reference during registration
        :param int MappedSection: Section to be warped during registration
        :rtype: RegistrationTreeNode
        '''

        if ControlSection == MappedSection:
            return

        ControlNode = self._GetOrCreateRootNode(ControlSection)
        MappedNode = self._GetOrCreateMappedNode(MappedSection)

        ControlNode.AddChild(MappedNode)
        # Remove mapped node from the root node
        if MappedSection in self.RootNodes:
            del self.RootNodes[MappedSection]

        return MappedNode

    def AddEmptyRoot(self, ControlSection):
        return self._GetOrCreateRootNode(ControlSection)


#     def NearestNode(self, sectionNumber, excludeLeafOnlyNodes=True):
#         '''Return the node nearest to the requested sectionNumber'''
#
#         if sectionNumber in self.Nodes:
#             return self.Nodes[sectionNumber]

    def FindControlForMapped(self, rtnode, mappedsection, center=None):
        ''' Returns the best control section for the mapped section
            :param RegistrationTreeNode rtnode: Root node to consider insertion on
            :param int sectionnum: Section number to insert
            :param int center: Number of the root for the tree we are searching
        '''
        if center is None:
            center = rtnode.SectionNumber

        direction = mappedsection - center
        children = rtnode.NonLeafOnlyChildren

        if len(children) == 0:
            return rtnode
        else:
            # Registration trees are setup so every child is either greater or less than our nodes value, except on the root node

            if direction < 0:
                # Left insertion
                for leftchild in children:
                    # Edge case, the root may have children greater than our value
                    if(leftchild.SectionNumber > rtnode.SectionNumber):
                        continue

                    if(mappedsection < leftchild.SectionNumber):
                        return self.FindControlForMapped(leftchild, mappedsection, center)

                # Made it this far, so it is smaller than all children and we should insert to ourselves
                return rtnode
            else:
                # Right insertion
                children.reverse()

                for rightchild in children:
                    # Edge case, the root may have children greater than our value
                    if(rightchild.SectionNumber < rtnode.SectionNumber):
                        continue

                    if(mappedsection > rightchild.SectionNumber):
                        return self.FindControlForMapped(rightchild, mappedsection, center)

                # Made it this far, so it is smaller than all children and we should insert to ourselves
                return rtnode

    def _InsertLeafNode(self, parent, sectionnum):
        '''
            :param RegistrationTreeNode rtnode: Root node to consider insertion on
            :param int sectionnum: Section number to insert
            :param int center: Number of the root for the tree we are searching
        '''

        leafonlynode = self._GetOrCreateMappedNode(sectionnum, leaf_only=True)
        parent.AddChild(leafonlynode)
        assert(not leafonlynode.SectionNumber in self.RootNodes)

        return

    def AddNonControlSections(self, sectionNumbers, center=None):
        '''Add section numbers which cannot have sections registered to them, they exist as leaf nodes only'''

        assert(len(self.RootNodes) == 1)  # This should be used on trees that have only one root

        rtnode = list(self.RootNodes.values())[0]
        if center:
            center = NearestSection(self.SectionNumbers, center)
            rtnode = self.Nodes[center]

        for sectionNumber in sectionNumbers:
            parent = self.FindControlForMapped(rtnode, sectionNumber)
            self._InsertLeafNode(parent, sectionNumber)

        return

    @classmethod
    def CreateRegistrationTree(cls, sectionNumbers, adjacentThreshold=2, center=None):
        sectionNumbers.sort()
        RT = RegistrationTree()

        if len(sectionNumbers) == 0:
            return RT
        elif len(sectionNumbers) == 1:
            RT.AddEmptyRoot(sectionNumbers[0])
            return RT
        else:
            centerindex = (len(sectionNumbers) - 1) / 2
            if not center is None:
                center = NearestSection(sectionNumbers, center)
                centerindex = sectionNumbers.index(center)


            listAdjacentBelowCenter = AdjacentPairs(sectionNumbers, adjacentThreshold, startindex=0, endindex=centerindex)
            listAdjacentAboveCenter = AdjacentPairs(sectionNumbers, adjacentThreshold, startindex=len(sectionNumbers) - 1, endindex=centerindex)

            for (mappedSection, controlSection) in listAdjacentBelowCenter + listAdjacentAboveCenter:
                RT.AddPair(ControlSection=controlSection, MappedSection=mappedSection)

    #        for imapped in range(0, centerindex):
    #            mappedSection = sectionNumbers[imapped]
    #
    #            for icontrol in range(imapped, centerindex):
    #                controlSection = sectionNumbers[icontrol]
    #                if (icontrol - imapped) < numadjacent:
    #                    RT.AddPair(ControlSection=controlSection, MappedSection=mappedSection)
    #                else:
    #                    break
    #
    #        for imapped in range(centerindex + 1, len(sectionNumbers)):
    #            mappedSection = sectionNumbers[imapped]
    #
    #            for icontrol in range(centerindex + 1, imapped):
    #                controlSection = sectionNumbers[icontrol]
    #                if (icontrol - imapped) < numadjacent:
    #                    RT.AddPair(ControlSection=controlSection, MappedSection=mappedSection)
    #                else:
    #                    break

            return RT


def NearestSection(sectionNumbers, reqnumber):
    '''Returns the section number nearest to the section number, or the same section number if the section exists'''
    if reqnumber in sectionNumbers:
        return reqnumber
    else:
        if len(sectionNumbers) == 1:
            return sectionNumbers[0]

        foundNumber = None

        nearest = (sectionNumbers[-1] - sectionNumbers[0]) + reqnumber
        for s in sectionNumbers:
            dist = abs(reqnumber - s)
            if dist < nearest:
                foundNumber = s
                nearest = dist

        return foundNumber


def AdjacentPairs(sectionNumbers, adjacentThreshold, startindex, endindex):
    listAdjacent = []
    if startindex == endindex:
        return listAdjacent

    step = 1
    if startindex > endindex:
        step = -1

    for imapped in range(startindex, endindex + step, step):
            mappedSection = sectionNumbers[imapped]

            for icontrol in range(imapped + step, endindex + step, step):
                controlSection = sectionNumbers[icontrol]
                if (abs(icontrol - imapped)) <= adjacentThreshold:
                    listAdjacent.append((mappedSection, controlSection))
                    # RT.AddPair(ControlSection=controlSection, MappedSection=mappedSection)
                else:
                    break

    return listAdjacent