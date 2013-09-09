'''
Created on Oct 18, 2012

@author: Jamesan
'''

class TransformBase(object):

    def __init__(self):
        self.OnChangeEventListeners = [];
        if(TransformBase.ThreadPool is None):
            TransformBase.ThreadPool = Pools.Threadpool.Thread_Pool();

    @classmethod
    def Load(cls, TransformString):
        pass;

    def Transform(self, point):
        return None

    def InverseTransform(self, point):
        return None

    def AddOnChangeEventListener(self, func):
        self.OnChangeEventListeners.append(func);

    ThreadPool = None;

    def OnTransformChanged(self):
        '''Calls every function registered to be notified when the transform changes.'''


        # Calls every listener when the transform has changed in a way that a point may be mapped to a new position in the fixed space
        tlist = list();
        for func in self.OnChangeEventListeners:
            tlist.append(TransformBase.ThreadPool.add_task("OnTransformChanged calling " + str(func), func));

        for task in tlist:
            task.wait();


    def SplitTrasform(self, transformstring):
        '''Returns transform name, variable points, fixed points'''
        parts = transformstring.split();
        transformName = parts[0];
        assert(parts[1] == 'vp');

        VariableParts = [];
        iVp = 2;
        while(parts[iVp] != 'fp'):
            VariableParts = float(parts[iVp]);
            iVp = iVp + 1


        self.OnChangeEventListeners = [];

        # skip vp # entries
        iVp = iVp + 2
        FixedParts = [];
        for iVp in range(iVp, len(parts)):
            FixedParts = float(parts[iVp]);

        return (transformName, FixedParts, VariableParts);