# -*- coding: utf-8 -*-

import unittest


from diribeoutils import programme_available

class ProcessAvailability(unittest.TestCase):
    
    def test_process_not_available(self):
        self.assertFalse(programme_available("random process name"))


    def test_process_available(self):
        self.assertTrue(programme_available("ffmpeg"))

        
if __name__ == '__main__':
    unittest.main()