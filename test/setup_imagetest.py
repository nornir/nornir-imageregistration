'''
Created on Mar 21, 2013

@author: u0490822
'''
import unittest
import os
import logging
from nornir_shared.misc import SetupLogging
import shutil


class ImageTestBase(unittest.TestCase):

    @property
    def classname(self):
        clsstr = str(self.__class__.__name__)
        return clsstr


    @property
    def TestInputPath(self):
        if 'TESTINPUTPATH' in os.environ:
            TestInputDir = os.environ["TESTINPUTPATH"]
            self.assertTrue(os.path.exists(TestInputDir), "Test input directory specified by TESTINPUTPATH environment variable does not exist")
            return TestInputDir
        else:
            self.fail("TESTINPUTPATH environment variable should specfify input data directory")

        return None

    @property
    def TestOutputPath(self):
        if 'TESTOUTPUTPATH' in os.environ:
            TestOutputDir = os.environ["TESTOUTPUTPATH"]
            return os.path.join(TestOutputDir, self.classname)
        else:
            self.fail("TESTOUTPUTPATH environment variable should specfify input data directory")

        return None
    
    @property
    def TestLogPath(self):
        if 'TESTOUTPUTPATH' in os.environ:
            TestOutputDir = os.environ["TESTOUTPUTPATH"]
            return os.path.join(TestOutputDir, "Logs", self.classname)
        else:
            self.fail("TESTOUTPUTPATH environment variable should specfify input data directory")

        return None

    def setUp(self):
        self.TestDataSource = os.path.join(self.TestInputPath, "Images")
        self.VolumeDir = self.TestOutputPath

        # Remove output of earlier tests
        if os.path.exists(self.VolumeDir):
            shutil.rmtree(self.VolumeDir)

        os.makedirs(self.VolumeDir)

        SetupLogging(self.TestLogPath)
        self.Logger = logging.getLogger(self.classname)


if __name__ == "__main__":
    # import syssys.argv = ['', 'Test.testName']
    unittest.main()