# -*- coding: utf-8 -*-

import unittest


from diribeomodel import MovieClip


class MovieClipSetFunctionality(unittest.TestCase):
    def test_length(self):
        filepath = "tests/test1.png"
        movieclip_set = set()
        movieclip_set.add(MovieClip(filepath, None))
        movieclip_set.add(MovieClip(filepath, None))
        self.assertEqual(len(movieclip_set), 1)
    

class MovieClipEqualFunctionality(unittest.TestCase):
    def test_equality(self):
        filepath = "tests/test1.png"
        self.assertEqual(MovieClip(filepath, {"test" : "testpics"}), MovieClip(filepath, {"test" : "testpics"}))
        
        
class MovieClipHashFunctionality(unittest.TestCase):
    def test_hashing(self):
        filepath = "tests/test1.png"
        self.assertEqual(hash(MovieClip(filepath, None)), hash(MovieClip(filepath, None)))

        
class MovieClipEqualFileDifferentName(unittest.TestCase):
    def test_equal(self):
        # test1.png and test7.png are the same file just with different names
        clip1 = MovieClip("tests/test1.png", None)
        clip2 = MovieClip("tests/test7.png", None)
        self.assertEqual(set([clip1, clip2]), set([clip1]))
    

    def test_not_equal(self):
        # test1.png and test6.png are not the same file
        clip1 = MovieClip("tests/test1.png", None)
        clip2 = MovieClip("tests/test6.png", None)
        self.assertNotEqual(set([clip1, clip2]), set([clip1]))

        
class MovieClipMergeFunctionality(unittest.TestCase):
    def test_merge_simple(self):
        clip1 = MovieClip("tests/test1.png", {"foo" : "test1234"})
        clip2 = MovieClip("tests/test1.png", {"bar" : "test1337"})
        
        clip1.merge(clip2)
        
        self.assertEqual(len(clip1.identifier), 2)
        
    def test_merge_exception(self):
        # test1.png and test6.png are not the same file
        clip1 = MovieClip("tests/test1.png", {"foo" : "test1234"})
        clip2 = MovieClip("tests/test6.png", {"bar" : "test1337"})
        
        try:
            clip1.merge(clip2) # This throws an exceptions since both objects don't have the same checksum.
            no_exception = True
        except TypeError:
            no_exception = False
            
        self.assertFalse(no_exception)
            
        
if __name__ == '__main__':
    unittest.main()