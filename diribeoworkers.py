# -*- coding: utf-8 -*-
'''
Created on 05.07.2010

@author: anopheles
'''

import hashlib
import shlex
import glob
import uuid
import functools
import os
import subprocess
import re
import diribeomessageboxes
import collections

from diribeomodel import settings, movieclips, series_list, MovieClip, NoConnectionAvailable, MovieClipAssociation
from diribeowrapper import library
from operator import itemgetter
from PyQt4 import QtCore


class WorkerThread(QtCore.QThread):
    
    # Define various signals        
    waiting = QtCore.pyqtSignal()
    finished = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    
    
    def __init__(self):
        QtCore.QThread.__init__(self)
        # Additional thread information
        self.description = "" # The description which is shown in the statusbar
        self.additional_descriptions = collections.defaultdict(lambda : str()) # This description can be altered while the thread is running


    def hash_file(self, file_obj,
                  hasher,
                  callback=lambda byte_count: None,
                  blocksize=4096):
        
        byte_count = 0
        for block in iter(functools.partial(file_obj.read, blocksize), ''):
            hasher.update(block)
            byte_count += len(block)
            # The next line is very important! If you use progress.emit as callback it prevents a deadlock under some conditions
            if byte_count % blocksize ** 2 == 0:                  
                callback(byte_count, self.filesize)
        return hasher.hexdigest()  
    
    
    def calculate_checksum(self, filepath):
        self.filesize = os.path.getsize(filepath)
    
        # For debugging purposes
        def print_progress(byte_count, filesize):
            print '\r%d/%d %6.2f' % (byte_count,
                                 filesize,
                                 100.0 * byte_count / filesize),
    
        with open(filepath, "rb") as iso_file:
            checksum = self.hash_file(iso_file, hashlib.sha224(), self.progress.emit)
            return checksum

    def dameraulevenshtein(self, seq1, seq2, lower = False):
            if lower:
                seq1 = seq1.lower()
                seq2 = seq2.lower()
            """Calculate the Damerau-Levenshtein distance between sequences.
        
            This distance is the number of additions, deletions, substitutions,
            and transpositions needed to transform the first sequence into the
            second. Although generally used with strings, any sequences of
            comparable objects will work.
        
            Transpositions are exchanges of *consecutive* characters; all other
            operations are self-explanatory.
        
            This implementation is O(N*M) time and O(M) space, for N and M the
            lengths of the two sequences.
        
            >>> dameraulevenshtein('ba', 'abc')
            2
            >>> dameraulevenshtein('fee', 'deed')
            2
        
            It works with arbitrary sequences too:
            >>> dameraulevenshtein('abcd', ['b', 'a', 'c', 'd', 'e'])
            2
            """
            # codesnippet:D0DE4716-B6E6-4161-9219-2903BF8F547F
            # Conceptually, this is based on a len(seq1) + 1 * len(seq2) + 1 matrix.
            # However, only the current and two previous rows are needed at once,
            # so we only store those.
            oneago = None
            thisrow = range(1, len(seq2) + 1) + [0]
            for x in xrange(len(seq1)):
                # Python lists wrap around for negative indices, so put the
                # leftmost column at the *end* of the list. This matches with
                # the zero-indexed strings and saves extra calculation.
                twoago, oneago, thisrow = oneago, thisrow, [0] * len(seq2) + [x + 1]
                for y in xrange(len(seq2)):
                    delcost = oneago[y] + 1
                    addcost = thisrow[y - 1] + 1
                    subcost = oneago[y - 1] + (seq1[x] != seq2[y])
       