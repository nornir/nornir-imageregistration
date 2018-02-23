import logging
import os

import nornir_imageregistration.tile

import nornir_imageregistration.transforms.factory as tfactory
#import nornir_pools
import numpy as np

from . import alignment_record
from . import core
from . import spatial


def _sort_array_on_column(a, iCol, ascending=False):
    '''Sort the numpy array on the specfied column'''
    
    iSorted = np.argsort(a[:, iCol], 0)
    if not ascending:
        iSorted = np.flipud(iSorted)
    return a[iSorted, :]



class LayoutPosition(object):
    '''This is an anchor with a number of springs of a certain length attached.  In our use the anchor is a tile and the spring size
       and strength is determined by the offset to overlap an adjacent tile
       
       Offsets is a numpy array of the form [[ID Y X Weight]]
    '''
    
    iOffsetID = 0
    iOffsetY = 1 
    iOffsetX = 2 
    iOffsetWeight = 3
    
    # offset_dtype = np.dtype([('ID', np.int32), ('Y', np.float32), ('X', np.float32), ('Weight', np.float32)])
     
    @property
    def ID(self):
        return self._ID
    
    @property
    def Position(self):
        '''Our position in the layout'''
        return self._position
    
    @property
    def OffsetArray(self):
        '''Read-only use please'''
        return self._OffsetArray
    
    @property
    def IsIsolated(self):
        '''Sometimes we have tiles which end up isolated, usually due to prune.  When this occurs they have no offsets'''
        return len(self._OffsetArray) == 0
    
    @Position.setter
    def Position(self, value):
        '''Our position in the layout'''
        if not isinstance(value, np.ndarray):
            self._position = np.array(value)
        else:
            self._position = value
        
        assert(self._position.ndim == 1)
        return 
        
    @property
    def ConnectedIDs(self):
        return self._OffsetArray[:, LayoutPosition.iOffsetID]
    
    
    def GetOffset(self, ID):
        iKnown = self.ConnectedIDs == ID
        return self.OffsetArray[iKnown, LayoutPosition.iOffsetY:LayoutPosition.iOffsetX + 1].flatten()
    
    def GetWeight(self, ID):
        iKnown = self.ConnectedIDs == ID
        return self.OffsetArray[iKnown, LayoutPosition.iOffsetWeight]
    
    
    def SetOffset(self, ID, offset, weight):
        '''Set the offset for the specified Layout position ID.  
           This means that when we subtract our position from the other ID's position we hope to obtain this offset value. 
        '''
         
        if np.isnan(weight):
            raise ValueError("weight is not a number")
        
        new_row = np.array((ID, offset[0], offset[1], weight))  # , dtype=LayoutPosition.offset_dtype, ndmin=2)
        iKnown = self.ConnectedIDs == ID
        if np.any(iKnown):
            # Update a row
            self._OffsetArray[iKnown] = new_row            
        else:
            # Insert a new row
            
            self._OffsetArray = np.vstack((self._OffsetArray, new_row))
            if self._OffsetArray.ndim == 1:
                self._OffsetArray = np.reshape(self._OffsetArray, (1, self._OffsetArray.shape[0]))
            else:
                self._OffsetArray = _sort_array_on_column(self._OffsetArray, 0)
            
        return
    
    def TensionVectors(self, connected_positions):
        '''The difference between the current connected_positions and the expected positions based on our offsets
        :param ndarray connected_positions: Position of the connected nodes'''
        
        relative_connected_positions = connected_positions - self.Position
        return relative_connected_positions - self._OffsetArray[:, LayoutPosition.iOffsetY:LayoutPosition.iOffsetX + 1]
    
    def NetTensionVector(self, connected_positions):
        position_difference = self.TensionVectors(connected_positions)
        return np.sum(position_difference, 0)
      
    def WeightedNetTensionVector(self, connected_positions):
        '''The direction of the vector this tile wants to move after summing all of the offsets
        :param ndarray connected_positions: Position of the connected nodes'''
        
        position_difference = self.TensionVectors(connected_positions)
 
        # Cannot weight more than 1.0
        # normalized_weight = self._OffsetArray[:,LayoutPosition.iOffsetWeight] / np.max(self._OffsetArray[:,LayoutPosition.iOffsetWeight])
        normalized_weight = self._OffsetArray[:, LayoutPosition.iOffsetWeight]
        
        assert(np.all(normalized_weight >= 0))
        assert(np.all(normalized_weight <= 1.0))
        weighted_position_difference = position_difference * normalized_weight.reshape((normalized_weight.shape[0], 1))
        
        return np.sum(weighted_position_difference, 0)
         
    
    def ScaleOffsetWeightsByPosition(self, connected_positions):
        '''
        Reweight our set of weights based on how far from this expectation our offsets are.  THis is useful if we believe our initial positions are largely accurate but
        our calculated desired offsets may have errors.
        :param ndarray connected_positions: The locations we believe our connected positions should be.  
        '''

        position_difference = self.TensionVectors(connected_positions)
        distance = np.sqrt(np.sum(position_difference ** 2, 1))
        medianDistance = np.median(distance)
        
        new_weight = distance / medianDistance
        
        self._OffsetArray[:, LayoutPosition.iOffsetWeight] = new_weight
            
        return 
     
    def __init__(self, ID, position, *args, **kwargs):
        
        self._ID = ID 
        self.Position = position
        self._OffsetArray = np.empty((0, 4))  # dtype=LayoutPosition.offset_dtype)
        
    def __str__(self):
        return "%d y:%g x:%g" % (self._ID, self.Position[0], self.Position[1]) 
        

class Layout(object):
    '''Arranges tiles in 2D space to form a mosaic.
       IDs of nodes should be incremental and match the row index of the array'''
    
    # Offsets into node position array
    iNodeID = 0
    iNodeY = 1 
    iNodeX = 2 
    
    @property
    def nodes(self):
        return self._nodes

    @property    
    def MaxWeightedTension(self):
        net_tension_vectors = self.WeightedNetTensionVectors()
        return np.max(core.array_distance(net_tension_vectors))
    
    @property    
    def MaxTension(self):
        net_tension_vectors = self.NetTensionVectors()
        return np.max(core.array_distance(net_tension_vectors))
    
    def Contains(self, ID):
        ''':rtype: bool
           :return: True if layout contains the ID
        '''
        return ID in self._nodes
    
    def SetOffset(self, A_ID, B_ID, offset, weight=1.0):
        '''Specify the expected offset between two nodes in the spring model'''
        A = self.nodes[A_ID]
        B = self.nodes[B_ID]
        A.SetOffset(B.ID, offset, weight)
        B.SetOffset(A.ID, -offset, weight)
        
    def GetPosition(self, ID):
        '''Return the position array for a set of nodes, sorted by node ID'''
        return self.nodes[ID].Position
              
        
    def GetPositions(self, IDs=None):
        '''Return the position array for a set of nodes, sorted by node ID'''
        
        if IDs is None:
            IDs = list(self.nodes.keys())
            IDs.sort()
            
        positions = np.empty((len(IDs), 2))
        for i, tileID in enumerate(IDs):
            positions[i, :] = self.nodes[tileID].Position 
                                         
        return positions
    
    def NetTensionVector(self, ID):
        '''Return the net tension vector of the specified ID'''
        
        node = self.nodes[ID]
        linked_node_positions = self.GetPositions(node.ConnectedIDs)
        
        return node.NetTensionVector(linked_node_positions)
    
    def NetTensionVectors(self):
        '''Return all net tension vectors for our nodes'''
        IDs = list(self.nodes.keys())
        output = np.zeros((len(IDs), 2))
        for i in range(0, len(IDs)):
            ID = IDs[i]
            output[i, :] = self.NetTensionVector(ID)
            
        return output
    
    def WeightedNetTensionVector(self, ID):
        '''Return the net tension vector of the specified ID'''
        
        node = self.nodes[ID]
        linked_node_positions = self.GetPositions(node.ConnectedIDs)
        
        return node.WeightedNetTensionVector(linked_node_positions)
        
    def WeightedNetTensionVectors(self):
        '''Return all net tension vectors for our nodes'''
        IDs = list(self.nodes.keys())
        IDs.sort()
        output = np.zeros((len(IDs), 2))
        for i, TileID in enumerate(IDs):
            output[i, :] = self.WeightedNetTensionVector(TileID)
            
        return output
    
    def _nextID(self):
        '''Generate the next ID number for a position'''
        return self._nodepositions.shape[0]
        
    def CreateNode(self, ID, position):
          
        assert(not ID in self.nodes)
        node = LayoutPosition(ID, position)
        self.nodes[ID] = node
        return
    
        
    def CreateOffsetNode(self, Existing_ID, New_ID, Offset, Weight):
        '''Add a new position to the layout.  Place the new relative to the specified existing position plus an offset'''
        
        new_position = self.GetPosition(Existing_ID) + Offset
        self.CreateNode(New_ID, new_position)
        self.SetOffset(New_ID, Existing_ID, Offset, Weight)
        return 
    
    def __init__(self):
        
        self._nodes = {}
        return
    
    def Translate(self, vector):
        '''Move all nodes by offset'''
        for node in self.nodes.values():
            node.Position = node.Position + vector
            
        return
    
    def Merge(self, layoutB):
        '''Merge layout directly into our layout'''
        self.nodes.update(layoutB.nodes)
    
    @classmethod
    def RelaxNodes(cls, layout_obj, vector_scalar=0.5):
        '''Adjust the position of each node along its tension vector
        :param Layout layout_obj: The layout to relax
        :param float vector_scalar: Multiply the weighted tension vectors by this amount before adjusting the position.  A high value is faster but may not be constrained.  A low value is slower but safe.
        '''
        
        # TODO: Get rid of vector scalar.  Instead calculate the net tension vector at the new position.  Then add them and apply the merged vector. 
        
        node_movement = np.zeros((len(layout_obj.nodes), 3))
        
        # vectors = {}
        
        i = 0
        first = True
        for ID, node in layout_obj.nodes.items():
            
            vector = layout_obj.WeightedNetTensionVector(ID) * vector_scalar
            # vectors[ID] = vector
            row = np.array([ID, vector[0], vector[1]])
            node_movement[i, :] = row
            i += 1
            # Skip the first node, the others can move around it
            node.Position = node.Position + vector
        
        return node_movement
    
    @classmethod
    def MergeLayouts(cls, layoutA, layoutB, offset):
        '''
        Merge B with A by translating all B transforms by offset.
        Then update the dictionary of A
        '''

        layoutB.Translate(offset)
        layoutA.nodes.update(layoutB.nodes) 
        return layoutA
    

def OffsetsSortedByWeight(layout):
    '''
    Return all of a layouts offsets sorted by weight.  
    :return: An array [[TileA_ID, TileB_ID, OffsetY, OffsetX, Weight]] To prevent duplicates we only report offsets where TileA_ID < TileB_ID
    ''' 
    ret_array = np.empty((0, 5))
    for node in layout.nodes.values():
        if node.IsIsolated:
            continue
        
        # Prevent duplicates by skipping IDs less than the nodes
        iNewRows = node.OffsetArray[:, 0] > node.ID 
        if not np.any(iNewRows):
            continue 
        
        new_column = np.ones((np.sum(iNewRows), 1)) * node.ID
        new_rows = np.hstack((new_column, node.OffsetArray[iNewRows, :]))
        ret_array = np.vstack((ret_array, new_rows))
        
    return _sort_array_on_column(ret_array, 4)  

def ScaleOffsetWeightsByPosition(original_layout):
    
    for node in original_layout.nodes.values():
        linked_node_positions = original_layout.GetPositions(node.ConnectedIDs)
        node.ScaleOffsetWeightsByPosition(linked_node_positions)
        
    return

def ScaleOffsetWeightsByPopulationRank(original_layout, min_allowed_weight=0, max_allowed_weight=1.0):
    '''
    Remap offset weights so the highest weight is 1.0 and the lowest is 0
    '''
    
    if min_allowed_weight >= max_allowed_weight:
        raise ValueError("Min allowed weight must be below the max allowed weight")
    
    maxWeight = np.NaN
    minWeight = np.NaN
    
    first = True
    for node in original_layout.nodes.values():
        # Sometimes we have tiles which end up isolated, usually due to prune.  When this occurs they have no scores
        if node.IsIsolated:
            continue
        
        weights = node.OffsetArray[:, LayoutPosition.iOffsetWeight]
        
        if first:
            first = False
            minWeight = np.min(weights)
            maxWeight = np.max(weights)
        else:
            minWeight = min((minWeight, np.min(weights)))
            maxWeight = max((maxWeight, np.max(weights)))
    
    # All the weights are equal... odd
    if maxWeight == minWeight:
        for node in original_layout.nodes.values():
            if node.IsIsolated:
                continue
            
            node.OffsetArray[:, LayoutPosition.iOffsetWeight] = max_allowed_weight
        return
    
    maxWeight -= minWeight
    
    allowed_weight_range = max_allowed_weight - min_allowed_weight
    
    for node in original_layout.nodes.values():
        # Sometimes we have tiles which end up isolated, usually due to prune.  When this occurs they have no scores
        if node.IsIsolated:
            continue
        
        node.OffsetArray[:, LayoutPosition.iOffsetWeight] = (node.OffsetArray[:, LayoutPosition.iOffsetWeight] - minWeight) / maxWeight
        node.OffsetArray[:, LayoutPosition.iOffsetWeight] *= allowed_weight_range
        node.OffsetArray[:, LayoutPosition.iOffsetWeight] += min_allowed_weight
        assert(np.alltrue(node.OffsetArray[:, LayoutPosition.iOffsetWeight] >= min_allowed_weight))
        assert(np.alltrue(node.OffsetArray[:, LayoutPosition.iOffsetWeight] <= max_allowed_weight))
                
    return 

    
def RelaxLayout(layout_obj, max_tension_cutoff=5, max_iter=50):
                
        
        max_tension = layout_obj.MaxWeightedTension
                 
        i = 0
        
#         MovieImageDir = os.path.join(self.TestOutputPath, "relax_movie")
#         if not os.path.exists(MovieImageDir):
#             os.makedirs(MovieImageDir)
            
        print("Relax Layout")
            
        while max_tension > max_tension_cutoff and i < max_iter:
            print("\t%d %g" % (i, max_tension))
            Layout.RelaxNodes(layout_obj)
            max_tension = layout_obj.MaxWeightedTension
            # node_distance = setup_imagetest.array_distance(node_movement[:,1:3])             
            # max_distance = np.max(node_distance,0)
            i += 1
            
            # nornir_shared.plot.VectorField(layout_obj.GetPositions(), layout_obj.NetTensionVectors(), filename)
            # pool.add_task("Plot step #%d" % (i), nornir_shared.plot.VectorField,layout_obj.GetPositions(), layout_obj.WeightedNetTensionVectors(), filename)
            
        return layout_obj

        

def BuildLayoutWithHighestWeightsFirst(original_layout):
    '''
    Constructs a mosaic by sorting all of the match results according to strength. 
    
    :param dict tiles: Dictionary of tile objects containing alignment records to other tiles
    '''

    placedTiles = dict()
    
    sorted_offsets = OffsetsSortedByWeight(original_layout) 

    LayoutList = [] 
    for iRow in range(0, sorted_offsets.shape[0]):
        row = sorted_offsets[iRow, :]      
        A_ID = row[0]
        B_ID = row[1]
        YOffset = row[2]
        XOffset = row[3]
        Weight = row[4]
        offset = row[2:4]
        
        print("%d -> %d (%g,%g w: %g)" % (A_ID, B_ID, YOffset, XOffset, Weight))

        if np.isnan(Weight):
            print("Skip: Invalid weight, not a number")
            continue

        ALayout = GetLayoutForID(LayoutList, A_ID)
        BLayout = GetLayoutForID(LayoutList, B_ID)

        if ALayout is None and BLayout is None:
            new_layout = Layout()
            new_layout.CreateNode(A_ID, np.zeros((2)))
            new_layout.CreateNode(B_ID, offset)
            new_layout.SetOffset(A_ID, B_ID, offset, Weight) 
            LayoutList.append(new_layout)
            print("New layout")

        elif (not ALayout is None) and (not BLayout is None):
            # Need to merge the layouts? See if they are the same
            if ALayout == BLayout:
                # Already mapped
                if B_ID in ALayout.nodes[A_ID].ConnectedIDs: 
                    print("Skip: Already mapped")
                else:
                    ALayout.SetOffset(A_ID, B_ID, offset, Weight)
            else:
                MergeLayoutsWithNodeOffset(ALayout, BLayout, A_ID, B_ID, offset, Weight)
                print("Merged")
                LayoutList.remove(BLayout)
        else:
            
            if ALayout is None and not BLayout is  None:
                BLayout.CreateOffsetNode(B_ID, A_ID, -offset, Weight)
                # We'll pick it up on the next pass
                # print("Skip: Getting it next time")
                # continue
                
            else:
                ALayout.CreateOffsetNode(A_ID, B_ID, offset, Weight)

    # OK, we should have a single list of layouts
    LargestLayout = LayoutList[0]

    return LargestLayout


def CreateTransform(layout, ID, bounding_box):
    '''
    Create a transform for the position in the layout
    '''
    OriginalImageSize = (bounding_box[spatial.iRect.MaxY] - 1, bounding_box[spatial.iRect.MaxX] - 1)
    
    return tfactory.CreateRigidTransform(OriginalImageSize, OriginalImageSize, 0, layout.GetPosition(ID)) 
    
    
 
def GetLayoutForID(listLayouts, ID):
    '''Given a list of tile layouts, returns the layout containing the given ID'''

    if listLayouts is None:
        return None

    for layout in listLayouts:
        if layout.Contains(ID):
            return layout

    return None
        
    
def MergeLayoutsWithNodeOffset(layoutA, layoutB, NodeInA, NodeInB, offset, weight):
    '''
    Merge B with A by translating all B transforms by offset.
    Then update the dictionary of A
    '''

    PositionInA = layoutA.GetPosition(NodeInA)
    PositionInB = layoutB.GetPosition(NodeInB)
    
    ExpectedMovingTilePosition = offset + PositionInA
    MovingPositionDifference = ExpectedMovingTilePosition - PositionInB
    
    layoutB.Translate(MovingPositionDifference)
    layoutA.Merge(layoutB)
    
    layoutA.SetOffset(NodeInA, NodeInB, offset, weight)
